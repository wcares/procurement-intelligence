"""A small MCP server to show the MCP connector working: it offers documents as MCP resources.

Two kinds of document, either or both:
  --folder DIR         every file in DIR (drop a file in during a demo and the next read finds it)
  --wb-projects IDS    the newest procurement plans of these World Bank projects, fetched live from the World Bank
                       documents API (search.worldbank.org/api/v3/wds) when the server starts; their text is fetched
                       when a resource is read
  --contracts          a read-only tool, contract_awards(project_id), returning the project's contract awards fetched
                       live from World Bank Finances One with that dataset's own column names: a stand-in for a table a
                       client would offer as a tool (a Databricks Unity Catalog function)

The folder is listed afresh on every request, and watched: when a file is added, changed or removed, the server tells
every client listening (MCP subscriptions/listen) that the list or that resource changed, so a subscribed connector
takes the change in at once instead of on its next scheduled read.

It is a stand-in for a client's own system (an e-procurement platform, a document store) that offers its documents
over MCP; the connector (procintel.pipeline.mcp_source) reads it like any other MCP server. Each resource carries its
size and last-modified time, so the connector sees a change without reading every document.

    .venv/bin/python scripts/demo_mcp_server.py --folder data/mcp_demo --wb-projects P163035,P181295
"""
from __future__ import annotations

import argparse
import asyncio
import mimetypes
import sys
from contextlib import asynccontextmanager
from typing import Any
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))   # procintel, for the Finances One reader
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.resources.resource_manager import ResourceManager
from mcp.server.mcpserver.resources.types import FunctionResource
from mcp.shared.subscriptions import ResourcesListChanged, ResourceUpdated
from mcp_types import Annotations, ToolAnnotations

WDS = "https://search.worldbank.org/api/v3/wds"
PLANS_PER_PROJECT = 2
TIMEOUT = 30
WATCH_SECONDS = 2


class LiveResources(ResourceManager):
    """The fixed resources (procurement plans) plus the folder as it is now: the SDK's manager keeps the list from
    startup and has no removal, so the folder part is listed afresh each time."""

    def __init__(self, fixed: list[FunctionResource], folder: Path | None):
        super().__init__()
        self.fixed, self.folder = fixed, folder

    def _all(self) -> list[FunctionResource]:
        return (folder_resources(self.folder) if self.folder else []) + self.fixed

    def list_resources(self):
        return self._all()

    async def get_resource(self, uri, context):
        for r in self._all():
            if r.uri == str(uri):
                return r
        return await super().get_resource(uri, context)


def snapshot(folder: Path) -> dict[str, tuple[float, int]]:
    return {f"file:///{f.name}": (f.stat().st_mtime, f.stat().st_size)
            for f in folder.iterdir() if f.is_file() and not f.name.startswith(".")}


async def watch(server: MCPServer, folder: Path) -> None:
    """Publish a change event for every file added, changed or removed (subscriptions/listen)."""
    bus = server._subscriptions   # the server's event bus; MCPServer has no public publish outside a request
    last = snapshot(folder)
    while True:
        await asyncio.sleep(WATCH_SECONDS)
        now = snapshot(folder)
        if set(now) != set(last):
            await bus.publish(ResourcesListChanged())
        for uri in set(now) & set(last):
            if now[uri] != last[uri]:
                await bus.publish(ResourceUpdated(uri))
        for uri in set(now) ^ set(last):
            await bus.publish(ResourceUpdated(uri))
        last = now


def folder_resources(folder: Path) -> list[FunctionResource]:
    out = []
    for f in sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith(".")):
        st = f.stat()
        modified = datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
        out.append(FunctionResource(
            uri=f"file:///{f.name}", name=f.name, title=f.name,
            description=f"File in the demo folder ({st.st_size:,} bytes)",
            mime_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream",
            annotations=Annotations(last_modified=modified), meta={"size": st.st_size},
            fn=(lambda f=f: f.read_bytes())))
    return out


def plan_resources(projects: list[str]) -> list[FunctionResource]:
    out = []
    with httpx.Client(timeout=TIMEOUT) as http:
        for pid in projects:
            r = http.get(WDS, params={"format": "json", "rows": PLANS_PER_PROJECT, "docty_exact": "Procurement Plan",
                                      "projectid": pid, "fl": "id,docdt,display_title,txturl", "sort": "docdt",
                                      "order": "desc"})
            r.raise_for_status()
            docs = [v for k, v in r.json().get("documents", {}).items() if k != "facets"]
            for d in docs:
                if not d.get("txturl"):
                    continue
                title = f"Procurement Plan {pid} ({(d.get('docdt') or '')[:10]})"
                out.append(FunctionResource(
                    uri=f"worldbank://documents/{d['id']}", name=f"procurement-plan-{pid}-{d['id']}.txt", title=title,
                    description=(d.get("display_title") or "").strip() or title, mime_type="text/plain",
                    annotations=Annotations(last_modified=d.get("docdt")),
                    meta={"project_id": pid, "source_url": d["txturl"]},
                    fn=(lambda url=d["txturl"]: _text(url))))
    return out


def _text(url: str) -> str:
    r = httpx.get(url, timeout=TIMEOUT, follow_redirects=True)
    r.raise_for_status()
    return r.text


def add_contracts_tool(server: MCPServer) -> None:
    @server.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True),
                 structured_output=True)
    def contract_awards(project_id: str) -> dict[str, Any]:
        """A World Bank project's contract awards from Finances One (live), with that dataset's column names."""
        from procintel.ingestion import contract_awards as fone
        return {"rows": fone.fetch_project(project_id)}


def build(folder: Path | None, projects: list[str], contracts: bool = False) -> MCPServer:
    @asynccontextmanager
    async def lifespan(server: MCPServer):
        task = asyncio.create_task(watch(server, folder)) if folder else None
        try:
            yield {}
        finally:
            if task:
                task.cancel()

    server = MCPServer("procintel-demo-source", instructions="Documents for the Procurement Intelligence demo: files "
                       "from a folder and live World Bank procurement plans.", lifespan=lifespan)
    plans = plan_resources(projects)
    server._resource_manager = LiveResources(plans, folder)   # the folder listed live (see LiveResources)
    if contracts:
        add_contracts_tool(server)
    n = len(plans) + (len(folder_resources(folder)) if folder else 0)
    print(f"demo MCP server: {n} document(s){', watching ' + str(folder) if folder else ''}", file=sys.stderr)
    return server


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--folder", type=Path, help="offer every file in this folder")
    ap.add_argument("--wb-projects", default="", help="comma-separated World Bank project ids: their newest procurement plans")
    ap.add_argument("--contracts", action="store_true", help="offer the contract_awards tool")
    ap.add_argument("--http", type=int, metavar="PORT", help="serve over Streamable HTTP on 127.0.0.1:PORT/mcp instead of stdio")
    args = ap.parse_args()
    if args.folder:
        args.folder.mkdir(parents=True, exist_ok=True)
    server = build(args.folder, [p.strip() for p in args.wb_projects.split(",") if p.strip()], args.contracts)
    if args.http:
        server.run("streamable-http", host="127.0.0.1", port=args.http)
    else:
        server.run("stdio")


if __name__ == "__main__":
    main()
