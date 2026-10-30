"""Background worker that drains the job queue without getting in a user's way.

Every user request marks activity (Activity.touch, called from the backend's middleware). The worker checks every
POLL_SECONDS. Jobs that use neither the answer nor the embedding model (LIGHT: change detection, drift check, retention,
retraining) run at once, in priority order, and a request does not pause them. The others wait until IDLE_SECONDS have
passed without a request, then run step by step; between steps it checks whether a request arrived since the job started and,
if so, pauses the job (back to pending with its cursor) until the next idle period. So that a busy day cannot keep a job waiting
forever, one that has waited MAX_WAIT_SECONDS (background jobs: BACKGROUND_WAIT times as long) runs anyway and is not paused. A step itself is not interrupted (a refresh is one step of about
3 minutes with fetching), so a request arriving during a step waits for it to end.

The heavy work shares the machine (and the single local LLM slot) with live requests, which is why idle time, not a
clock time, decides when it runs. A drift check is queued daily and a refresh weekly.

Two ways to run it (PROCINTEL_JOBS):
  1 (default)  a thread inside the backend; it sees requests directly and reloads the backend itself
  external     separate worker processes, `python -m procintel.jobs.worker` (any number; needs Postgres, since a
               DuckDB file allows one writing process). The backend records the time of the last request in the
               shared store and reloads when a worker raises the data version.
  0            no worker
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from procintel.core import llm
from procintel.jobs import handlers, store

log = logging.getLogger(__name__)
IDLE_SECONDS = 300  # tunable on the Settings page
# Jobs that use neither the answer model nor the embedding model never compete with a user's request, so they do not wait for
# quiet (and are not paused by a request); the rest wait for IDLE_SECONDS without a request.
LIGHT = {"detect_changes", "drift_check", "retention", "retrain"}
# Busy all day means quiet never comes: a job that has waited this long runs anyway (background jobs: BACKGROUND_WAIT times as long).
MAX_WAIT_SECONDS = 3600  # tunable on the Settings page
BACKGROUND_WAIT = 12
POLL_SECONDS = 10
# queued automatically, and how often (detect_changes: procintel.pipeline; the weekly refresh reconciles)
SCHEDULE = {"drift_check": timedelta(days=1), "refresh": timedelta(days=7), "detect_changes": timedelta(hours=1),
            "retention": timedelta(days=1)}


def _only_when_busy(now=None) -> str:
    """The condition for a job that may start while users are active: a light one, or one that has waited past its limit."""
    now = now or store._now()
    cut = (now - timedelta(seconds=MAX_WAIT_SECONDS)).isoformat(sep=" ")
    cut_background = (now - timedelta(seconds=MAX_WAIT_SECONDS * BACKGROUND_WAIT)).isoformat(sep=" ")
    kinds = ", ".join(f"'{k}'" for k in sorted(LIGHT))
    return (f"AND (kind IN ({kinds}) OR (coalesce(priority, 1) < 2 AND created_at < '{cut}') "
            f"OR (coalesce(priority, 1) >= 2 AND created_at < '{cut_background}'))")


def _overdue(job: dict, now=None) -> bool:
    created = job.get("created_at")   # a time or its ISO text, as the store returns it
    if isinstance(created, str):
        created = datetime.fromisoformat(created.rstrip("Z"))
    waited = ((now or store._now()) - created).total_seconds() if created else 0
    return waited >= MAX_WAIT_SECONDS * (BACKGROUND_WAIT if (job.get("priority") or 1) >= 2 else 1)


class Activity:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.last = clock()

    def touch(self) -> None:
        self.last = self.clock()

    def idle_for(self) -> float:
        return self.clock() - self.last


class SharedActivity:
    """Activity read from the shared job store, for a worker in its own process: `last` is the last request's time."""

    def __init__(self, db_path=None):
        self.db_path = db_path

    def _last(self) -> float | None:
        t = store.last_activity(self.db_path)  # naive UTC, as every time in the store
        return t.replace(tzinfo=timezone.utc).timestamp() if t else None

    @property
    def last(self) -> float:
        return self._last() or 0.0

    def idle_for(self) -> float:
        last = self._last()
        return float("inf") if last is None else time.time() - last


