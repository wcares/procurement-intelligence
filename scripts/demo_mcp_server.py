"""A small MCP server to show the MCP connector working: it offers documents as MCP resources.

Two kinds of document, either or both:
  --folder DIR         every file in DIR (drop a file in during a demo and the next read finds it)
  --wb-projects IDS    the newest procurement plans of these World Bank projects, fetched live from the World Bank
                       documents API (search.worldbank.org/api/v3/wds) when the server starts; their text is fetched
                       when a resource is read

It is a stand-in for a client's own system (an e-procurement platform, a document store) that offers its documents
over MCP; the connector (procintel.pipeline.mcp_source) reads it like any other MCP server. Each resource carries its
size and last-modified time, so the connector sees a change without reading every document.

    .venv/bin/python scripts/demo_mcp_server.py --folder data/mcp_demo --wb-projects P163035,P181295
"""
from __future__ import annotations

import argparse
import mimetypes
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.resources.types import FunctionResource
from mcp_types import Annotations

WDS = "https://search.worldbank.org/api/v3/wds"
PLANS_PER_PROJECT = 2
TIMEOUT = 30


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


def build(folder: Path | None, projects: list[str]) -> MCPServer:
    server = MCPServer("procintel-demo-source", instructions="Documents for the Procurement Intelligence demo: files "
                       "from a folder and live World Bank procurement plans.")
    resources = (folder_resources(folder) if folder else []) + plan_resources(projects)
    for res in resources:
        server.add_resource(res)
    print(f"demo MCP server: {len(resources)} document(s)", file=sys.stderr)
    return server


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--folder", type=Path, help="offer every file in this folder")
    ap.add_argument("--wb-projects", default="", help="comma-separated World Bank project ids: their newest procurement plans")
    args = ap.parse_args()
    if args.folder:
        args.folder.mkdir(parents=True, exist_ok=True)
    build(args.folder, [p.strip() for p in args.wb_projects.split(",") if p.strip()]).run("stdio")


if __name__ == "__main__":
    main()
