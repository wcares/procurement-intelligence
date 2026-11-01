"""MCP servers as a source: the documents an MCP server offers as resources become uploads, read like a file added on
the website.

The servers are listed in data/mcp_sources.json (edited by an admin; a server is never added from the web):

    [{"name": "demo", "command": [".venv/bin/python", "scripts/demo_mcp_server.py", "--folder", "data/mcp_demo"]},
     {"name": "client-docs", "url": "https://example.org/mcp", "headers": {"Authorization": "PROCINTEL_MCP_CLIENT_DOCS_TOKEN"},
      "uri_prefix": "docs://", "trusted": false}]

    name        letters, digits, - and _; part of every item's key (<name>|<resource uri>)
    command     a local server started for each read (stdio), as [program, arg, ...], run from the project folder
    url         a remote server (Streamable HTTP)
    headers     HTTP headers, each named by the environment variable that holds its value (never the value itself)
    uri_prefix  only resources whose URI starts with this
    trusted     true: a completion report from this server joins the evidence at once; false (default): it waits for an
                admin, as a planner's upload does (procintel.intake.process)
    enabled     false: skipped

Each read lists every server's resources (entity type McpDocument). An item's fingerprint is its name, MIME type, size
and last-modified time as the server lists them, so a change is seen without reading every document; a server that
lists neither size nor time has its documents read and hashed instead. The connector only lists and reads resources:
it calls no tools, so a server cannot be made to act. Added and changed documents are read by the action
ingest_mcp_documents, saved as uploads (uploaded_by "mcp:<name>") and run through intake; a changed document replaces
its earlier upload, a removed one takes its upload out (procintel.intake.process.remove). Table mcp_item (pipeline
store) records which upload holds which item.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from procintel.core import paths

TYPE = "McpDocument"
WATCHED = ["name", "mime_type", "size", "last_modified", "content_hash"]
SOURCE = "MCP servers listed in data/mcp_sources.json (resources only; no tools are called)"
MAX_ITEMS = 500                   # per server and read
MAX_BYTES = 50 * 1024 * 1024      # per document, as for uploads (procintel.intake.extract)
TIMEOUT = 120                     # seconds for one server's whole read
NAME = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
FORMATS = {"application/pdf": "pdf", "text/plain": "txt", "text/markdown": "md", "text/html": "html",
           "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx"}


def config_path() -> Path:
    return paths.DATA_DIR / "mcp_sources.json"


def servers() -> list[dict]:
    """The configured servers that are switched on. Raises ValueError for an entry that cannot be used."""
    f = config_path()
    if not f.exists():
        return []
    out = []
    for s in json.loads(f.read_text()):
        if not isinstance(s, dict) or not NAME.match(str(s.get("name", ""))):
            raise ValueError(f"{f.name}: each server needs a name of letters, digits, - and _ ({s!r:.80})")
        if bool(s.get("command")) == bool(s.get("url")):
            raise ValueError(f"{f.name}: server {s['name']} needs either a command or a url")
        if s.get("enabled", True):
            out.append(s)
    return out


def key(server: str, uri: str) -> str:
    return f"{server}|{uri}"


def _client(server: dict):
    from mcp import Client, StdioServerParameters
    if server.get("command"):
        cmd = list(server["command"])
        return Client(StdioServerParameters(command=cmd[0], args=cmd[1:], cwd=str(paths.ROOT)),
                      read_timeout_seconds=TIMEOUT)
    import httpx2
    from mcp.client.streamable_http import streamable_http_client
    headers = {}
    for header, var in (server.get("headers") or {}).items():
        if not os.environ.get(var):
            raise ValueError(f"server {server['name']}: environment variable {var} (header {header}) is not set")
        headers[header] = os.environ[var]
    http = httpx2.AsyncClient(headers=headers, timeout=TIMEOUT)
    return Client(streamable_http_client(server["url"], http_client=http), read_timeout_seconds=TIMEOUT)


async def _read(client, uri: str) -> bytes:
    result = await client.read_resource(uri)
    parts = []
    for c in result.contents:
        parts.append(c.text.encode() if getattr(c, "text", None) is not None else base64.b64decode(c.blob))
    data = b"".join(parts)
    if len(data) > MAX_BYTES:
        raise ValueError(f"{uri}: {len(data):,} bytes, more than {MAX_BYTES:,}")
    return data


async def _list(server: dict) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    async with _client(server) as client:
        cursor = None
        while len(rows) < MAX_ITEMS:
            page = await client.list_resources(cursor=cursor)
            for r in page.resources:
                uri = str(r.uri)
                if server.get("uri_prefix") and not uri.startswith(server["uri_prefix"]):
                    continue
                modified = r.annotations.last_modified if r.annotations else None
                size = r.size if r.size is not None else (r.meta or {}).get("size")
                rows[key(server["name"], uri)] = {
                    "server": server["name"], "uri": uri, "name": r.name, "title": r.title or r.name,
                    "mime_type": r.mime_type, "size": size,
                    "last_modified": str(modified) if modified else None, "content_hash": None,
                    "description": r.description}
                if size is None and not modified:   # nothing to compare by: read it and compare the content
                    rows[key(server["name"], uri)]["content_hash"] = hashlib.sha256(await _read(client, uri)).hexdigest()
            cursor = page.next_cursor
            if not cursor:
                break
    return rows


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, TIMEOUT))


def list_items(server: dict) -> dict[str, dict]:
    return _run(_list(server))


def read_item(server: dict, uri: str) -> bytes:
    async def go():
        async with _client(server) as client:
            return await _read(client, uri)
    return _run(go())


# --- the source reader (procintel.pipeline.entities) -------------------------------------------------------------------

def read_source(ctx: dict) -> tuple[dict[str, dict], bool]:
    """Every configured server's resources. A server that cannot be read fails the whole read (logged, retried with
    back-off), so its documents are not taken for removed. Complete unless documents are known from a server that is
    no longer listed: those are kept until the server is back or an admin removes them."""
    rows: dict[str, dict] = {}
    conf = servers()
    for s in conf:
        try:
            rows.update(list_items(s))
        except Exception as e:   # noqa: BLE001 - named, then left to the detection log
            raise RuntimeError(f"MCP server {s['name']}: {type(e).__name__}: {e}") from e
    listed = {s["name"] for s in conf}
    gone = {k.split("|", 1)[0] for k in ctx.get("tracked", [])} - listed
    return rows, not gone


def read_db() -> dict[str, dict]:
    """The items already taken in (table mcp_item), so a reconciliation after a full refresh compares like with like."""
    con = _connect()
    try:
        return {k: json.loads(row) for k, row in con.execute("SELECT key, item FROM mcp_item WHERE upload_id IS NOT NULL")
                .fetchall()}
    finally:
        con.close()


def describe() -> str:
    """For the Connectors page: what the next read covers."""
    try:
        conf = servers()
    except ValueError as e:
        return f"configuration error: {e}"
    if not conf:
        return "no MCP server configured (data/mcp_sources.json)"
    names = ", ".join(f"{s['name']} ({'local' if s.get('command') else 'remote'})" for s in conf)
    return f"every resource of {len(conf)} server(s): {names}; compared by size and last-modified time"


# --- the action: take documents in -------------------------------------------------------------------------------------

def _connect(db_path: Path | None = None):
    from procintel.pipeline import store
    con = store.connect(db_path)
    con.execute("""CREATE TABLE IF NOT EXISTS mcp_item (key VARCHAR, server VARCHAR, uri VARCHAR, item VARCHAR,
                   upload_id VARCHAR, status VARCHAR, note VARCHAR, taken_at TIMESTAMP)""")
    return con


def _set(k: str, row: dict | None, upload_id: str | None, status: str, note: str) -> None:
    con = _connect()
    try:
        con.execute("DELETE FROM mcp_item WHERE key = ?", [k])
        server, uri = k.split("|", 1)
        con.execute("INSERT INTO mcp_item VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [k, server, uri, json.dumps(row) if row else None, upload_id, status, note[:500],
                     datetime.now(timezone.utc).replace(tzinfo=None)])
    finally:
        con.close()


def _upload_of(k: str) -> str | None:
    con = _connect()
    try:
        r = con.execute("SELECT upload_id FROM mcp_item WHERE key = ?", [k]).fetchone()
        return r[0] if r else None
    finally:
        con.close()


def items(db_path: Path | None = None) -> list[dict]:
    """What was taken in from MCP servers, newest first (for the Connectors page and checks)."""
    con = _connect(db_path)
    try:
        cols = ["key", "server", "uri", "item", "upload_id", "status", "note", "taken_at"]
        out = [dict(zip(cols, r)) for r in con.execute(f"SELECT {', '.join(cols)} FROM mcp_item ORDER BY taken_at DESC").fetchall()]
    finally:
        con.close()
    for d in out:
        d["item"] = json.loads(d["item"]) if d["item"] else None
        d["taken_at"] = d["taken_at"].isoformat() + "Z"
    return out


def fmt_of(row: dict) -> str | None:
    from procintel.intake import extract
    by_name = extract.format_of(row.get("name") or "")
    mime = (row.get("mime_type") or "").split(";")[0].strip().lower()
    return by_name or FORMATS.get(mime)


def ingest(keys: list[str], events: dict[str, dict], ctx: dict) -> list[dict]:
    """Action ingest_mcp_documents: read each added or changed document, save it as an upload and run intake; take the
    upload of a changed or removed one out. Intake queues its own indexing (Upload.ingested), so nothing is returned."""
    from procintel.intake import process, store as intake_store
    conf = {s["name"]: s for s in servers()}
    for k in keys:
        ev = events.get(k)
        if ev is None:
            continue
        old = _upload_of(k)
        row = ev.get("new")
        if row is None:                                   # removed from the server
            if old:
                process.remove(old, jobs_db=ctx.get("jobs_db"))
            _set(k, None, None, "removed", "no longer offered by the server")
            continue
        server = conf.get(row["server"])
        fmt = fmt_of(row)
        if server is None or fmt is None:
            why = "server no longer configured" if server is None else f"format not readable ({row.get('mime_type')})"
            _set(k, row, old, "skipped", why)
            continue
        try:
            content = read_item(server, row["uri"])
        except Exception as e:   # noqa: BLE001 - one document failing does not stop the others
            _set(k, row, old, "failed", f"read failed: {type(e).__name__}: {e}")
            continue
        filename = row["name"] if "." in (row["name"] or "") else f"{row['name']}.{fmt}"
        up = intake_store.save(filename, content, fmt, f"mcp:{row['server']}")
        if up["status"] == "received":
            up = process.run(up["upload_id"], jobs_db=ctx.get("jobs_db"), trusted=bool(server.get("trusted")))
        if old and old != up["upload_id"]:
            process.remove(old, jobs_db=ctx.get("jobs_db"))   # the earlier version leaves the evidence
        _set(k, row, up["upload_id"], up["status"], (up["stages"][-1]["detail"] if up.get("stages") else ""))
    return []
