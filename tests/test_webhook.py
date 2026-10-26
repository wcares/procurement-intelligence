import hashlib
import hmac
import json
from datetime import timedelta

from fastapi.testclient import TestClient

from procintel.core import paths
from procintel.jobs import store as jobs_store
from procintel.pipeline import connector_config, entities, store

SECRET = "test-webhook-secret"


def _setup(tmp_path, monkeypatch, mode="push"):
    monkeypatch.setattr(paths, "PIPELINE_DB", tmp_path / "pipeline.duckdb")
    monkeypatch.setattr(jobs_store, "DB_PATH", tmp_path / "jobs.duckdb")
    et = entities.EntityType("Notice", timedelta(hours=1), ["award_date"], lambda ctx: ({}, False),
                             lambda: {"n1": {"notice_id": "n1", "award_date": None}}, "src", key=lambda r: r["notice_id"])
    monkeypatch.setattr(entities, "ENTITY_TYPES", {"Notice": et})
    store.seed("Notice", ["award_date"], {"n1": {"notice_id": "n1", "award_date": None}})
    monkeypatch.setenv("PROCINTEL_WEBHOOK_SECRET_NOTICE", SECRET)
    connector_config.save("Notice", {"mode": mode})
    from procintel.api.app import app
    return TestClient(app)


def _post(c, body: dict, secret=SECRET, name="Notice"):
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return c.post(f"/connectors/{name}/webhook", content=raw, headers={"X-Signature": sig, "Content-Type": "application/json"})


def test_a_signed_push_records_changes_and_queues_them_at_high_priority(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch)
    r = _post(c, {"items": [{"notice_id": "n1", "award_date": "2026-10-01"}, {"notice_id": "n2", "award_date": None}]})
    assert r.status_code == 200 and r.json()["events"] == 2 and r.json()["job"]
    assert sorted(e["type"] for e in store.batch_events(r.json()["batch"])) == ["Notice.added", "Notice.changed"]
    job = jobs_store.next_pending()
    assert job["kind"] == "pipeline_batch" and job["priority"] == 0
    again = _post(c, {"items": [{"notice_id": "n1", "award_date": "2026-10-01"}]})   # nothing new: no batch work
    assert again.json()["events"] == 0 and again.json()["job"] is None


def test_unsigned_wrongly_signed_or_unconfigured_pushes_are_refused(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch)
    body = {"items": [{"notice_id": "n9"}]}
    assert _post(c, body, secret="wrong").status_code == 401
    assert c.post("/connectors/Notice/webhook", json=body).status_code == 401            # no signature
    assert _post(c, body, name="Nope").status_code == 404
    assert _post(c, {"items": []}).status_code == 400 and _post(c, {"items": [{"x": 1}]}).status_code == 400
    monkeypatch.delenv("PROCINTEL_WEBHOOK_SECRET_NOTICE")
    assert _post(c, body).status_code == 403                                             # push not set up
    monkeypatch.setenv("PROCINTEL_WEBHOOK_SECRET_NOTICE", SECRET)
    connector_config.save("Notice", {"mode": "poll"})
    assert _post(c, body).status_code == 409                                             # not in push mode
    assert store.states("Notice").keys() == {"n1"}                                       # nothing was recorded
