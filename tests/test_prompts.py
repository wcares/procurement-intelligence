import threading

from fastapi.testclient import TestClient

from procintel.core import paths, prompts
from procintel.learning import prompt_eval


def test_versions_activate_and_override_stays_in_its_own_thread(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    default = prompts.get("rephrase")
    assert default.startswith("You turn a planner's question")
    v = prompts.save("rephrase", "Write search queries.\n", note="shorter")
    assert v == 1 and prompts.get("rephrase") == default                     # saved, not active yet
    seen = {}
    with prompts.override("rephrase", 1):
        t = threading.Thread(target=lambda: seen.update(other=prompts.get("rephrase")))
        t.start(); t.join()
        assert prompts.get("rephrase") == "Write search queries."
    assert seen["other"] == default and prompts.get("rephrase") == default    # other threads kept the active one
    prompts.activate("rephrase", 1)
    assert prompts.get("rephrase") == "Write search queries."
    entry = next(p for p in prompts.listing() if p["name"] == "rephrase")
    assert entry["active"] == 1 and [x["version"] for x in entry["versions"]] == [0, 1]
    assert entry["versions"][1]["note"] == "shorter" and entry["versions"][1]["activated"]


def test_placeholders_are_filled_and_json_braces_are_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    assert prompts.get("problem_kind", kinds="a; b").endswith("exactly one of: a; b.")
    assert '{"sentences": []}' in prompts.get("answer")


def test_summary_counts_answers_support_and_refused_traps():
    rows = [{"answerable": True, "answered": True, "sentences": 3, "supported": 2, "seconds": 20.0},
            {"answerable": True, "answered": False, "sentences": 0, "supported": 0, "seconds": 10.0},
            {"answerable": False, "answered": False, "sentences": 0, "supported": 0, "seconds": 5.0}]
    s = prompt_eval.summarise(rows)
    assert (s["answered"], s["answerable"], s["supported_sentences"], s["sentences"], s["refused_traps"], s["traps"]) \
        == (1, 2, 2, 3, 1, 1) and s["median_seconds"] == 10.0


def test_api_saves_a_candidate_queues_its_evaluation_and_activates(tmp_path, monkeypatch):
    from procintel.api.app import app
    from procintel.api.routes import prompts as route
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    queued = []
    monkeypatch.setattr(route.jobs_store, "enqueue", lambda kind, reason, params, dedupe: queued.append((kind, params)) or "j1")
    local = TestClient(app, client=("127.0.0.1", 5000))
    r = local.post("/prompts/answer", json={"text": "Answer briefly.", "note": "t"}).json()
    assert r == {"version": 1, "evaluationJob": "j1"} and queued == [("prompt_evaluate", {"name": "answer", "version": 1})]
    assert local.post("/prompts/precedents", json={"text": "Pick lessons."}).json()["evaluationJob"] is None
    assert local.post("/prompts/answer/activate", json={"version": 7}).status_code == 404
    assert local.post("/prompts/answer/activate", json={"version": 1}).status_code == 200 and prompts.get("answer") == "Answer briefly."
    assert TestClient(app, client=("10.0.0.5", 5000)).post("/prompts/answer", json={"text": "x"}).status_code == 403
    assert local.post("/prompts/nope", json={"text": "x"}).status_code == 404
