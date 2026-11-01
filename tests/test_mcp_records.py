import json
import sys

import duckdb
import pytest

from procintel.core import paths
from procintel.jobs import store as jobs_store
from procintel.pipeline import detect, mcp_records, store

SERVER = str(paths.ROOT / "tests" / "fixtures" / "mcp_tool_server.py")
FIELDS = {"wb_contract_number": "contract_no", "supplier_id": "supplier_id", "supplier": "supplier_name",
          "contract_ref": "bid_ref", "signing_date": "signed_on", "amount_usd": "amount", "project_id": "project"}
ROW = {"contract_no": "900001", "supplier_id": 4242, "supplier_name": "Test Builders", "bid_ref": "KE-X-1-CW-RFB",
       "signed_on": "2025-03-04T00:00:00", "amount": 1000.5, "project": "P123456"}


def _setup(tmp_path, monkeypatch, tools):
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "main.duckdb")
    monkeypatch.setattr(paths, "PIPELINE_DB", tmp_path / "pipeline.duckdb")
    monkeypatch.setattr(jobs_store, "DB_PATH", tmp_path / "jobs.duckdb")
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    from procintel.ingestion import contract_awards
    con = duckdb.connect(str(tmp_path / "main.duckdb"))
    cols = ", ".join(f"{c} VARCHAR" if c not in ("amount_usd", "firm_id", "signing_date", "as_of_date") else
                     f"{c} {'DOUBLE' if c == 'amount_usd' else 'BIGINT' if c == 'firm_id' else 'DATE'}"
                     for c in contract_awards.TABLE_COLUMNS)
    con.execute(f"CREATE TABLE contract_award ({cols})")
    con.close()
    rows = tmp_path / "rows.json"
    rows.write_text(json.dumps([ROW]))
    (tmp_path / "mcp_sources.json").write_text(json.dumps(
        [{"name": "lake", "command": [sys.executable, SERVER, str(rows)], "tools": tools}]))
    return rows


def _read_and_apply():
    steps = detect.detect_steps({"types": ["McpRecord"], "force": True}, None, {})
    try:
        while True:
            next(steps)
    except StopIteration as stop:
        out = stop.value
    events = store.batch_events(out["batch"])
    ev = {e["key"]: e for e in events}
    if ev:
        mcp_records.apply(list(ev), ev, {})
    return events


def _awards(tmp_path):
    con = duckdb.connect(str(tmp_path / "main.duckdb"))
    try:
        return con.execute("SELECT wb_contract_number, supplier_id, supplier, signing_date::VARCHAR, amount_usd, firm_id "
                           "FROM contract_award").fetchall()
    finally:
        con.close()


def test_rows_from_a_tool_become_contract_awards_and_follow_its_changes(tmp_path, monkeypatch):
    rows = _setup(tmp_path, monkeypatch, [{"name": "awards", "arguments": {"since": "2024-01-01"}, "as": "ContractAward",
                                           "fields": FIELDS}])
    events = _read_and_apply()
    assert [e["type"] for e in events] == ["McpRecord.added"] and events[0]["key"] == "lake|awards|900001|4242"
    assert _awards(tmp_path) == [("900001", "4242", "Test Builders", "2025-03-04", 1000.5, 4242)]
    assert _read_and_apply() == []                                           # unchanged: nothing

    rows.write_text(json.dumps([ROW | {"amount": 2000.0}]))
    assert [e["type"] for e in _read_and_apply()] == ["McpRecord.changed"]
    assert _awards(tmp_path)[0][4] == 2000.0

    rows.write_text(json.dumps([]))
    assert [e["type"] for e in _read_and_apply()] == ["McpRecord.removed"]
    assert _awards(tmp_path) == []
    card = mcp_records.overview()
    assert card["tools"] == [{"server": "lake", "tool": "awards", "as": "ContractAward", "records": 0}]


def test_plain_rows_are_kept_but_never_written_to_the_awards(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, [{"name": "awards", "key": "contract_no"}])
    _read_and_apply()
    assert _awards(tmp_path) == []
    assert mcp_records.overview()["tools"][0]["records"] == 1


def test_a_destructive_tool_is_refused_and_nothing_is_called(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, [{"name": "drop_table", "key": "x"}])
    with pytest.raises(RuntimeError, match="not read-only"):
        mcp_records.read_source({})


def test_the_configuration_is_checked(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, [{"name": "awards", "as": "ContractAward", "fields": {"supplier_id": "s"}}])
    with pytest.raises(ValueError, match="wb_contract_number"):
        mcp_records.tool_sources()


def test_rows_are_read_from_the_shapes_tools_return():
    class R:
        def __init__(self, structured=None, text=None):
            self.structured_content = structured
            self.content = [type("T", (), {"text": text})()] if text is not None else []
    assert mcp_records.parse_rows(R({"rows": [{"a": 1}]})) == [{"a": 1}]
    assert mcp_records.parse_rows(R(text=json.dumps({"columns": ["a", "b"], "rows": [[1, 2]]}))) == [{"a": 1, "b": 2}]
    assert mcp_records.parse_rows(R(text="a,b\n1,2\n")) == [{"a": "1", "b": "2"}]
    assert mcp_records.parse_rows(R(text=json.dumps([{"a": 1}]))) == [{"a": 1}]


def test_a_key_of_several_columns_keeps_rows_that_share_one(tmp_path, monkeypatch):
    rows = _setup(tmp_path, monkeypatch, [{"name": "awards", "key": ["contract_no", "supplier_id"]}])
    rows.write_text(json.dumps([ROW, ROW | {"supplier_id": 5555}]))      # one contract, two suppliers
    assert len(mcp_records.read_source({})[0]) == 2
