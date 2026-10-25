import pytest

from procintel.retrieve import DB_PATH

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="needs data/procintel.duckdb (run ingest, model, chunk)")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from procintel.server import app
    with TestClient(app) as c:
        yield c


def test_options(client):
    r = client.get("/options").json()
    assert len(r["countries"]) > 10 and {g["code"] for g in r["procGroups"]} == {"GO", "CW", "CS", "NC"}


def test_assess_matches_known_benchmark(client):
    # Kenya / civil works / RFB: the same numbers the mock UI showed (n=195, median 113)
    r = client.post("/assess", json={"countryCode": "KE", "procGroup": "CW", "methodCode": "RFB"}).json()
    assert (r["timeline"]["n"], r["timeline"]["median"]) == (195, 113)
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


def test_bad_input_is_400(client):
    assert client.post("/assess", json={"countryCode": "KE", "procGroup": "XX", "methodCode": "RFB"}).status_code == 400
    assert client.post("/ask", json={"question": ""}).status_code == 400


@pytest.fixture(autouse=True)
def feedback_db(tmp_path, monkeypatch):
    """Every API test logs responses to a temporary feedback database, never to data/feedback.duckdb."""
    from procintel import feedback
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
