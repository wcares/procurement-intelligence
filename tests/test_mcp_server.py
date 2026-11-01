import asyncio

import pytest

from procintel import mcp_server

CITE = {"id": "c1", "title": "ICR Rural Roads", "section": "Lessons ¶3", "quote": "Re-bidding delayed the works.",
        "url": "https://documents.worldbank.org/x.pdf", "projectId": "P123456", "projectName": "Rural Roads"}


class FakeBackend:
    def __init__(self):
        self.calls = []

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path == "/options":
            return {"countries": [{"code": "KE", "name": "Kenya", "region": "AFE"}], "sectors": ["Transport"],
                    "procGroups": [{"code": "CW", "label": "Civil works"}],
                    "methods": [{"code": "RFB", "label": "Request for bids", "procGroups": ["CW"], "n": 9}]}
        if path == "/assess":
            return {"prediction": {"basis": "model", "days_p50": 112, "days_p90": None, "p_long": 0.2},
                    "timeline": {"n": 217, "median": 108.0, "p90": 240.0, "scope": "KE CW RFB"},
                    "risks": [{"label": "Re-bidding", "level": "high", "basis": "statistic", "detail": "1 in 5",
                               "evidence": [{"kind": "package", "ref": "p", "label": "Package X", "detail": "re-bid", "url": None}]}],
                    "precedents": [{"citation": CITE, "relevance": 0.9, "matchedOn": ["sector"]}],
                    "similarPackages": [], "governance": [{"indicator": "CPIA", "year": 2024, "value": 3.5}],
                    "meta": {"caveats": ["a caveat"]}}
        if path == "/ask":
            return {"answer": [{"text": "Re-bidding delayed works.", "citations": [0]}], "citations": [CITE],
                    "unsupported": False, "meta": {"caveats": []}}
        if path == "/passages/c1":
            return CITE
        raise AssertionError(path)


def _call(server, tool, args):
    from mcp import Client

    async def go():
        async with Client(server) as c:
            names = [t.name for t in (await c.list_tools()).tools]
            res = await c.call_tool(tool, args)
            return names, res
    return asyncio.run(go())


def test_the_tools_shape_the_backend_answers_and_keep_the_citations():
    fake = FakeBackend()
    server = mcp_server.build(fake)
    names, res = _call(server, "assess_package", {"country_code": "KE", "procurement_type": "CW", "method_code": "RFB"})
    assert sorted(names) == ["ask_evidence", "assess_package", "get_passage", "list_options"]
    out = res.structured_content
    assert out["daysToAward"]["typical"] == 112 and out["daysToAward"]["slowCase"] == 240.0   # the slow case from history
    assert out["risks"][0]["evidence"][0]["what"] == "Package X"
    assert out["lessons"][0]["passageId"] == "c1" and out["lessons"][0]["quote"] == CITE["quote"]
    assert fake.calls[-1] == ("POST", "/assess", {"countryCode": "KE", "procGroup": "CW", "methodCode": "RFB"})

    _, res = _call(server, "ask_evidence", {"question": "Why were works delayed?"})
    out = res.structured_content
    assert out["answered"] and out["answer"][0]["citations"] == [1] and out["citations"][0]["n"] == 1
    _, res = _call(server, "get_passage", {"passage_id": "c1"})
    assert res.structured_content["report"] == "ICR Rural Roads"


def test_every_tool_is_marked_read_only():
    from mcp import Client

    async def go():
        async with Client(mcp_server.build(FakeBackend())) as c:
            return (await c.list_tools()).tools
    tools = asyncio.run(go())
    assert all(t.annotations.read_only_hint and not t.annotations.destructive_hint for t in tools)


def test_signing_in_needs_an_account_from_the_environment(monkeypatch):
    monkeypatch.delenv("PROCINTEL_MCP_USER", raising=False)
    monkeypatch.delenv("PROCINTEL_MCP_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="PROCINTEL_MCP_USER"):
        mcp_server.Backend("http://127.0.0.1:9")._login()
