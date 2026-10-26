"""Push mode (docs/event-pipeline-design.md 6b): a source posts its new or changed items to
POST /connectors/<name>/webhook instead of being polled.

The request must be signed: header X-Signature = "sha256=" + hex HMAC-SHA256 of the raw body with the connector's secret,
from the environment (PROCINTEL_WEBHOOK_SECRET_<NAME>, e.g. PROCINTEL_WEBHOOK_SECRET_NOTICE; never stored or shown).
No secret set, or the connector not in push mode (procintel.pipeline.connector_config): the push is refused. Body:
{"items": [row, ...]} with the same fields the source's reader returns. The items are compared with the stored state
like a partial read (an item missing from a push is not a removal), the events recorded in a batch of their own, and
the rules' actions queued at high priority. Polling of a pushed source continues daily, to catch pushes lost while the
app was down.
"""
from __future__ import annotations

import hashlib
import hmac
import os

from procintel.pipeline import connector_config, detect, entities, store

MAX_ITEMS = 5000


def secret(name: str) -> str | None:
    return os.environ.get(f"PROCINTEL_WEBHOOK_SECRET_{name.upper()}") or None


def signature_ok(name: str, body: bytes, header: str | None) -> bool:
    key = secret(name)
    if not key or not header or not header.startswith("sha256="):
        return False
    want = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, header.removeprefix("sha256="))


class Refused(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def receive(name: str, body: bytes, header: str | None, payload: dict) -> dict:
    """Record a push; returns the batch, the events per type and the queued job."""
    et = entities.ENTITY_TYPES.get(name)
    if et is None:
        raise Refused(404, f"no connector named {name!r}")
    if not secret(name):
        raise Refused(403, f"push is not set up for {name}: no PROCINTEL_WEBHOOK_SECRET_{name.upper()} in the environment")
    if not signature_ok(name, body, header):
        raise Refused(401, "bad or missing signature")
    if connector_config.settings(name)["mode"] != "push":
        raise Refused(409, f"{name} is in poll mode; switch it to push on the Connectors page first")
    items = payload.get("items")
    if not isinstance(items, list) or not items or len(items) > MAX_ITEMS or et.key is None:
        raise Refused(400, f"body must be {{\"items\": [...]}} with 1 to {MAX_ITEMS} items")
    try:
        rows = {et.key(r): r for r in items}
    except (KeyError, TypeError) as e:
        raise Refused(400, f"an item lacks its key field: {e}") from e
    batch = store.new_batch()
    known = store.states(name)
    events = store.diff(name, et.watched, rows, known, complete=False)
    store.record(name, batch, events, list(rows))
    store.log_detection(batch, name, len(rows), len(events), "pushed by the source")
    job = detect.queue_batch(batch, "pushed change(s)", priority="high") if events else None
    return {"batch": batch, "items": len(rows), "events": len(events), "job": job}
