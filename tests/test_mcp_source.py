import json
import sys

import duckdb
import pandas as pd
import pytest

from procintel.core import paths
from procintel.intake import store as intake_store
from procintel.jobs import store as jobs_store
from procintel.pipeline import detect, mcp_source, store

ICR = ("The World Bank\nIMPLEMENTATION COMPLETION AND RESULTS REPORT\nRural Roads Project (P123456)\nRepublic of Kenya\n"
       + "The project rehabilitated feeder roads; procurement of civil works was delayed by re-bidding. " * 20)
SERVER = str(paths.ROOT / "scripts" / "demo_mcp_server.py")


def _setup(tmp_path, monkeypatch, trusted=False):
    from procintel.pipeline import mcp_listen
    monkeypatch.setattr(mcp_listen, "_state", {})       # not the state of a listener the app started in another test
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "main.duckdb")
    monkeypatch.setattr(paths, "PIPELINE_DB", tmp_path / "pipeline.duckdb")
    monkeypatch.setattr(jobs_store, "DB_PATH", tmp_path / "jobs.duckdb")
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.delenv("PROCINTEL_DECIDE_API_BASE", raising=False)
    con = duckdb.connect(str(tmp_path / "main.duckdb"))
    con.execute("CREATE TABLE projects AS SELECT * FROM (VALUES ('P123456', 'Rural Roads', 'Republic of Kenya', 'KE')) "
                "t(project_id, name, country, country_code)")
    docs = pd.DataFrame([{"doc_id": "1", "project_id": "P1", "doc_type": "x", "doc_date": pd.Timestamp("2020-01-01", tz="UTC"),
                          "title": "t", "pdf_url": "u", "txt_url": "u", "text": "old"}])
    con.execute("CREATE TABLE documents AS SELECT * FROM docs")
    con.close()
    folder = tmp_path / "offered"
    folder.mkdir()
    (tmp_path / "mcp_sources.json").write_text(json.dumps(
        [{"name": "demo", "command": [sys.executable, SERVER, "--folder", str(folder)], "trusted": trusted}]))
    return folder


def _read_and_run():
    """One detection read of the MCP source, then the batch its events ask for (the ingest action)."""
    steps = detect.detect_steps({"types": ["McpDocument"], "force": True}, None, {})
    try:
        while True:
            cur = next(steps)
    except StopIteration as stop:
        out = stop.value
    events = store.batch_events(out["batch"])
    if out["job"]:
        for _ in detect.batch_steps({"batch": out["batch"]}, None, {}):
            pass
    return events


def test_configuration_is_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    assert mcp_source.servers() == [] and "no MCP server" in mcp_source.describe()
    (tmp_path / "mcp_sources.json").write_text(json.dumps([{"name": "bad name", "url": "http://x"}]))
    with pytest.raises(ValueError):
        mcp_source.servers()
    (tmp_path / "mcp_sources.json").write_text(json.dumps([{"name": "a", "url": "http://x", "command": ["y"]}]))
    with pytest.raises(ValueError):
        mcp_source.servers()
    (tmp_path / "mcp_sources.json").write_text(json.dumps([{"name": "a", "url": "http://x", "enabled": False}]))
    assert mcp_source.servers() == []


def test_documents_offered_over_mcp_are_taken_in_replaced_and_removed(tmp_path, monkeypatch):
    folder = _setup(tmp_path, monkeypatch)
    (folder / "report.txt").write_text(ICR)
    (folder / "photo.jpg").write_bytes(b"\xff\xd8not a document")

    events = _read_and_run()                                   # first read: both are new
    assert sorted(e["type"] for e in events) == ["McpDocument.added", "McpDocument.added"]
    items = {i["uri"]: i for i in mcp_source.items()}
    report = items["file:///report.txt"]
    assert report["status"] == "awaiting_approval"            # a completion report from an untrusted server waits
    up = intake_store.get(report["upload_id"])
    assert up["uploaded_by"] == "mcp:demo" and up["doc_type"] == "completion_report"
    assert items["file:///photo.jpg"]["status"] == "skipped" and "format" in items["file:///photo.jpg"]["note"]

    assert _read_and_run() == []                               # nothing changed: no events, nothing read again

    (folder / "report.txt").write_text(ICR + " A later version.")
    events = _read_and_run()
    assert [e["type"] for e in events] == ["McpDocument.changed"]
    new = {i["uri"]: i for i in mcp_source.items()}["file:///report.txt"]
    assert new["upload_id"] != report["upload_id"]
    assert intake_store.get(report["upload_id"])["status"] == "removed"   # the earlier version is taken out

    (folder / "report.txt").unlink()
    events = _read_and_run()
    assert [e["type"] for e in events] == ["McpDocument.removed"]
    assert intake_store.get(new["upload_id"])["status"] == "removed"
    assert {i["uri"]: i for i in mcp_source.items()}["file:///report.txt"]["status"] == "removed"


