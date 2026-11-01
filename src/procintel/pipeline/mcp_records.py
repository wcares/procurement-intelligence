"""Records from MCP tools: a server in data/mcp_sources.json may name read-only tools whose rows become records, for
servers that offer data as tools rather than documents (Databricks' managed MCP servers: Unity Catalog functions,
Genie). Entity type McpRecord.

    {"name": "client-databricks",
     "url": "https://<workspace-host>/api/2.0/mcp/functions/<catalog>/<schema>/<function>",
     "bearer_env": "PROCINTEL_DATABRICKS_TOKEN",
     "tools": [{"name": "<the tool name the server lists>", "arguments": {"since": "2024-01-01"},
                "as": "ContractAward",
                "fields": {"wb_contract_number": "contract_no", "supplier_id": "supplier_id", "supplier": "supplier_name",
                           "contract_ref": "bid_reference", "signing_date": "signed_on", "amount_usd": "amount_usd",
                           "project_id": "project_id"}}]}

    name        the tool as the server lists it (python -m procintel.pipeline.mcp_records tools <server> shows them)
    arguments   fixed: the connector never builds a query, so it cannot be made to run anything else
    as          ContractAward: rows are contract awards, written to contract_award as Finances One awards are (the
                award dates of their packages are filled from them); rows (the default): kept for reference only
    fields      our column <- the tool's column; ContractAward needs at least wb_contract_number and supplier_id
    key         for "rows": the tool's column, or list of columns, that identifies a row
    title       for "rows": the columns that name a row on the Connectors page (default: its first non-date columns)

Only tools named here are called. A tool the server marks as destructive, or as not read-only, is refused. Each
call's rows are the complete set for that tool, so a row that disappears is a removal; a server or tool that fails
fails the whole read (logged, retried with back-off), so nothing is taken for removed.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from procintel.pipeline import mcp_source

TYPE = "McpRecord"
WATCHED = ["record_hash"]
SOURCE = "MCP tools named in data/mcp_sources.json (read-only tools with fixed arguments, e.g. Databricks functions)"
KINDS = {"ContractAward": ("wb_contract_number", "supplier_id")}   # what rows can become, and their key columns
DATES = {"signing_date", "as_of_date"}
MAX_ROWS = 50_000


def tool_sources() -> list[tuple[dict, dict]]:
    """(server, tool entry) for every tool named in the configuration. Raises ValueError for an unusable entry."""
    out = []
    for s in mcp_source.servers():
        for t in s.get("tools") or []:
            if not t.get("name"):
                raise ValueError(f"server {s['name']}: each tool needs a name")
            kind = t.get("as", "rows")
            if kind != "rows" and kind not in KINDS:
                raise ValueError(f"server {s['name']}, tool {t['name']}: as must be rows or one of {sorted(KINDS)}")
            need = KINDS.get(kind) or ()
            if kind == "rows" and not t.get("key"):
                raise ValueError(f"server {s['name']}, tool {t['name']}: rows need a key column")
            if kind != "rows" and not all(c in (t.get("fields") or {}) for c in need):
                raise ValueError(f"server {s['name']}, tool {t['name']}: fields must map {', '.join(need)}")
            out.append((s, t))
    return out


def parse_rows(result) -> list[dict]:
    """Rows from a tool result: structured content (a list of objects, or an object holding one), else the text: JSON
    (a list of objects, or {"columns": [...], "rows": [[...]]}) or CSV with a header line."""
    data = result.structured_content
    if data is None:
        text = "".join(getattr(c, "text", "") or "" for c in result.content).strip()
        try:
            data = json.loads(text)
        except ValueError:
            return list(csv.DictReader(io.StringIO(text))) if text else []
    if isinstance(data, dict):
        if isinstance(data.get("columns"), list) and isinstance(data.get("rows"), list):
            cols = [c if isinstance(c, str) else c.get("name") for c in data["columns"]]
            return [dict(zip(cols, r)) for r in data["rows"]]
        lists = [v for v in data.values() if isinstance(v, list)]
        data = lists[0] if len(lists) == 1 else [data]
    return [r for r in data if isinstance(r, dict)][:MAX_ROWS]


def _date(v):
    if v in (None, ""):
        return None
    try:
        return pd.Timestamp(v).date().isoformat()
    except (ValueError, TypeError):
        return None


def to_record(server: dict, tool: dict, row: dict) -> tuple[str, dict] | None:
    """(key, record) for one tool row, or None when it lacks its key."""
    kind = tool.get("as", "rows")
    if kind == "ContractAward":
        rec = {col: row.get(src) for col, src in tool["fields"].items()}
        for col in DATES & set(rec):
            rec[col] = _date(rec[col])
        if rec.get("supplier_id") is not None:
            rec["supplier_id"] = str(rec["supplier_id"])
            rec.setdefault("firm_id", int(rec["supplier_id"]) if rec["supplier_id"].isdigit() else None)
        inner = "|".join(str(rec.get(c) or "") for c in KINDS[kind])
    else:
        rec = dict(row)
        cols = tool["key"] if isinstance(tool["key"], list) else [tool["key"]]
        inner = "|".join(str(row.get(c) or "") for c in cols)
    if not inner.strip("|"):
        return None
    body = json.dumps(rec, sort_keys=True, default=str)
    return f"{server['name']}|{tool['name']}|{inner}", {
        "server": server["name"], "tool": tool["name"], "kind": kind, "record": rec,
        "record_hash": hashlib.sha256(body.encode()).hexdigest()}


async def _tool_rows(server: dict, tools: list[dict]) -> dict[str, list[dict]]:
    out = {}
    async with mcp_source._client(server) as client:
        listed = {t.name: t for t in (await client.list_tools()).tools}
        for tool in tools:
            info = listed.get(tool["name"])
            if info is None:
                raise ValueError(f"the server has no tool {tool['name']!r} (it lists {sorted(listed)[:10]})")
            a = info.annotations
            if a and (a.destructive_hint or a.read_only_hint is False):
                raise ValueError(f"tool {tool['name']!r} is not read-only by the server's own description; not called")
            result = await client.call_tool(tool["name"], tool.get("arguments") or {})
            if result.is_error:
                raise RuntimeError(f"tool {tool['name']!r} failed: {''.join(getattr(c, 'text', '') for c in result.content)[:300]}")
            out[tool["name"]] = parse_rows(result)
    return out


def read_source(ctx: dict) -> tuple[dict[str, dict], bool]:
    rows: dict[str, dict] = {}
    by_server: dict[str, tuple[dict, list[dict]]] = {}
    for s, t in tool_sources():
        by_server.setdefault(s["name"], (s, []))[1].append(t)
    for name, (s, tools) in by_server.items():
        try:
            got = mcp_source._run(_tool_rows(s, tools))
        except Exception as e:   # noqa: BLE001 - named, then left to the detection log
            raise RuntimeError(f"MCP server {name}: {mcp_source.reason(e)}") from e
        for t in tools:
            for r in got[t["name"]]:
                kr = to_record(s, t, r)
                if kr:
                    rows[kr[0]] = kr[1]
    gone = {k.split("|", 1)[0] for k in ctx.get("tracked", [])} - set(by_server)
    return rows, not gone


def _connect(db_path: Path | None = None):
    from procintel.pipeline import store
    con = store.connect(db_path)
    con.execute("""CREATE TABLE IF NOT EXISTS mcp_record (key VARCHAR, server VARCHAR, tool VARCHAR, kind VARCHAR,
                   record VARCHAR, record_hash VARCHAR, taken_at TIMESTAMP)""")
    return con


def read_db() -> dict[str, dict]:
    con = _connect()
    try:
        return {k: {"server": s, "tool": t, "kind": kind, "record": json.loads(r), "record_hash": h}
                for k, s, t, kind, r, h in con.execute("SELECT key, server, tool, kind, record, record_hash FROM mcp_record").fetchall()}
    finally:
        con.close()


def apply(keys: list[str], events: dict[str, dict], ctx: dict) -> list[dict]:
    """Action apply_mcp_records: keep every record (table mcp_record) and write contract awards to contract_award, as
    Finances One awards are written; their packages' award dates are filled by the next action (fill_award_dates)."""
    from procintel.pipeline import actions
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    awards, gone_awards = [], []
    con = _connect()
    try:
        for k in keys:
            ev = events.get(k)
            if ev is None:
                continue
            had = con.execute("SELECT kind FROM mcp_record WHERE key = ?", [k]).fetchone()
            con.execute("DELETE FROM mcp_record WHERE key = ?", [k])
            new = ev.get("new")
            inner = k.split("|", 2)[2]
            if new is None:
                if had and had[0] == "ContractAward":       # only an award this connector wrote is taken out
                    gone_awards.append(inner)
                continue
            con.execute("INSERT INTO mcp_record VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [k, new["server"], new["tool"], new["kind"], json.dumps(new["record"], default=str),
                         new["record_hash"], now])
            if new["kind"] == "ContractAward":
                awards.append({c: new["record"].get(c) for c in _award_columns()} | {"__key": inner})
    finally:
        con.close()
    if not awards and not gone_awards:
        return []
    actions._upsert("contract_award", "wb_contract_number || '|' || supplier_id", awards, gone_awards)
    return [actions.DATA]


