import pytest

from procintel.answering.retrieve import DB_PATH

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="needs data/procintel.duckdb (run ingest, model, chunk)")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from procintel.api.app import app
    with TestClient(app) as c:
        yield c


def test_options(client):
    r = client.get("/options").json()
    assert len(r["countries"]) > 10 and {g["code"] for g in r["procGroups"]} == {"GO", "CW", "CS", "NC"}


def test_assess_matches_known_benchmark(client):
    # Kenya / civil works / RFB: 215 packages, median 112 days (212 / 111.5 before the ongoing portfolio, 2026-10-26;
    # 198 / 116 before contract signing dates filled
    # missing award dates; 195 / 113 before re-bid awards under "-N" references were linked, both 2026-10-25);
    # regenerate web/src/mocks/data.json when this changes
    r = client.post("/assess", json={"countryCode": "KE", "procGroup": "CW", "methodCode": "RFB"}).json()
    assert (r["timeline"]["n"], r["timeline"]["median"]) == (215, 112.0)
    assert r["meta"]["source"] == "live" and r["precedents"]
    assert all(p["citation"]["quote"] for p in r["precedents"])


def test_ask_cites_every_sentence(client, monkeypatch):
    monkeypatch.delenv("PROCINTEL_LLM_MODEL", raising=False)
    r = client.post("/ask", json={"question": "Why were contracts terminated?"}).json()
    assert not r["unsupported"] and r["answer"]
    for s in r["answer"]:
        assert s["citations"] and all(0 <= c < len(r["citations"]) for c in s["citations"])
        assert any(s["text"] in r["citations"][c]["quote"] for c in s["citations"])  # verbatim quote


def test_ask_unsupported(client):
    r = client.post("/ask", json={"question": "What is the boiling point of tungsten?"}).json()
    assert r["unsupported"] and r["answer"] == [] and r["citations"] == []
    assert r["fallback"]["answer"][0]["text"]          # a plain reply, not a bare refusal


def test_bad_input_is_400(client):
    assert client.post("/assess", json={"countryCode": "KE", "procGroup": "XX", "methodCode": "RFB"}).status_code == 400
    assert client.post("/ask", json={"question": ""}).status_code == 400


@pytest.fixture(autouse=True)
def feedback_db(tmp_path, monkeypatch):
    """Every API test logs responses to a temporary feedback database, never to data/feedback.duckdb."""
    from procintel.learning import feedback
    monkeypatch.setattr(feedback, "DB_PATH", tmp_path / "fb.duckdb")
    return feedback


def test_feedback_attaches_to_a_logged_response(client, feedback_db, monkeypatch):
    monkeypatch.delenv("PROCINTEL_LLM_MODEL", raising=False)
    r = client.post("/ask", json={"question": "Why were contracts terminated?"}).json()
    rid, cid = r["meta"]["responseId"], r["citations"][0]["id"]
    assert client.post("/feedback", json={"responseId": rid, "rating": "useful"}).status_code == 200
    ok = client.post("/feedback", json={"responseId": rid, "rating": "bad_citation", "citationId": cid, "comment": "off topic"})
    assert ok.status_code == 200 and ok.json()["ok"]
    s = feedback_db.summary()
    assert s["responses"] == 1 and ("ask", "bad_citation", 1) in s["ratings"] and s["flagged_citations"] == [(cid, 1)]


def test_feedback_is_refused_for_unknown_responses_and_citations(client, feedback_db, monkeypatch):
    monkeypatch.delenv("PROCINTEL_LLM_MODEL", raising=False)
    rid = client.post("/assess", json={"countryCode": "KE", "procGroup": "CW", "methodCode": "RFB"}).json()["meta"]["responseId"]
    assert client.post("/feedback", json={"responseId": "nope", "rating": "useful"}).status_code == 400
    assert client.post("/feedback", json={"responseId": rid, "rating": "bad_citation", "citationId": "not-shown"}).status_code == 400
    assert client.post("/feedback", json={"responseId": rid, "rating": "bad_citation"}).status_code == 400  # no citation named
    assert client.post("/feedback", json={"responseId": rid, "rating": "great"}).status_code == 400