def test_a_trusted_server_adds_a_completion_report_to_the_evidence(tmp_path, monkeypatch):
    folder = _setup(tmp_path, monkeypatch, trusted=True)
    (folder / "report.txt").write_text(ICR)
    _read_and_run()
    item = mcp_source.items()[0]
    assert item["status"] == "added"
    con = duckdb.connect(str(tmp_path / "main.duckdb"))
    assert con.execute("SELECT project_id FROM documents WHERE doc_id = ?", [f"upload-{item['upload_id']}"]).fetchone() == ("P123456",)
    con.close()


def test_a_server_that_cannot_be_read_fails_the_read_without_removing_anything(tmp_path, monkeypatch):
    folder = _setup(tmp_path, monkeypatch)
    (folder / "report.txt").write_text(ICR)
    _read_and_run()
    (tmp_path / "mcp_sources.json").write_text(json.dumps([{"name": "demo", "command": [sys.executable, "-c", "import sys; sys.exit(3)"]}]))
    assert _read_and_run() == []                                # the read failed: logged, no removals
    reads = store.connect().execute("SELECT error FROM detection WHERE entity_type = 'McpDocument' ORDER BY ran_at DESC").fetchall()
    assert reads[0][0] and "MCP server demo" in reads[0][0]
    assert mcp_source.items()[0]["status"] == "awaiting_approval"


def test_the_connectors_page_shows_the_servers_and_the_documents_taken_in(tmp_path, monkeypatch):
    from procintel.pipeline import connector_config, connectors
    folder = _setup(tmp_path, monkeypatch)
    (folder / "report.txt").write_text(ICR)
    _read_and_run()
    card = next(c for c in connectors.status() if c["name"] == "McpDocument")
    assert card["mcp"]["servers"] == [{"name": "demo", "kind": "local", "where": "demo_mcp_server.py", "trusted": False,
                                       "subscribe": False, "listen": None}]
    assert card["mcp"]["documents"][0]["title"] == "report.txt" and card["mcp"]["documents"][0]["status"] == "awaiting_approval"
    assert card["cursor"].startswith("every resource of 1 server(s): demo (local)")
    assert "cannot push" in connector_config.validate("McpDocument", {"mode": "push"})


def test_a_subscribed_server_reports_changes_and_each_queues_a_read_that_runs_at_once(tmp_path, monkeypatch):
    import asyncio
    from procintel.pipeline import mcp_listen
    folder = _setup(tmp_path, monkeypatch)
    (folder / "report.txt").write_text(ICR)
    monkeypatch.setattr(mcp_listen, "DEBOUNCE", 0.1)
    server = {"name": "demo", "command": [sys.executable, SERVER, "--folder", str(folder)], "subscribe": True}
    changes = []

    async def go():
        stop = asyncio.Event()
        task = asyncio.create_task(mcp_listen.follow(server, on_change=changes.append, stop=stop))
        for _ in range(100):                                     # wait until it listens
            if mcp_listen.state().get("demo", {}).get("state") == "listening":
                break
            await asyncio.sleep(0.1)
        (folder / "report.txt").write_text(ICR + " changed")     # a change to a followed resource
        for _ in range(100):
            if changes:
                break
            await asyncio.sleep(0.1)
        stop.set()
        await asyncio.wait_for(task, 10)

    asyncio.run(go())
    assert changes and changes[0] == "demo"
    assert mcp_listen.state()["demo"]["changes"] >= 1

    job = mcp_listen.queue_read("demo")                         # what a change queues: a high-priority read
    queued = jobs_store.next_pending()
    assert queued["id"] == job and queued["priority"] == 0 and queued["params"]["batchPriority"] == "high"
    steps = detect.detect_steps(queued["params"], None, {})
    try:
        while True:
            next(steps)
    except StopIteration as stop:
        batch_job = stop.value["job"]
    batch = next(j for j in jobs_store.recent() if j["id"] == batch_job)
    assert batch["kind"] == "pipeline_batch_light"                          # only light actions: runs while the app is busy
    from procintel.jobs import worker
    assert "pipeline_batch_light" in worker.LIGHT


def test_a_light_batch_hands_a_heavy_action_over_to_a_normal_batch(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    batch = store.new_batch()
    store.log_derived(batch, [{"type": "Passages.changed", "key": "x"}])       # asks for indexing: heavy
    out = None
    steps = detect.batch_steps({"batch": batch, "light": True}, None, {})
    try:
        while True:
            next(steps)
    except StopIteration as stop:
        out = stop.value
    assert out["actions"] == [] and out["handedOver"]
    queued = jobs_store.next_pending()
    assert queued["kind"] == "pipeline_batch" and queued["params"]["batch"] == batch
