from datetime import timedelta

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from procintel.core import paths
from procintel.reports import shares


def _client(tmp_path, monkeypatch, user):
    from procintel.api.routes import shares as route
    monkeypatch.setattr(paths, "PIPELINE_DB", tmp_path / "p.duckdb")
    app = FastAPI()

    @app.middleware("http")
    async def as_user(request: Request, call_next):
        request.state.user = user
        return await call_next(request)

    app.include_router(route.router)
    return TestClient(app)


def test_a_shared_plan_opens_by_its_link_until_it_expires(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, {"username": "ana", "role": "planner"})
    made = c.post("/shares", json={"kind": "plan", "body": {"packages": [{"id": "a"}]}}).json()
    got = c.get(f"/shares/{made['id']}").json()
    assert got["kind"] == "plan" and got["body"] == {"packages": [{"id": "a"}]} and got["createdBy"] == "ana"
    assert c.post("/shares", json={"kind": "nope", "body": {}}).status_code == 400
    assert c.get("/shares/not-a-real-link-id").status_code == 404
    monkeypatch.setattr(shares, "_now", lambda: shares.datetime.now(shares.timezone.utc).replace(tzinfo=None) + timedelta(days=8))
    assert c.get(f"/shares/{made['id']}").status_code == 404                         # expired after 7 days


def test_only_the_creator_or_an_admin_deletes_a_link(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, {"username": "ana", "role": "planner"})
    sid = c.post("/shares", json={"kind": "assessment", "body": {"response": {}}}).json()["id"]
    other = _client(tmp_path, monkeypatch, {"username": "bo", "role": "planner"})
    assert other.delete(f"/shares/{sid}").status_code == 404
    assert c.delete(f"/shares/{sid}").json() == {"deleted": sid}
    assert c.get(f"/shares/{sid}").status_code == 404


def test_the_creator_edits_the_plan_behind_the_same_link(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, {"username": "ana", "role": "planner"})
    sid = c.post("/shares", json={"kind": "plan", "body": {"packages": [{"id": "a"}]}}).json()["id"]
    assert c.put(f"/shares/{sid}", json={"body": {"packages": [{"id": "a"}, {"id": "b"}]}}).json()["body"]["packages"][1]["id"] == "b"
    assert c.get(f"/shares/{sid}").json()["body"]["packages"][1]["id"] == "b"
    other = _client(tmp_path, monkeypatch, {"username": "bo", "role": "planner"})
    assert other.put(f"/shares/{sid}", json={"body": {}}).status_code == 404
