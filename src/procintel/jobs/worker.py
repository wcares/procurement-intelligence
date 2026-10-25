"""Background worker that drains the job queue only while nobody is using the app.

Every user request marks activity (Activity.touch, called from the backend's middleware). The worker checks every
POLL_SECONDS; once IDLE_SECONDS have passed without a request it takes the oldest pending job and runs it step by step.
Between steps it checks whether a request arrived since the job started; if so the job is paused (back to pending with
its cursor) and waits for the next idle period. A step itself is not interrupted (a refresh is one step of about
3 minutes with fetching), so a request arriving during a step waits for it to end.

The heavy work shares the machine (and the single local LLM slot) with live requests, which is why idle time, not a
clock time, decides when it runs. A drift check is queued daily and a refresh weekly.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import timedelta
from typing import Any, Callable

from procintel.jobs import handlers, store

log = logging.getLogger(__name__)
IDLE_SECONDS = 300  # tunable on the Settings page
POLL_SECONDS = 10
SCHEDULE = {"drift_check": timedelta(days=1), "refresh": timedelta(days=7)}  # queued automatically, and how often


class Activity:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.last = clock()

    def touch(self) -> None:
        self.last = self.clock()

    def idle_for(self) -> float:
        return self.clock() - self.last


def run_one(job: dict, activity: Activity, ctx: dict, db_path=None) -> str:
    """Run a job until it finishes, fails or a request arrives; returns its new status."""
    started = activity.last
    handler = handlers.REGISTRY.get(job["kind"])
    if handler is None:
        return store.fail(job["id"], f"unknown job kind {job['kind']!r}", db_path)
    gen = handler(job["params"] or {}, job["cursor"], ctx)
    try:
        while True:
            cursor = next(gen)
            store.checkpoint(job["id"], cursor, db_path)
            if activity.last != started:  # a request came in during the step: give the machine back
                store.pause(job["id"], db_path)
                return "pending"
    except StopIteration as done:
        store.finish(job["id"], done.value or {}, db_path)
        return "done"
    except Exception as e:  # noqa: BLE001 - a failing job must not stop the worker; it is retried, then failed
        log.exception("job %s (%s) failed", job["id"], job["kind"])
        return store.fail(job["id"], f"{type(e).__name__}: {e}", db_path)


class Worker:
    def __init__(self, activity: Activity, ctx: dict[str, Any], db_path=None):
        self.activity, self.ctx, self.db_path = activity, ctx, db_path
        self._stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.current: str | None = None

    def tick(self) -> str | None:
        """One poll: queue due periodic jobs, then run a pending job if the app has been idle long enough."""
        for kind, every in SCHEDULE.items():
            if store.due(kind, every, self.db_path):
                store.enqueue(kind, f"scheduled: every {every.days} day(s)", db_path=self.db_path)
        if self.activity.idle_for() < IDLE_SECONDS:
            return None
        job = store.next_pending(self.db_path)
        if job is None:
            return None
        self.current = job["kind"]
        try:
            return run_one(job, self.activity, self.ctx, self.db_path)
        finally:
            self.current = None

    def start(self) -> None:
        n = store.recover(self.db_path)
        if n:
            log.info("jobs: %d interrupted job(s) back to pending", n)

        def loop() -> None:
            while not self._stop.wait(POLL_SECONDS):
                try:
                    self.tick()
                except Exception:  # noqa: BLE001 - e.g. the jobs file is briefly locked by a command-line tool
                    log.exception("jobs: worker tick failed")
        self.thread = threading.Thread(target=loop, name="procintel-jobs", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self._stop.set()
