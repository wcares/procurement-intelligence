from fastapi.testclient import TestClient

from procintel.api import server


def test_reload_swaps_state_and_is_refused_from_other_hosts(monkeypatch):
    built = []

    class Fake:
        def __init__(self, db_path):
            built.append(db_path)
            self.retriever = type("R", (), {"records": [1, 2, 3]})()
    monkeypatch.setattr(server, "State", Fake)
    monkeypatch.setattr(server, "_state", None)
    first = server.state()
    assert server.state() is first and len(built) == 1             # built once, then reused
    server.reload_state()
    assert server.state() is not first and len(built) == 2         # rebuilt and swapped
    remote = TestClient(server.app, client=("10.0.0.5", 5000))
    assert remote.post("/admin/reload").status_code == 403
    local = TestClient(server.app, client=("127.0.0.1", 5000))
    r = local.post("/admin/reload")
    assert r.status_code == 200 and r.json()["passages"] == 3 and len(built) == 3