def _award_columns() -> list[str]:
    from procintel.ingestion import contract_awards
    return contract_awards.TABLE_COLUMNS


def overview(db_path: Path | None = None, latest: int = 10) -> dict:
    """For the Connectors page: the tools called and the latest records."""
    try:
        conf = tool_sources()
        tools, error = [{"server": s["name"], "tool": t["name"], "as": t.get("as", "rows")} for s, t in conf], None
    except ValueError as e:
        conf, tools, error = [], [], str(e)
    titles = {(s["name"], t["name"]): t.get("title") for s, t in conf}
    con = _connect(db_path)
    try:
        counts = {(s, t): n for s, t, n in con.execute("SELECT server, tool, count(*) FROM mcp_record GROUP BY ALL").fetchall()}
        last = con.execute("SELECT server, tool, kind, record, taken_at FROM mcp_record ORDER BY taken_at DESC LIMIT ?",
                           [latest]).fetchall()
    finally:
        con.close()
    for t in tools:
        t["records"] = counts.get((t["server"], t["tool"]), 0)

    def title(server, tool, kind, rec):
        if kind == "ContractAward":
            return f"{rec.get('contract_ref') or rec.get('wb_contract_number')} · {rec.get('supplier') or ''}".strip(" ·")
        cols = titles.get((server, tool)) or [c for c in rec if "date" not in c.lower()][:3]
        return " · ".join(str(rec.get(c)) for c in cols if rec.get(c) not in (None, ""))
    records = [{"server": s, "tool": t, "kind": k, "title": title(s, t, k, json.loads(r)), "takenAt": at.isoformat() + "Z"}
               for s, t, k, r, at in last]
    return {"tools": tools, "records": records, "error": error}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="MCP tools: list what a configured server offers")
    ap.add_argument("command", choices=["tools"])
    ap.add_argument("server", help="a server name from data/mcp_sources.json")
    args = ap.parse_args()
    server = next((s for s in mcp_source.servers() if s["name"] == args.server), None)
    if server is None:
        raise SystemExit(f"no server {args.server!r} in {mcp_source.config_path()}")

    async def go():
        async with mcp_source._client(server) as client:
            return (await client.list_tools()).tools
    for t in mcp_source._run(go()):
        a = t.annotations
        ro = "read-only" if a and a.read_only_hint else "destructive" if a and a.destructive_hint else "not marked read-only"
        print(f"{t.name}  ({ro})\n    {(t.description or '').strip()[:200]}\n    arguments: {json.dumps((t.input_schema or {}).get('properties', {}))[:300]}")


if __name__ == "__main__":
    main()
