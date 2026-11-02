"""How this API process takes part in background jobs (procintel.jobs), by PROCINTEL_JOBS:

  1 (default)  a worker thread here; it sees requests directly and reloads this process itself
  external     separate worker processes: request times go to the shared store, and this process reloads when a
               worker raises the data version (polled every VERSION_POLL_SECONDS)
  0            no background jobs
"""
from __future__ import annotations

import logging
import os
import threading

from procintel.api.state import reload_state
from procintel.jobs import store, worker

log = logging.getLogger(__name__)
MODE = os.environ.get("PROCINTEL_JOBS", "1")
VERSION_POLL_SECONDS = 15

activity = worker.Activity()
publisher = worker.ActivityPublisher() if MODE == "external" else None
job_worker = worker.Worker(activity, {"reload": lambda: reload_state()})
loaded_version: dict[str, str | None] = {"version": None}  # data version this process has loaded (external mode)
_stop = threading.Event()


def touch() -> None:
    """A user request: postpone background jobs."""
    activity.touch()
    if publisher:
        publisher.touch()


def start() -> None:
    if MODE == "1":
        job_worker.start()
    elif MODE == "external":
        threading.Thread(target=_watch_data_version, name="procintel-data-version", daemon=True).start()
    if MODE != "0":
        from procintel.pipeline import mcp_listen
        try:
            mcp_listen.start()   # MCP servers marked subscribe: followed live (their changes queue reads)
        except Exception as e:   # noqa: BLE001 - a bad MCP configuration must not stop the API
            log.warning("MCP subscriptions not started: %s", e)


def stop() -> None:
    job_worker.stop()
    _stop.set()


def status() -> dict:
    from procintel.core import llm
    return {"idleSeconds": round(activity.idle_for()), "runAfterIdleSeconds": worker.IDLE_SECONDS,
            # background work has a model of its own: no job waits for a quiet app (procintel.jobs.worker.tick)
            "dedicatedModel": llm.batch_dedicated(),
            "running": job_worker.current,
            "workerOn": MODE == "external" or (job_worker.thread is not None and job_worker.thread.is_alive()),
            "workerMode": {"1": "thread", "external": "external"}.get(MODE, "off"),
            "dataVersion": loaded_version["version"]}


def _watch_data_version() -> None:
    loaded_version["version"] = store.data_version()
    while not _stop.wait(VERSION_POLL_SECONDS):
        try:
            v = store.data_version()
            if v != loaded_version["version"]:
                print(f"data version {v}: reloading", flush=True)
                reload_state()
                loaded_version["version"] = v
        except Exception:  # noqa: BLE001 - try again on the next poll
            log.exception("data version check failed")
