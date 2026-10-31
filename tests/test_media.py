from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from procintel.core import paths
from procintel.intake import media


def _client(tmp_path, monkeypatch, user=None):
    from procintel.api.routes import media as route
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(paths, "PIPELINE_DB", tmp_path / "pipeline.duckdb")
    monkeypatch.setattr(media, "known_project", lambda pid: pid == "P1")
    app = FastAPI()

    @app.middleware("http")
    async def as_user(request: Request, call_next):
        request.state.user = user
        return await call_next(request)

    app.include_router(route.router)
    return TestClient(app)


def test_a_photo_is_attached_to_a_project_listed_and_served(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, {"username": "ana", "role": "planner"})
    r = c.post("/media", files={"file": ("site.jpg", b"\xff\xd8 jpeg bytes", "image/jpeg")},
               data={"projectId": "P1", "packageRef": "KE-RD-01", "caption": "Bridge deck", "takenOn": "2026-09-14"})
    item = r.json()
    assert r.status_code == 200 and item["kind"] == "image" and item["packageRef"] == "KE-RD-01" and not item["synthetic"]
    listed = c.get("/media", params={"projectIds": "P1,P2"}).json()["items"]
    assert [m["id"] for m in listed] == [item["id"]] and listed[0]["takenOn"] == "2026-09-14"
    f = c.get(item["url"])
    assert f.content == b"\xff\xd8 jpeg bytes" and f.headers["content-type"] == "image/jpeg"
    part = c.get(item["url"], headers={"Range": "bytes=3-6"})
    assert part.status_code == 206 and part.content == b"jpeg" and part.headers["content-range"] == "bytes 3-6/13"
    assert c.delete(f"/media/{item['id']}").json() == {"removed": item["id"]}
    assert c.get(item["url"]).status_code == 404


def test_uploads_are_refused_for_an_unknown_project_a_bad_type_or_a_bad_date(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    send = lambda name, **data: c.post("/media", files={"file": (name, b"x", "application/octet-stream")},
                                       data={"projectId": "P1", **data})
    assert send("notes.exe").status_code == 400
    assert send("a.png", projectId="P9").status_code == 400
    assert send("a.png", takenOn="yesterday").status_code == 400
    assert c.get("/media/../../etc/file").status_code == 404


def test_only_the_uploader_or_an_admin_removes_media(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, {"username": "ana", "role": "planner"})
    item = media.save("v.mp4", b"video", "P1", "not-ana")
    assert item["kind"] == "video"
    assert c.delete(f"/media/{item['id']}").status_code == 404
    admin = _client(tmp_path, monkeypatch, {"username": "boss", "role": "admin"})
    assert admin.delete(f"/media/{item['id']}").status_code == 200
