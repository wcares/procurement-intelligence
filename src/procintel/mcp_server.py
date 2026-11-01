"""The engine as an MCP server: an assistant (Claude, Copilot, any MCP client) can assess a package, ask the evidence and
read a cited passage, and gets the engine's checked, cited output rather than raw documents.

It is a thin client of the backend API, so sign-in, the guardrails and the feedback log all apply as for the website:
  PROCINTEL_MCP_API        the backend (default http://127.0.0.1:8000)
  PROCINTEL_MCP_USER       an account to sign in with (a planner account is enough)
  PROCINTEL_MCP_PASSWORD   its password; read from the environment, never shown
With sign-in off on the backend, no account is needed.

Tools (all read-only; none changes data):
  list_options     the countries, procurement types and methods assess_package accepts
  assess_package   days from tender notice to award (typical and slow case), risk flags with their evidence,
                   lessons from past reports, similar contracts, caveats
  ask_evidence     a question answered only from the reports: every sentence with its numbered citations, each
                   checked against the passage it cites; a question the reports do not cover is refused
  get_passage      a cited passage in full, by the id a citation gives

    python -m procintel.mcp_server               # stdio (Claude Desktop, Claude Code: "command" in the client's config)
    python -m procintel.mcp_server --http 8090   # Streamable HTTP on 127.0.0.1:8090/mcp
"""
from __future__ import annotations

import argparse
import os
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

TIMEOUT = 180    # seconds: an answer takes about half a minute with the local models, longer when they wake
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
COOKIE = "procintel_session"


class Backend:
    """Signs in once (again when the session ends) and calls the API. The session cookie is sent by hand: the backend
    marks it Secure, which a client keeps from a plain-http address."""

    def __init__(self, base: str | None = None):
        self.base = (base or os.environ.get("PROCINTEL_MCP_API") or "http://127.0.0.1:8000").rstrip("/")
        self.http = httpx.Client(timeout=TIMEOUT)
        self.session: str | None = None

    def _login(self) -> None:
        user, pw = os.environ.get("PROCINTEL_MCP_USER", ""), os.environ.get("PROCINTEL_MCP_PASSWORD", "")
        if not user or not pw:
            raise RuntimeError("the backend asks for sign-in: set PROCINTEL_MCP_USER and PROCINTEL_MCP_PASSWORD")
        r = self.http.post(f"{self.base}/auth/login", json={"username": user, "password": pw})
        if r.status_code != 200:
            raise RuntimeError(f"sign-in refused ({r.status_code})")
        self.session = r.cookies.get(COOKIE)

    def call(self, method: str, path: str, body: dict | None = None) -> Any:
        for attempt in (1, 2):
            headers = {"Cookie": f"{COOKIE}={self.session}"} if self.session else {}
            r = self.http.request(method, f"{self.base}{path}", json=body, headers=headers)
            if r.status_code == 401 and attempt == 1:
                self._login()
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"{method} {path}: {r.status_code} {r.text[:200]}")
            return r.json()


def _citation(c: dict, n: int | None = None) -> dict[str, Any]:
    out = {"passageId": c["id"], "report": c["title"], "section": c["section"], "quote": c["quote"], "url": c["url"],
           "project": f"{c.get('projectName') or ''} ({c.get('projectId')})".strip()}
    return ({"n": n} | out) if n is not None else out


def shape_assessment(r: dict) -> dict[str, Any]:
    """The assessment as an assistant needs it: the numbers, each risk with its evidence, the lessons with sources."""
    p, t = r.get("prediction") or {}, r.get("timeline") or {}
    return {
        "daysToAward": {"typical": p.get("days_p50") or t.get("median"), "slowCase": p.get("days_p90") or t.get("p90"),
                        "chanceOver180Days": p.get("p_long"), "basis": p.get("basis") or "historical median",
                        "comparablePackages": t.get("n"), "comparedWith": t.get("scope")},
        "risks": [{"risk": f["label"], "level": f["level"], "from": f["basis"], "detail": f["detail"],
                   "evidence": [{"what": e["label"], "detail": e["detail"], "url": e.get("url")} for e in f.get("evidence", [])]}
                  for f in r.get("risks", [])],
        "lessons": [_citation(pr["citation"]) | {"matchedOn": pr.get("matchedOn", [])} for pr in r.get("precedents", [])],
        "similarContracts": [{"package": s["packageId"], "description": s["description"], "country": s["countryCode"],
                              "daysToAward": s["tenderToAwardDays"]} for s in r.get("similarPackages", [])[:5]],
        "governance": [{"indicator": g["indicator"], "year": g["year"], "value": g["value"]} for g in r.get("governance", [])],
        "caveats": (r.get("meta") or {}).get("caveats", []),
    }