@pytest.fixture
def saved_config(tmp_path, monkeypatch):
    from procintel.answering import answer
    from procintel.api import config
    monkeypatch.setattr(config, "SAVED", tmp_path / "config.json")
    monkeypatch.setattr(answer, "SEARCH_K", answer.SEARCH_K)  # restored after the test
    monkeypatch.setattr(answer, "DECIDE_MIN", answer.DECIDE_MIN)
    return config


def test_config_lists_settings_and_hides_keys(client):
    keys = {s["key"]: s for s in client.get("/config").json()["settings"]}
    assert keys["search_k"]["editable"] and not keys["embed_model"]["editable"]
    assert not any("key" in k.split("_")[-1] and k != "search_k" for k in keys)  # no API keys exposed
    assert "api_key" not in str(keys)


def test_config_update_applies_live_and_saves(client, saved_config):
    from procintel.answering import answer
    r = client.put("/config", json={"values": {"search_k": 8, "decide_min": "0.6"}, "save": True})
    assert r.status_code == 200 and answer.SEARCH_K == 8 and answer.DECIDE_MIN == 0.6
    assert saved_config.SAVED.exists() and '"search_k": 8' in saved_config.SAVED.read_text()


def test_config_rejects_invalid_values_and_applies_nothing(client, saved_config):
    from procintel.answering import answer
    before = answer.SEARCH_K
    for body in [{"search_k": 0}, {"search_k": "lots"}, {"embed_model": "x"}, {"nope": 1},
                 {"llm_api_base": "ftp://x"}, {"llm_extra_body": "{not json"}, {"search_k": 7, "decide_min": 5}]:
        r = client.put("/config", json={"values": body})
        assert r.status_code == 400, body
    assert answer.SEARCH_K == before  # the valid search_k=7 in the last body was not applied either


def test_ask_stream_ends_with_what_ask_returns(client, monkeypatch):
    import json
    monkeypatch.delenv("PROCINTEL_LLM_MODEL", raising=False)
    q = {"question": "Why were contracts terminated?"}
    res = client.post("/ask/stream", json=q)
    assert res.headers["content-type"].startswith("text/event-stream") and "no-transform" in res.headers["cache-control"]
    events = [json.loads(b[len("data: "):]) for b in res.text.split("\n\n") if b.startswith("data: ")]
    assert events[0]["type"] == "stage" and events[-1]["type"] == "done"
    plain = client.post("/ask", json=q).json()
    done = events[-1]["result"]
    assert done["answer"] == plain["answer"] and done["citations"] == plain["citations"] and done["meta"]["responseId"]


def test_assess_without_precedents_gives_the_same_forecast_and_no_passages(client, monkeypatch):
    from procintel.core import llm

    def no_model(*a, **kw):
        raise AssertionError("the model must not be called")
    monkeypatch.setattr(llm, "complete", no_model)
    body = {"countryCode": "KE", "procGroup": "CW", "methodCode": "RFB"}
    r = client.post("/assess", json={**body, "withPrecedents": False}).json()
    assert r["precedents"] == [] and (r["timeline"]["n"], r["timeline"]["median"]) == (215, 112.0)
    assert r["risks"] and r["prediction"] is not None


def test_summarize_compacts_a_conversation(client, monkeypatch):
    from procintel.core import llm
    monkeypatch.setattr(llm, "available", lambda *a, **k: True)
    seen = {}

    def fake(system, user, **k):
        seen["user"] = user
        return "Roads project in Kenya, 5 million, supervision after the works."
    monkeypatch.setattr(llm, "complete", fake)
    r = client.post("/assistant/summarize", json={"messages": [{"role": "user", "content": "Plan roads in Kenya, 5 million"},
                                                               {"role": "assistant", "content": "Got it."}]}).json()
    assert r["summary"].startswith("Roads project") and "Planner: Plan roads in Kenya" in seen["user"]
