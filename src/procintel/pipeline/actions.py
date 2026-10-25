"""Actions: the units of pipeline work rules can ask for. Each is today's build step for the affected data.

An action gets the keys its events named and the batch's events (whose `new` holds the source rows), does its work,
and returns derived events (Package.award_changed, Data.updated) that rules may turn into further actions in the same
batch. ACTIONS is ordered by data dependency: raw rows are written before the tables built from them, tables before
the award-date fill, everything before the reload. Adding an action = one function here, then name it in a rule.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from procintel.core import db


@dataclass(frozen=True)
class Action:
    name: str
    label: str
    run: Callable[[list[str], dict[str, dict], dict], list[dict]]   # (keys, events by key, ctx) -> derived events


def _upsert(table: str, key_sql: str, rows: list[dict], removed: list[str]) -> int:
    """Replace the rows whose key (an SQL expression over the table) is among the given ones; insert by column name."""
    con = db.connect()
    try:
        keys = [r["__key"] for r in rows] + removed
        if keys:
            con.execute(f"DELETE FROM {table} WHERE {key_sql} IN (SELECT unnest(?))", [keys])
        if rows:
            df = pd.DataFrame([{k: v for k, v in r.items() if k != "__key"} for r in rows])
            con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM df")
        return len(rows)
    finally:
        con.close()


def _rows(events: dict[str, dict]) -> tuple[list[dict], list[str]]:
    """(source rows of added/changed items with their key, keys of removed items)."""
    rows = [e["new"] | {"__key": k} for k, e in events.items() if e["new"] is not None]
    return rows, [k for k, e in events.items() if e["new"] is None]


def _suppliers_as_text() -> None:
    """Older databases keep notices.suppliers as a list of structs; new rows carry JSON text (Postgres has no unnamed
    structs). Convert the column once; procintel.ingestion.tables reads both forms."""
    con = db.connect()
    try:
        t = con.execute("SELECT data_type FROM duckdb_columns() WHERE table_name = 'notices' "
                        "AND column_name = 'suppliers'").fetchone()
        if t and t[0] != "VARCHAR":
            con.execute("ALTER TABLE notices ALTER suppliers TYPE VARCHAR USING to_json(suppliers)::VARCHAR")
    finally:
        con.close()


def _award_stats() -> tuple:
    con = db.connect(read_only=True)
    try:
        return con.execute("SELECT count(tender_to_award_days), sum(tender_to_award_days) FROM package").fetchone()
    finally:
        con.close()


DATA = {"type": "Data.updated", "key": "all"}


def ingest_documents(keys, events, ctx):
    """New or changed completion reports: fetch their text and write them; a report from a project not tracked yet
    also brings that project's record and its notices (the rest of the system needs both)."""
    from procintel.ingestion import ingest
    from procintel.ingestion.wb_client import WBClient
    rows, removed = _rows(events)
    client = WBClient()
    for r in rows:
        r["text"] = client.document_text(r["txt_url"])
    _upsert("documents", "doc_id", rows, removed)
    con = db.connect(read_only=True)
    try:
        known = {p for (p,) in con.execute("SELECT project_id FROM projects").fetchall()}
    finally:
        con.close()
    new = sorted({p for r in rows for p in r["project_id"].split(",") if p and p not in known})
    if new:
        _, ps = WBClient(fresh_listings=True).projects(rows=len(new) + 10, id="^".join(new))
        _upsert("projects", "project_id", [ingest.project_row(p) | {"__key": p["id"]} for p in ps], [])
        notices = [ingest.notice_row(n) for pid in new
                   for n in client.iter_notices(ingest.MAX_NOTICES_PER_PROJECT, project_id=pid)]
        _suppliers_as_text()
        _upsert("notices", "notice_id", [n | {"__key": n["notice_id"]} for n in notices], [])
    return [DATA, {"type": "Documents.changed", "key": "all"}]


def apply_notices(keys, events, ctx):
    _suppliers_as_text()
    rows, removed = _rows(events)
    _upsert("notices", "notice_id", rows, removed)
    return [DATA]


def apply_projects(keys, events, ctx):
    rows, removed = _rows(events)
    _upsert("projects", "project_id", rows, removed)
    return [DATA]


def apply_contracts(keys, events, ctx):
    rows, removed = _rows(events)
    _upsert("contract_award", "wb_contract_number || '|' || supplier_id", rows, removed)
    return [DATA]


