import json
from datetime import datetime

from fastapi.testclient import TestClient

from procintel.core import paths, prompts
from procintel.jobs import store as jobs_store
from procintel.learning import evaluate, overview, shadows
from procintel.prediction import predict


def _setup(tmp_path, monkeypatch, bundle=None):
    hist = tmp_path / "history.jsonl"
    hist.write_text("\n".join(json.dumps(r) for r in [
        {"time": "2026-10-25 09:00 UTC", "hybrid_p5": 0.70, "judged_pairs": 100},
        {"time": "2026-10-25 10:00 UTC", "hybrid_p5": 0.70, "judged_pairs": 200},
        {"time": "2026-10-25 12:00 UTC", "hybrid_p5": 0.75, "judged_pairs": 200}]))
    (tmp_path / "history-other-model.jsonl").write_text(json.dumps({"time": "2026-10-25 11:00 UTC", "hybrid_p5": 0.6,
                                                                    "judged_pairs": 100}))
    monkeypatch.setattr(evaluate, "HISTORY", hist)
    monkeypatch.setattr(paths, "EVAL_DIR", tmp_path)
    monkeypatch.setattr(predict, "MODEL_HISTORY", tmp_path / "models.jsonl")
    monkeypatch.setattr(predict, "load", lambda path=None: bundle)
    monkeypatch.setattr(prompts, "listing", lambda: [{"name": "answer", "label": "Answer writer", "active": 0, "versions": [
        {"version": 0, "active": True, "activated": None, "evaluation": None},
        {"version": 1, "active": False, "activated": None, "note": "shorter", "evaluation": {"active": 0.9, "candidate": 0.9}}]}])
    monkeypatch.setattr(shadows, "states", lambda: [])
    db = tmp_path / "jobs.duckdb"
    monkeypatch.setattr(jobs_store, "DB_PATH", db)
    jid = jobs_store.enqueue("refresh", "weekly")
    jobs_store.finish(jid, {"changes": {}})
    con = jobs_store._connect(None)
    con.execute("UPDATE jobs SET finished_at = ? WHERE id = ?", [datetime(2026, 10, 25, 11, 30), jid])
    con.close()


def test_runs_carry_the_changes_made_since_the_run_before(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    q = overview.quality()
    assert [r["hybrid_p5"] for r in q] == [0.70, 0.70, 0.75]
    assert q[0]["changesBefore"] == [] and [c["what"] for c in q[2]["changesBefore"]] == ["data refresh"]
    assert q[1]["changesBefore"] == [{"at": "2026-10-25T10:00:00Z", "what": "evaluation set changed",
                                      "detail": "judged passages: 100 → 200"}]
    m = overview.other_model_runs()
    assert m[0]["name"] == "other-model" and m[0]["live"]["time"] == "2026-10-25 09:00 UTC"   # same questions, before it
    c = overview.comparisons()
    assert [(p["name"], p["version"]) for p in c["prompts"]] == [("answer", 1)]                  # candidates only


def test_model_history_comes_from_the_file_then_the_saved_model(tmp_path, monkeypatch):
    bundle = {"trained_at": "2026-10-25T16:32:46+00:00", "use": {"days_p50": True},
              "metrics": {"n": 100, "projects": 9, "folds": 5, "days_p50_mae": (70.0, 80.0)}}
    _setup(tmp_path, monkeypatch, bundle)
    rows = overview.models()["retrains"]
    assert rows == [{"trained_at": "2026-10-25T16:32:46+00:00", "n": 100, "projects": 9, "folds": 5,
                     "metrics": {"days_p50_mae": [70.0, 80.0]}, "use": {"days_p50": True}, "source": "the saved model"}]
    predict.record(bundle, predict.MODEL_HISTORY)                  # once recorded, it is not listed twice
    assert len(overview.models()["retrains"]) == 1 and "source" not in overview.models()["retrains"][0]


def test_evaluation_endpoints(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    from procintel.api.app import app
    c = TestClient(app, client=("127.0.0.1", 5000))
    assert len(c.get("/evaluation").json()["quality"]) == 3
    r = c.post("/evaluation/run", json={"answers": False}).json()
    job = jobs_store.next_pending()
    assert r["queued"] == job["id"] and job["kind"] == "evaluate" and job["params"] == {"answers": False}
    assert job["priority"] == 2                                     # background
