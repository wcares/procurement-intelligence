import pytest
from fastapi.testclient import TestClient

from procintel.auth import passwords, service, store


@pytest.fixture
def local(monkeypatch, tmp_path):
    from procintel.core import paths
    monkeypatch.setenv("PROCINTEL_AUTH", "local")
    monkeypatch.setenv("PROCINTEL_COOKIE_SECURE", "0")   # the test client speaks plain http
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)       # the pseudonym salt
    monkeypatch.setattr(service, "_requests", {})          # sign-up counts per client
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


def test_the_quality_page_is_for_admins(local):
    ana, root = client(local), client(local)
    ana.post("/auth/login", json={"username": "ana", "password": "planner-pass-1"})
    for path in ["/evaluation/labelling", "/feedback/review"]:
        assert ana.get(path).status_code == 403, path                                       # planner: not admin
    root.post("/auth/login", json={"username": "root", "password": "admin-pass-12"})
    for path in ["/evaluation/labelling", "/feedback/review"]:
        assert root.get(path).status_code != 403, path
    assert root.patch("/auth/users/ana", json={"role": "reviewer"}).status_code == 400      # the role was dropped
    assert root.patch("/auth/users/root", json={"role": "planner"}).status_code == 400      # not your own admin role


def test_reviewer_accounts_become_planners(local):
    store.add_user("rae", passwords.hash_password("reviewer-pass-1"), "reviewer")          # an account from before
    assert store.drop_retired_roles() == 1 and store.drop_retired_roles() == 0
    assert store.get_user("rae")["role"] == "planner"


def test_sign_up_waits_for_an_admin(local):
    anon, admin = client(local, "10.0.0.7"), client(local)
    assert anon.post("/auth/signup", json={"username": "ben", "password": "ben-pass-123", "role": "admin"}).json() == {"ok": True}
    refused = anon.post("/auth/login", json={"username": "ben", "password": "ben-pass-123"})
    assert refused.status_code == 401 and "waiting" in refused.json()["error"]
    wrong = anon.post("/auth/login", json={"username": "ben", "password": "not-his-pass"})
    assert wrong.json()["error"] == "wrong username or password"       # only the right password learns it is pending
    admin.post("/auth/login", json={"username": "root", "password": "admin-pass-12"})
    ben = next(u for u in admin.get("/auth/users").json()["users"] if u["username"] == "ben")
    assert ben["role"] == "planner" and not ben["active"] and ben["requestedAt"]   # a request never asks for a role
    ben = next(u for u in admin.patch("/auth/users/ben", json={"active": True}).json()["users"] if u["username"] == "ben")
    assert ben["active"] and ben["requestedAt"] is None
    assert anon.post("/auth/login", json={"username": "ben", "password": "ben-pass-123", "portal": "planner"}).json()["role"] == "planner"


def test_sign_up_checks_and_limits(local):
    anon = client(local, "10.0.0.8")
    assert "exists" in anon.post("/auth/signup", json={"username": "ana", "password": "another-pass-1"}).json()["error"]
    assert "password" in anon.post("/auth/signup", json={"username": "cy", "password": "short"}).json()["error"]
    for name in ("u1", "u2", "u3"):
        assert anon.post("/auth/signup", json={"username": name, "password": "long-enough-1"}).status_code == 200
    assert anon.post("/auth/signup", json={"username": "u4", "password": "long-enough-1"}).status_code == 429
    assert client(local, "10.0.0.9").post("/auth/signup", json={"username": "u4", "password": "long-enough-1"}).status_code == 200


def test_declining_a_request_removes_it(local):
    admin = client(local)
    client(local, "10.0.0.10").post("/auth/signup", json={"username": "dee", "password": "dee-pass-123"})
    admin.post("/auth/login", json={"username": "root", "password": "admin-pass-12"})
    assert "dee" not in [u["username"] for u in admin.delete("/auth/users/dee").json()["users"]]
    assert client(local).delete("/auth/users/ana").status_code == 401


def test_removing_an_account_leaves_nothing_for_a_later_one(local, monkeypatch, tmp_path):
    from procintel.core import paths
    monkeypatch.setattr(paths, "FEEDBACK_DB", tmp_path / "feedback.duckdb")     # saved conversations
    monkeypatch.setattr(paths, "PIPELINE_DB", tmp_path / "pipeline.duckdb")     # watch-lists and alerts
    ana, admin = client(local), client(local)
    ana.post("/auth/login", json={"username": "ana", "password": "planner-pass-1"})
    assert ana.put("/conversations/conv-0001", json={"kind": "plan", "messages": [{"role": "user", "content": "hi"}]}).status_code == 200
    assert ana.put("/insights/watch", json={"watch": {"country": ["KE"]}}).status_code == 200
    admin.post("/auth/login", json={"username": "root", "password": "admin-pass-12"})
    assert admin.delete("/auth/users/root").status_code == 400                # not your own account
    assert admin.delete("/auth/users/nobody").status_code == 404
    assert ana.delete("/auth/users/root").status_code == 403                  # planners cannot remove anyone
    assert "ana" not in [u["username"] for u in admin.delete("/auth/users/ana").json()["users"]]
    assert ana.get("/auth/me").status_code == 401                             # the session ended with the account
    service.create_user("ana", "a-new-pass-12", "planner")                    # someone new with the same name
    ana2 = client(local)
    ana2.post("/auth/login", json={"username": "ana", "password": "a-new-pass-12"})
    assert ana2.get("/conversations?kind=plan").json()["items"] == []
    assert not any(ana2.get("/insights/watch").json()["watch"].values())


def test_each_sign_in_page_admits_its_roles(local):
    for name, pw, portal, ok in [("ana", "planner-pass-1", "admin", False), ("root", "admin-pass-12", "planner", False),
                                 ("ana", "planner-pass-1", "planner", True),
                                 ("root", "admin-pass-12", "admin", True), ("ana", "planner-pass-1", None, True)]:
        c = client(local)
        r = c.post("/auth/login", json={"username": name, "password": pw, "portal": portal})
        assert (r.status_code == 200) == ok, (name, portal)
        assert (c.get("/auth/me").status_code == 200) == ok, (name, portal)    # a refused page sets no session
        if not ok:
            assert "sign-in" in r.json()["error"]

