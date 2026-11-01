"""A Databricks MCP bridge: the table functions of one Unity Catalog schema as read-only MCP tools.

Databricks' own managed MCP server for Unity Catalog functions (https://<host>/api/2.0/mcp/functions/<catalog>/<schema>)
needs a Public Preview that a Free Edition workspace cannot switch on. This bridge does the same job from outside: it
lists the schema's table-valued functions (Unity Catalog API) and offers each as a tool named the way Databricks names
them (<catalog>__<schema>__<function>), with the function's own parameters; a call runs
`SELECT * FROM <catalog>.<schema>.<function>(:param, ...)` on a SQL warehouse through the SQL Statement Execution API,
with the arguments bound as parameters, never pasted into SQL. Only functions are offered, so nothing can be written.

    .venv/bin/python scripts/databricks_mcp_server.py --host https://dbc-....cloud.databricks.com \\
        --schema workspace.procintel_demo --token-env PROCINTEL_DATABRICKS

The token is read from the environment variable named by --token-env (a Databricks personal access token) and never
printed. On a workspace with managed MCP servers, point the connector at Databricks' own URL instead; the tools are the
same.
"""
from __future__ import annotations

import argparse
import inspect
import os
import sys
import time
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

TIMEOUT = 120
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)


class Databricks:
    def __init__(self, host: str, token: str):
        self.host = host.rstrip("/")
        self.http = httpx.Client(timeout=TIMEOUT, headers={"Authorization": f"Bearer {token}"})
        self._warehouse: str | None = None

    def get(self, path: str, **params) -> dict:
        r = self.http.get(self.host + path, params=params)
        r.raise_for_status()
        return r.json()

    def warehouse(self) -> str:
        if not self._warehouse:
            whs = self.get("/api/2.0/sql/warehouses").get("warehouses", [])
            if not whs:
                raise RuntimeError("the workspace has no SQL warehouse")
            self._warehouse = next((w["id"] for w in whs if w.get("state") == "RUNNING"), whs[0]["id"])
        return self._warehouse

    def functions(self, catalog: str, schema: str) -> list[dict]:
        fns = self.get("/api/2.1/unity-catalog/functions", catalog_name=catalog, schema_name=schema).get("functions", [])
        # the list leaves out the parameters: each function is read in full
        full = [self.get(f"/api/2.1/unity-catalog/functions/{f['full_name']}") for f in fns]
        return [f for f in full if f.get("data_type") == "TABLE_TYPE"]      # table functions: rows out, nothing written

    def query(self, statement: str, params: list[dict]) -> list[dict]:
        r = self.http.post(self.host + "/api/2.0/sql/statements", json={
            "warehouse_id": self.warehouse(), "statement": statement, "parameters": params,
            "wait_timeout": "50s", "on_wait_timeout": "CONTINUE"})
        r.raise_for_status()
        j = r.json()
        deadline = time.time() + TIMEOUT
        while j.get("status", {}).get("state") in ("PENDING", "RUNNING") and time.time() < deadline:
            time.sleep(2)
            j = self.get(f"/api/2.0/sql/statements/{j['statement_id']}")
        if j.get("status", {}).get("state") != "SUCCEEDED":
            raise RuntimeError(f"query {j.get('status', {}).get('state')}: {j.get('status', {}).get('error', {}).get('message', '')[:300]}")
        cols = [c["name"] for c in j["manifest"]["schema"]["columns"]]
        rows = [dict(zip(cols, r)) for r in (j.get("result") or {}).get("data_array") or []]
        # a large result comes in chunks
        for link in (j.get("result") or {}).get("next_chunk_internal_link") and [j["result"]["next_chunk_internal_link"]] or []:
            while link:
                part = self.get(link)
                rows += [dict(zip(cols, r)) for r in part.get("data_array") or []]
                link = part.get("next_chunk_internal_link")
        return rows


def add_function_tool(server: MCPServer, db: Databricks, fn: dict) -> str:
    full = fn["full_name"]                                    # catalog.schema.function
    name = full.replace(".", "__")
    params = [p["name"] for p in (fn.get("input_params") or {}).get("parameters", [])]

    def call(**kwargs) -> dict[str, Any]:
        placeholders = ", ".join(f":{p}" for p in params)
        bound = [{"name": p, "value": None if kwargs.get(p) is None else str(kwargs[p])} for p in params]
        return {"rows": db.query(f"SELECT * FROM {full}({placeholders})", bound)}

    call.__name__ = name
    call.__doc__ = fn.get("comment") or f"Rows of the Databricks function {full}"
    call.__signature__ = inspect.Signature(
        [inspect.Parameter(p, inspect.Parameter.KEYWORD_ONLY, annotation=str) for p in params],
        return_annotation=dict[str, Any])
    call.__annotations__ = {p: str for p in params} | {"return": dict[str, Any]}
    server.tool(name=name, annotations=READ_ONLY, structured_output=True)(call)
    return name


def build(host: str, schema: str, token: str) -> MCPServer:
    catalog, _, sch = schema.partition(".")
    db = Databricks(host, token)
    server = MCPServer("databricks-bridge", instructions=f"Read-only table functions of the Databricks schema {schema}.")
    names = [add_function_tool(server, db, f) for f in db.functions(catalog, sch)]
    print(f"databricks bridge: {len(names)} function(s) from {schema}: {', '.join(names)}", file=sys.stderr)
    return server


def main() -> None:
    ap = argparse.ArgumentParser(description="Databricks Unity Catalog table functions as read-only MCP tools")
    ap.add_argument("--host", required=True, help="the workspace URL, https://dbc-....cloud.databricks.com")
    ap.add_argument("--schema", required=True, help="catalog.schema whose table functions become tools")
    ap.add_argument("--token-env", default="PROCINTEL_DATABRICKS", help="environment variable holding the access token")
    ap.add_argument("--http", type=int, metavar="PORT", help="serve over Streamable HTTP on 127.0.0.1:PORT/mcp instead of stdio")
    args = ap.parse_args()
    token = os.environ.get(args.token_env)
    if not token:
        raise SystemExit(f"environment variable {args.token_env} is not set")
    server = build(args.host, args.schema, token)
    if args.http:
        server.run("streamable-http", host="127.0.0.1", port=args.http)
    else:
        server.run("stdio")


if __name__ == "__main__":
    main()
