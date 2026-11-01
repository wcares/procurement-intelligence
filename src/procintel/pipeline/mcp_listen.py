"""Subscribe mode for MCP servers: a server with "subscribe": true in data/mcp_sources.json is followed live.

One background thread holds a session with each such server and listens (MCP subscriptions/listen, protocol
2026-07-28) for changes to its resource list and to each resource it offers. A change does not carry the new content:
it queues a read of the MCP source (detect_changes for McpDocument, high priority, so it runs at once rather than
waiting for an idle app, and the batch it plans runs at once too). The read compares every resource with the stored
state as the scheduled read does, so a subscription only makes a change arrive sooner; the scheduled read stays as the
safety net for events lost while the session was down. Events within DEBOUNCE seconds share one read.

A dropped session is reopened after RETRY seconds, doubling up to RETRY_CAP; a server that does not offer
subscriptions is left to the scheduled read. state() says how each followed server is doing, for the Connectors page.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone

from procintel.pipeline import mcp_source

log = logging.getLogger(__name__)
DEBOUNCE = 3.0       # seconds: events this close together share one read
RETRY = 5.0          # seconds before reopening a dropped session, doubled each time
RETRY_CAP = 300.0

_state: dict[str, dict] = {}
_thread: threading.Thread | None = None


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def state() -> dict[str, dict]:
    """Per followed server: state (connecting | listening | reconnecting | not supported), since, changes seen, last
    change, error."""
    return {k: dict(v) for k, v in _state.items()}


def followed() -> list[dict]:
    try:
        return [s for s in mcp_source.servers() if s.get("subscribe")]
    except ValueError:
        return []


def queue_read(server: str, jobs_db=None) -> str | None:
    from procintel.jobs import store as jobs_store
    return jobs_store.enqueue("detect_changes", f"MCP server {server} reported a change",
                              {"force": True, "types": [mcp_source.TYPE], "batchPriority": "high"},
                              dedupe=False, db_path=jobs_db, priority="high")


async def _session(server: dict, st: dict, on_change) -> None:
    """One session: list, listen, queue a read per burst of changes; returns to listen again when the list changed."""
    from mcp.shared.subscriptions import ResourcesListChanged
    async with mcp_source._client(server) as client:
        while True:
            uris = [str(r.uri) for r in (await client.list_resources(cache_mode="bypass")).resources
                    if not server.get("uri_prefix") or str(r.uri).startswith(server["uri_prefix"])]
            relist = False
            async with client.listen(resources_list_changed=True, resource_subscriptions=uris) as sub:
                st.update(state="listening", since=_now(), error=None)
                async for event in sub:
                    st["changes"] += 1
                    st["lastChange"] = _now()
                    await asyncio.sleep(DEBOUNCE)     # let a burst settle (copying several files)
                    on_change(server["name"])
                    if isinstance(event, ResourcesListChanged):
                        relist = True                 # new resources: listen again to follow them too
                        break
            if not relist:
                return                                # the server closed the stream: reopen from the top


async def follow(server: dict, on_change=queue_read, stop: asyncio.Event | None = None) -> None:
    """Follow one server until stopped: listen, queue a read on each burst of changes, reopen on a drop."""
    from mcp.client.subscriptions import ListenNotSupportedError
    name = server["name"]
    st = _state.setdefault(name, {"state": "connecting", "since": _now(), "changes": 0, "lastChange": None, "error": None})
    stop = stop or asyncio.Event()
    wait = RETRY
    while not stop.is_set():
        session = asyncio.create_task(_session(server, st, on_change))
        stopping = asyncio.create_task(stop.wait())
        done, _ = await asyncio.wait({session, stopping}, return_when=asyncio.FIRST_COMPLETED)
        if stopping in done:
            session.cancel()
            await asyncio.gather(session, return_exceptions=True)
            break
        stopping.cancel()
        try:
            session.result()
            wait = RETRY                              # a clean close: reopen soon
        except ListenNotSupportedError:
            st.update(state="not supported", error="the server does not offer subscriptions; read on schedule only")
            return
        except Exception as e:   # noqa: BLE001 - logged, shown on the Connectors page, retried
            st.update(state="reconnecting", error=f"{type(e).__name__}: {e}"[:300])
            log.warning("MCP server %s: %s; retrying in %.0f s", name, e, wait)
        try:
            await asyncio.wait_for(stop.wait(), wait)
        except asyncio.TimeoutError:
            pass
        wait = min(wait * 2, RETRY_CAP)
    st.update(state="stopped")


def start() -> None:
    """Follow every server marked subscribe, in one daemon thread (called when the API starts its background work)."""
    global _thread
    servers = followed()
    if not servers or (_thread and _thread.is_alive()):
        return

    async def all_servers() -> None:
        await asyncio.gather(*(follow(s) for s in servers))

    _thread = threading.Thread(target=lambda: asyncio.run(all_servers()), name="procintel-mcp-listen", daemon=True)
    _thread.start()