def shape_answer(r: dict) -> dict[str, Any]:
    cites = r.get("citations", [])
    out = {"answered": not r.get("unsupported"),
           # the API gives each sentence's citations as positions in the list (0 first); here they are the numbers n
           "answer": [{"sentence": s["text"], "citations": [i + 1 for i in s["citations"]]} for s in r.get("answer", [])],
           "citations": [_citation(c, i + 1) for i, c in enumerate(cites)],
           "caveats": (r.get("meta") or {}).get("caveats", [])}
    if r.get("unsupported") and r.get("fallback"):
        fb = r["fallback"]
        out["closestPassages"] = [_citation(c, i + 1) for i, c in enumerate(fb.get("citations", []))]
    return out


def build(backend: Backend | None = None) -> MCPServer:
    api = backend or Backend()
    server = MCPServer("procurement-intelligence", instructions=(
        "Evidence-backed procurement planning on World Bank open data. Use list_options for valid codes, "
        "assess_package for a tender's expected time to award and its risks, ask_evidence for lessons from completion "
        "and supervision reports. Quote the citations given; do not add facts they do not support."))

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def list_options() -> dict[str, Any]:
        """The countries, procurement types (GO goods, CW civil works, CS consulting services, NC non-consulting) and
        procurement methods (with the types each applies to) that assess_package accepts."""
        o = api.call("GET", "/options")
        return {"countries": [{"code": c["code"], "name": c["name"]} for c in o["countries"]],
                "procurementTypes": o["procGroups"],
                "methods": [{"code": m["code"], "label": m["label"], "types": m["procGroups"]} for m in o["methods"]],
                "sectors": o["sectors"]}

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def assess_package(country_code: str, procurement_type: str, method_code: str, sector: str | None = None,
                       estimated_value_usd: float | None = None, description: str | None = None) -> dict[str, Any]:
        """Assess a planned procurement package: typical and slow-case days from tender notice to contract award
        (gradient-boosted trees where they beat the historical median), risk flags each with the notices, reports or
        indicators they rest on, lessons from past reports, similar past contracts and caveats.
        procurement_type: GO, CW, CS or NC; codes as list_options gives them."""
        body = {"countryCode": country_code, "procGroup": procurement_type, "methodCode": method_code, "sector": sector,
                "estimatedValueUsd": estimated_value_usd, "description": description}
        return shape_assessment(api.call("POST", "/assess", {k: v for k, v in body.items() if v is not None}))

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def ask_evidence(question: str, country_code: str | None = None, procurement_type: str | None = None) -> dict[str, Any]:
        """Answer a question from World Bank completion and supervision reports only. Every sentence lists the numbers
        of the citations it rests on, and each was checked against its passage; when the reports do not answer it,
        answered is false and the closest passages are given instead of a guess. Takes about half a minute."""
        body = {"question": question, "countryCode": country_code, "procGroup": procurement_type}
        return shape_answer(api.call("POST", "/ask", {k: v for k, v in body.items() if v is not None}))

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def get_passage(passage_id: str) -> dict[str, Any]:
        """A cited passage in full, with its report, section and link, by the passageId a citation gives."""
        return _citation(api.call("GET", f"/passages/{passage_id}"))

    return server


def main() -> None:
    ap = argparse.ArgumentParser(description="The Procurement Intelligence engine as an MCP server")
    ap.add_argument("--http", type=int, metavar="PORT", help="serve over Streamable HTTP on 127.0.0.1:PORT/mcp instead of stdio")
    args = ap.parse_args()
    server = build()
    if args.http:
        server.run("streamable-http", host="127.0.0.1", port=args.http)
    else:
        server.run("stdio")


if __name__ == "__main__":
    main()
