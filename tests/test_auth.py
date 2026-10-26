import pytest
from fastapi.testclient import TestClient

from procintel.auth import passwords, service, store


@pytest.fixture
def local(monkeypatch, tmp_path):
    from procintel.core import paths
    monkeypatch.setenv("PROCINTEL_AUTH", "local")
    monkeypatch.setenv("PROCINTEL_COOKIE_SECURE", "0")   # the test client speaks plain http
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)       # the pseudonym salt
    service.create_user("ana", "planner-pass-1", "planner")
    service.create_user("root", "admin-pass-12", "admin")
    from procintel.api.app import app
    return app


def client(app, ip="127.0.0.1"):
    return TestClient(app, client=(ip, 5000))


def test_passwords_are_salted_hashes():
    a, b = passwords.hash_password("same password"), passwords.hash_password("same password")
    assert a != b and "same password" not in a
    assert passwords.verify("same password", a) and not passwords.verify("other", a)
    assert passwords.check_strength("short") and passwords.check_strength("long enough pw") is None


def test_roles_are_enforced_in_the_backend(local):
    anon, planner, admin = client(local), client(local), client(local)
    assert anon.get("/auth/me").status_code == 401
    assert anon.post("/config/compare", json={"values": {}}).status_code == 401           # admin endpoint, no session
    assert planner.post("/auth/login", json={"username": "ana", "password": "planner-pass-1"}).json()["role"] == "planner"
    assert planner.get("/auth/me").json()["username"] == "ana"
    for method, path in [("get", "/config"), ("get", "/jobs"), ("get", "/pipeline"), ("get", "/prompts"),
                         ("get", "/feedback/review"), ("get", "/auth/users"), ("get", "/shadows")]:
        assert getattr(planner, method)(path).status_code == 403, path                      # planner: not admin
    assert admin.post("/auth/login", json={"username": "root", "password": "admin-pass-12"}).status_code == 200
    assert admin.get("/auth/users").status_code == 200 and admin.get("/jobs").status_code == 200
    assert planner.post("/auth/logout").status_code == 200 and planner.get("/auth/me").status_code == 401


def test_failed_logins_are_throttled_and_do_not_reveal_names(local):
    c = client(local, "10.1.1.1")
    for _ in range(service.MAX_FAILURES):
        r = c.post("/auth/login", json={"username": "ana", "password": "wrong"})
        assert r.status_code == 401 and r.json()["error"] == "wrong username or password"
    r = c.post("/auth/login", json={"username": "ana", "password": "planner-pass-1"})
    assert r.status_code == 429                                                             # even the right password
    other = client(local, "10.2.2.2").post("/auth/login", json={"username": "nobody", "password": "x"})
    assert other.json()["error"] == "wrong username or password"                           # same answer for unknown


def test_admin_manages_accounts_and_changes_end_sessions(local):
    admin, ana = client(local), client(local)
    admin.post("/auth/login", json={"username": "root", "password": "admin-pass-12"})
    ana.post("/auth/login", json={"username": "ana", "password": "planner-pass-1"})
    assert admin.post("/auth/users", json={"username": "bo", "password": "short", "role": "planner"}).status_code == 400
    assert admin.post("/auth/users", json={"username": "bo", "password": "long enough pw"}).status_code == 200
    assert admin.patch("/auth/users/ana", json={"active": False}).status_code == 200
    assert ana.get("/auth/me").status_code == 401                                          # disabled: signed out
    assert admin.patch("/auth/users/root", json={"role": "planner"}).status_code == 400    # not your own admin role
    assert [u["username"] for u in admin.get("/auth/users").json()["users"]] == ["ana", "bo", "root"]


def test_first_admin_from_the_environment_and_pseudonyms(local, monkeypatch, tmp_path):
    from procintel.core import paths
    monkeypatch.setattr(paths, "AUTH_DB", tmp_path / "fresh.duckdb")
    monkeypatch.setenv("PROCINTEL_ADMIN_USER", "first")
    monkeypatch.setenv("PROCINTEL_ADMIN_PASSWORD", "first-admin-pw")
    assert service.ensure_first_admin() == "first" and service.ensure_first_admin() is None
    assert store.get_user("first")["role"] == "admin"
    p = service.pseudonym("ana")
    assert p == service.pseudonym("ana") and p != service.pseudonym("bo") and "ana" not in p and len(p) == 16


def test_sign_in_off_means_everyone_is_admin(monkeypatch):
    from procintel.api.app import app
    monkeypatch.setenv("PROCINTEL_AUTH", "off")
    assert client(app).get("/auth/me").json()["role"] == "admin"


def test_reviewer_labels_and_reviews_but_has_no_pipeline_control(local):
    service.create_user("rae", "reviewer-pass-1", "reviewer")
    rae = client(local)
    assert rae.post("/auth/login", json={"username": "rae", "password": "reviewer-pass-1"}).json()["role"] == "reviewer"
    for path in ["/evaluation/labelling", "/feedback/review"]:
        assert rae.get(path).status_code != 403, path                                       # reviewer work
    assert rae.get("/dashboard").status_code != 403                                         # and the planner app
    assert rae.post("/evaluation/run", json={"answers": False}).status_code == 403          # starting runs: admin
    for method, path in [("get", "/config"), ("get", "/jobs"), ("get", "/pipeline"), ("get", "/prompts"),
                         ("get", "/shadows"), ("get", "/auth/users")]:
        assert getattr(rae, method)(path).status_code == 403, path
    ana = client(local)
    ana.post("/auth/login", json={"username": "ana", "password": "planner-pass-1"})
    assert ana.get("/evaluation/labelling").status_code == 403                              # planner: not a reviewer
    root = client(local)
    root.post("/auth/login", json={"username": "root", "password": "admin-pass-12"})
    assert root.patch("/auth/users/root", json={"role": "reviewer"}).status_code == 400     # not your own admin role
    r = root.patch("/auth/users/ana", json={"role": "reviewer"})
    assert r.status_code == 200, r.json()
