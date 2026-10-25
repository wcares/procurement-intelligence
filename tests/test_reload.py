from fastapi.testclient import TestClient

from procintel.api import state as api_state
from procintel.api.app import app


def test_reload_swaps_state_and_is_refused_from_other_hosts(monkeypatch):
    built = []

    class Fake:
        def __init__(self, db_path):
            built.append(db_path)
            self.retriever = type("R", (), {"records": [1, 2, 3]})()
    monkeypatch.setattr(api_state, "State", Fake)
    monkeypatch.setattr(api_state, "_state", None)
    first = api_state.state()
    assert api_state.state() is first and len(built) == 1          # built once, then reused
    api_state.reload_state()
    assert api_state.state() is not first and len(built) == 2      # rebuilt and swapped
    remote = TestClient(app, client=("10.0.0.5", 5000))
    assert remote.post("/admin/reload").status_code == 403
    local = TestClient(app, client=("127.0.0.1", 5000))
    r = local.post("/admin/reload")
    assert r.status_code == 200 and r.json()["passages"] == 3 and len(built) == 3


def test_admin_clients_are_a_setting(monkeypatch):
    from procintel.api import access
    monkeypatch.setenv("PROCINTEL_ADMIN_CLIENTS", "172.16.0.0/12")
    req = type("Req", (), {})()
    for host, ok in (("172.18.0.5", True), ("127.0.0.1", False), ("10.0.0.5", False), ("not-an-ip", False)):
        req.client = type("C", (), {"host": host})()
        assert access.is_admin_client(req) is ok, host
