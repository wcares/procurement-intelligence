from datetime import timedelta

from procintel.jobs import handlers, store, worker


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_store_dedupes_retries_and_recovers(tmp_path):
    db = tmp_path / "jobs.duckdb"
    a = store.enqueue("drift_check", "test", db_path=db)
    assert a and store.enqueue("drift_check", "again", db_path=db) is None        # one pending per kind
    job = store.next_pending(db)
    assert job["id"] == a and job["status"] == "running" and store.next_pending(db) is None
    assert store.recover(db) == 1 and store.next_pending(db)["id"] == a              # a stopped backend's job resumes
    for _ in range(store.MAX_ATTEMPTS):
        store.fail(a, "boom", db)
    [j] = store.recent(db_path=db)
    assert j["status"] == "failed" and j["attempts"] == store.MAX_ATTEMPTS and j["error"] == "boom"
    assert store.due("drift_check", timedelta(days=1), db)                          # never done -> due


def test_a_request_during_a_job_pauses_it_and_it_resumes_from_its_cursor(tmp_path, monkeypatch):
    db = tmp_path / "jobs.duckdb"
    clock = Clock()
    activity = worker.Activity(clock)
    seen = []

    def three_steps(params, cursor, ctx):
        start = (cursor or {}).get("done", 0)
        seen.append(start)
        for i in range(start, 3):
            if i == 1 and ctx.get("interrupt"):
                ctx["interrupt"] = False
                clock.t += 1
                activity.touch()                         # a user request arrives during step 2
            yield {"done": i + 1}
        return {"steps": 3}
    monkeypatch.setitem(handlers.REGISTRY, "test_job", three_steps)
    store.enqueue("test_job", "test", db_path=db)
    ctx = {"interrupt": True}
    assert worker.run_one(store.next_pending(db), activity, ctx, db) == "pending"
    [j] = store.recent(db_path=db)
    assert j["status"] == "pending" and j["cursor"] == {"done": 2}
    assert worker.run_one(store.next_pending(db), activity, ctx, db) == "done"
    [j] = store.recent(db_path=db)
    assert j["result"] == {"steps": 3} and seen == [0, 2]                          # resumed at step 3, not from scratch


def test_worker_waits_for_idle_time_and_queues_the_daily_drift_check(tmp_path, monkeypatch):
    db = tmp_path / "jobs.duckdb"
    clock = Clock()
    monkeypatch.setattr(worker, "SCHEDULE", {"drift_check": timedelta(days=1)})
    ran = []
    monkeypatch.setitem(handlers.REGISTRY, "drift_check", lambda p, c, ctx: (ran.append(1), (yield {"step": 1}))[1])
    w = worker.Worker(worker.Activity(clock), {}, db)
    assert w.tick() is None and ran == []                                           # queued, but the app is busy
    assert [j["kind"] for j in store.recent(db_path=db)] == ["drift_check"]
    clock.t += worker.IDLE_SECONDS
    assert w.tick() == "done" and ran == [1]
    assert w.tick() is None                                                          # done today: not queued again


def test_drift_decision():
    assert handlers.drift_decision(1000, 60, None, 80)[0]                            # 6% new packages: retrain
    assert not handlers.drift_decision(1000, 30, 85, 80)[0]                         # few new, error close to CV
    assert handlers.drift_decision(1000, 30, 120, 80)[0]                            # few new, but much worse
    assert not handlers.drift_decision(1000, 10, 300, 80)[0]                        # too few to judge


def test_a_failed_refresh_fails_the_job_without_stopping_the_worker(tmp_path, monkeypatch):
    from procintel import refresh
    db = tmp_path / "jobs.duckdb"
    monkeypatch.setattr(refresh, "run", lambda **kw: (_ for _ in ()).throw(SystemExit(1)))
    store.enqueue("refresh", "test", db_path=db)
    assert worker.run_one(store.next_pending(db), worker.Activity(Clock()), {}, db) == "pending"   # retried later
    [j] = store.recent(db_path=db)
    assert "refresh failed" in j["error"] and j["attempts"] == 1
