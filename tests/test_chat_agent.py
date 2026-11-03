import json
from datetime import date
from types import SimpleNamespace

from procintel.answering.retrieve import Hit
from procintel.assistant import agent, tools
from procintel.core import decide, llm

HIT = Hit(chunk_id="c1", doc_id="d1", title="ICR Rural Roads", doc_type="ICR", url="u", section="Lessons", para=None,
          kind="text", text="Civil works were delayed because the contractor lacked equipment and the rainy season stopped work.",
          project_id="P123456", project_name="Rural Roads", country_code="MA", score=1.0)


class Retriever:
    def __init__(self):
        self.queries = []

    def search(self, query, k=8, country=None, proc_group=None):
        self.queries.append((query, country))
        return [HIT]

    def passage(self, chunk_id):
        return HIT if chunk_id == "c1" else None


def _state():
    options = {"countries": [{"code": "MA", "name": "Kingdom of Morocco", "region": "MNA"}], "sectors": [],
               "procGroups": [{"code": "CW", "label": "Civil works"}],
               "methods": [{"code": "RFB", "label": "Request for bids", "procGroups": ["CW"], "n": 3}]}
    return SimpleNamespace(retriever=Retriever(), options=options, dashboard=None)


def _call(name, args, i):
    return SimpleNamespace(id=f"call{i}", function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def test_the_agent_calls_tools_then_answers_and_the_answer_is_checked(monkeypatch):
    monkeypatch.setattr(decide, "available", lambda: False)
    monkeypatch.setattr(llm, "model_name", lambda prefix=llm.ANSWER: "anthropic/claude-sonnet-5-5")
    final = {"sentences": [
        {"text": "Civil works were delayed because the contractor lacked equipment.", "kind": "evidence", "citations": [1]},
        {"text": "Past roads works took 999 days.", "kind": "data"},           # a number no tool returned: dropped
        {"text": "Schedule works outside the rainy season.", "kind": "general"}]}
    turns = iter([SimpleNamespace(content=None, tool_calls=[_call("search_reports", {"query": "civil works delays", "country": "Morocco"}, 1)]),
                  SimpleNamespace(content=json.dumps(final), tool_calls=None)])
    sent = []
    monkeypatch.setattr(llm, "chat", lambda messages, tools_=None, **k: (sent.append(list(messages)), next(turns))[1])
    st = _state()
    out = agent.run(st, [{"role": "user", "content": "what went wrong on roads in Morocco?"}], {"packages": []}, "", date(2026, 11, 2))
    assert st.retriever.queries == [("civil works delays", "MA")]                 # the country name became its code
    assert out["steps"] == ['Searched the reports for "civil works delays" (MA)']
    assert [(s["kind"], s["citations"]) for s in out["answer"]["answer"]] == [("evidence", [0]), ("general", [])]
    assert out["answer"]["citations"][0]["id"] == "c1"
    assert sent[1][-1]["role"] == "tool" and json.loads(sent[1][-1]["content"])["passages"][0]["n"] == 1


def test_the_agent_can_change_the_plan_and_reports_the_changes(monkeypatch):
    monkeypatch.setattr(decide, "available", lambda: False)
    monkeypatch.setattr(llm, "model_name", lambda prefix=llm.ANSWER: "anthropic/claude-sonnet-5-5")
    change = {"country": "Morocco", "packages": [{"name": "Road works", "action": "add", "type": "works", "value_usd": 5000000}]}
    final = {"sentences": [{"text": "I added the road works to your plan.", "kind": "general"}]}
    turns = iter([SimpleNamespace(content=None, tool_calls=[_call("update_plan", change, 1)]),
                  SimpleNamespace(content=json.dumps(final), tool_calls=None)])
    monkeypatch.setattr(llm, "chat", lambda *a, **k: next(turns))
    out = agent.run(_state(), [{"role": "user", "content": "add 5M of road works in Morocco"}], {"packages": []}, "", date(2026, 11, 2))
    assert out["plan"]["countryCode"] == "MA" and out["plan"]["packages"][0]["procGroup"] == "CW"
    assert out["changes"] and out["steps"][0].startswith("Updated your plan")


def test_tool_failures_and_unknown_tools_come_back_as_errors_the_model_can_read():
    sess = tools.Session(state=_state(), plan={"packages": []}, results="", today=date(2026, 11, 2))
    assert "no tool" in tools.run(sess, "drop_everything", "{}")["error"]
    assert "error" in tools.run(sess, "search_reports", "{not json")
    assert all(t.schema()["function"]["parameters"]["type"] == "object" for t in tools.TOOLS.values())


def test_the_agent_is_used_only_for_a_model_that_calls_tools(monkeypatch):
    monkeypatch.delenv("PROCINTEL_CHAT_TOOLS", raising=False)
    monkeypatch.setattr(llm, "supports_tools", lambda prefix=llm.ANSWER: False)
    assert not agent.enabled()
    monkeypatch.setattr(llm, "supports_tools", lambda prefix=llm.ANSWER: True)
    assert agent.enabled()
    monkeypatch.setenv("PROCINTEL_CHAT_TOOLS", "off")
    assert not agent.enabled()


def test_every_chat_answer_says_where_it_came_from(monkeypatch):
    """The card under each answer: the model, what it was built from (what the tools brought in), the sentence kinds."""
    from procintel.answering import answer
    from procintel.assistant import converse, tools
    from procintel.answering.retrieve import Hit
    hit = Hit(chunk_id="c1", doc_id="d1", title="t", doc_type="x", url="u", section="S", para="1", kind="text",
              text="Delays came from weak contractors.", project_id="P", project_name="n", country_code="KE",
              score=1.0, via="bm25", tag=None, tag_confidence=None, problem=None)
    monkeypatch.setattr(converse.llm, "model_name", lambda prefix="llm": "test-model")
    monkeypatch.setattr(converse.decide, "available", lambda: False)
    raw = '{"sentences": [{"text": "Delays came from weak contractors.", "kind": "evidence", "citations": [1]}, ' \
          '{"text": "Plan a buffer.", "kind": "general"}]}'
    used = [answer.basis("conversation", "The last 2 messages"), answer.basis("assessment", "Assessment of CW by RFB in KE", "217 comparable packages")]
    out = converse.assemble(None, raw, [hit], "", "first", used)
    assert out["provenance"] == {"model": "test-model", "basis": used, "kinds": {"evidence": 1, "general": 1}}
    sess = tools.Session(state=None, plan={}, results="", today=None)
    sess.used.append(answer.basis("plan", "Your plan"))
    assert [b["kind"] for b in sess.used] == ["plan"] and "detail" not in sess.used[0]


def test_a_local_server_is_asked_whether_it_takes_tools(monkeypatch):
    import io
    import json
    from procintel.core import llm
    llm._server_tools.clear()
    monkeypatch.setenv("PROCINTEL_LLM_MODEL", "openai/saluki-27b")
    monkeypatch.setenv("PROCINTEL_LLM_API_BASE", "http://127.0.0.1:9/v1")
    asked = []

    def fake_open(url, timeout):
        asked.append(url)
        return io.BytesIO(json.dumps({"chat_template_caps": {"supports_tools": True}}).encode())
    monkeypatch.setattr(llm.urllib.request if hasattr(llm, "urllib") else __import__("urllib.request").request, "urlopen", fake_open)
    assert llm.supports_tools() and asked == ["http://127.0.0.1:9/props"]
    assert llm.supports_tools() and len(asked) == 1                       # asked once per server
    llm._server_tools.clear()
    monkeypatch.setattr(__import__("urllib.request").request, "urlopen", lambda url, timeout: (_ for _ in ()).throw(OSError("down")))
    assert not llm.supports_tools()                                       # a server that does not answer: no tools