class ActivityPublisher:
    """In the backend when workers run separately: records request times in the shared store, at most every
    `every` seconds, so a busy app costs one write per interval."""

    def __init__(self, every: float = 10.0, clock: Callable[[], float] = time.monotonic, db_path=None):
        self.every, self.clock, self.db_path, self._sent = every, clock, db_path, None

    def touch(self) -> None:
        now = self.clock()
        if self._sent is None or now - self._sent >= self.every:
            self._sent = now
            try:
                store.touch_activity(self.db_path)
            except Exception:  # noqa: BLE001 - a busy store must not fail the user's request
                log.exception("jobs: could not record activity")


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


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
            # a request came in during the step, or a more urgent job is waiting: give the machine back
            # light and overdue jobs, and every job when the batch model is its own, are not paused by requests
            yields = job["kind"] not in LIGHT and not _overdue(job) and not llm.batch_dedicated()
            if (yields and activity.last != started) or store.higher_waiting(job.get("priority"), db_path):
                store.pause(job["id"], db_path)
                return "pending"
    except StopIteration as done:
        store.finish(job["id"], done.value or {}, db_path)
        return "done"
    except Exception as e:  # noqa: BLE001 - a failing job must not stop the worker; it is retried, then failed
        log.exception("job %s (%s) failed", job["id"], job["kind"])
        return store.fail(job["id"], f"{type(e).__name__}: {e}", db_path)


class Worker:
    def __init__(self, activity, ctx: dict[str, Any], db_path=None, name: str = "local", shared: bool = False):
        self.activity, self.ctx, self.db_path, self.name, self.shared = activity, ctx, db_path, name, shared
        self._stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.current: str | None = None

    def tick(self) -> str | None:
        """One poll: queue due periodic jobs, then run a pending job: any when the app has been idle long enough, otherwise only
        a light one or one that has waited past its limit."""
        for kind, every in SCHEDULE.items():
            if store.due(kind, every, self.db_path):
                store.enqueue(kind, f"scheduled: every {every}", db_path=self.db_path)
        idle = self.activity.idle_for() >= IDLE_SECONDS or llm.batch_dedicated()   # a model of their own: no need to wait for users
        job = store.next_pending(self.db_path, self.name, "" if idle else _only_when_busy())
        if job is None:
            return None
        self.current = job["kind"]
        try:
            with llm.use_batch():   # the job's model calls go to the batch model, where one is set
                return run_one(job, self.activity, self.ctx, self.db_path)
        finally:
            self.current = None

    def start(self) -> None:
        n = store.recover(self.db_path, stale_only=self.shared)
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


def main() -> None:
    """A worker in its own process (PROCINTEL_JOBS=external in the backend)."""
    from procintel.api import config
    from procintel.core import db
    global IDLE_SECONDS
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if db.backend() != "postgres":
        raise SystemExit("a separate worker needs PROCINTEL_DB_URL (Postgres): a DuckDB file allows one writing process")
    for key, err in config.load_saved().items():  # settings saved on the Settings page (read at start)
        log.warning("config: saved value for %s ignored: %s", key, err)
    IDLE_SECONDS = int(os.environ.get("PROCINTEL_JOBS_IDLE_SECONDS", IDLE_SECONDS))
    w = Worker(SharedActivity(), {"reload": store.bump_version}, name=worker_id(), shared=True)
    w.start()
    log.info("jobs: worker %s running (idle after %ss)", w.name, IDLE_SECONDS)
    try:
        while w.thread and w.thread.is_alive():
            w.thread.join(1)
    except KeyboardInterrupt:
        w.stop()


if __name__ == "__main__":
    main()