def apply_indicators(keys, events, ctx):
    rows, removed = _rows(events)
    for source in ("cpia", "wgi"):
        mine = [{k: v for k, v in r.items() if k != "source"} for r in rows if r["source"] == source]
        gone = [k for k in removed if k.startswith(f"{source}|")]
        _upsert(source, f"'{source}|' || country_code || '|' || indicator || '|' || year", mine, gone)
    return [DATA]


def rebuild_tables(keys, events, ctx):
    from procintel.ingestion import tables
    before = _award_stats()
    tables.build()
    out = [DATA]
    if _award_stats() != before:
        out.append({"type": "Package.award_changed", "key": "all"})
    return out


def fill_award_dates(keys, events, ctx):
    from procintel.ingestion import contract_awards
    before = _award_stats()
    contract_awards.fill_award_dates()
    return [DATA] + ([{"type": "Package.award_changed", "key": "all"}] if _award_stats() != before else [])


def sector_links(keys, events, ctx):
    from procintel.ingestion import sectors
    sectors.build()
    return [DATA]


def rebuild_firms(keys, events, ctx):
    from procintel.ingestion import entities
    entities.build()
    return [DATA]


def chunk_documents(keys, events, ctx):
    """Re-cut the passages (the whole corpus takes about 2 s, and unchanged texts keep their ids, vectors and tags);
    reports Passages.changed when any passage text changed."""
    from procintel.ingestion import chunk
    before = _passage_digest()
    chunk.build()
    return [DATA] + ([{"type": "Passages.changed", "key": "all"}] if _passage_digest() != before else [])


def _passage_digest() -> tuple:
    con = db.connect(read_only=True)
    try:
        return con.execute("SELECT count(*), sum(hash(chunk_id || text)) FROM chunk").fetchone()
    finally:
        con.close()


def index_passages(keys, events, ctx):
    """Embed and tag the passages that are new or changed (each step skips what is already up to date), and bring
    the vector store along."""
    from procintel.core import decide, embed, llm, vector_index
    from procintel.ingestion import problem_tag, tag
    if embed.available():
        embed.build()
        embed.build_packages()
        if vector_index.backend() == "qdrant":
            for kind in vector_index.SOURCES:
                vector_index.sync(kind)
    if decide.available():
        tag.build()
        if llm.available():
            problem_tag.build()
    return [DATA]


def document_checks(keys, events, ctx):
    """Everything read from the reports' passages: rating checks, re-bid and amendment evidence, sector links."""
    from procintel.ingestion import sectors
    from procintel.prediction import evidence, procurement_rating, ratings
    ratings.build()
    procurement_rating.build()
    evidence.build(evidence.KINDS)
    sectors.build()
    return [DATA]


def drift_check(keys, events, ctx):
    from procintel.jobs import store as jobs_store
    jobs_store.enqueue("drift_check", "pipeline: award times changed", db_path=ctx.get("jobs_db"))
    return []


def reload_backend(keys, events, ctx):
    reload = ctx.get("reload")
    if reload:
        reload()
    return []


ACTIONS: dict[str, Action] = {a.name: a for a in [
    Action("ingest_documents", "Fetch and write new or changed reports (and new projects' records and notices)",
           ingest_documents),
    Action("apply_notices", "Write new and changed procurement notices", apply_notices),
    Action("apply_projects", "Write changed project records", apply_projects),
    Action("apply_contracts", "Write new and changed contract awards", apply_contracts),
    Action("apply_indicators", "Write CPIA and WGI values", apply_indicators),
    Action("rebuild_tables", "Rebuild packages, suppliers and links (procintel.ingestion.tables)", rebuild_tables),
    Action("fill_award_dates", "Fill award dates from contract signing dates", fill_award_dates),
    Action("rebuild_firms", "Merge supplier firm ids of the same firm (procintel.ingestion.entities)", rebuild_firms),
    Action("chunk_documents", "Cut report texts into passages", chunk_documents),
    Action("index_passages", "Embed and tag new or changed passages", index_passages),
    Action("document_checks", "Rating checks, re-bid and amendment evidence from the passages", document_checks),
    Action("sector_links", "Rebuild contract-to-report links by sector and time", sector_links),
    Action("drift_check", "Queue a prediction drift check", drift_check),
    Action("reload_backend", "Reload the backend's data", reload_backend),
]}
ORDER = list(ACTIONS)
