"""Entity types the pipeline tracks: what identifies an item, which fields count as a change, how often to look, and
how to read the item both from its source and from the database (the latter seeds the state on a first run).

Adding a kind of data means one more EntityType here (a source reader and a database reader); the state store, event
log, rules and the Settings page then handle it unchanged. Readers return rows as they come; the store normalises the
watched fields before fingerprinting (store.norm), so the same item read from the source and from the database gets
the same fingerprint, and the actions write the source rows unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

import pandas as pd

from procintel.core import db

NOTICE_WINDOW = timedelta(days=30)   # notices read newest first back to this long before the newest one known
NOTICE_MAX_PAGES = 20                # at most 2,000 notices per run


@dataclass
class EntityType:
    name: str
    every: timedelta                                   # how often detection reads the source
    watched: list[str]                                 # fields whose change is an event
    read_source: Callable[[dict], tuple[dict[str, dict], bool]]   # (rows by key, complete?) from the source
    read_db: Callable[[], dict[str, dict]]             # rows by key from the database (first run: seed)
    source: str = ""                                   # where read_source reads, for the Connectors page
    mode: str = "poll"                                 # how changes reach us: poll | push | subscribe | upload
    key: Callable[[dict], str] | None = None           # an item's key, for pushed items (procintel.pipeline.webhook)


def _rows(sql: str, key: Callable[[dict], str]) -> dict[str, dict]:
    con = db.connect(read_only=True)
    try:
        df = con.execute(sql).df()  # through pandas: DuckDB's own conversion of zoned times needs pytz
        out = {}
        for rec in df.to_dict("records"):
            out[key(rec)] = rec
        return out
    finally:
        con.close()


def _project_ids() -> list[str]:
    con = db.connect(read_only=True)
    try:
        return [p for (p,) in con.execute("SELECT project_id FROM project ORDER BY 1").fetchall()]
    finally:
        con.close()


# --- Notice -----------------------------------------------------------------------------------------------------------

NOTICE_FIELDS = ["notice_type", "notice_version", "notice_date", "award_date", "price_currency", "price_amount",
                 "suppliers"]


def notices_from_db() -> dict[str, dict]:
    return _rows("SELECT * EXCLUDE (text), text FROM notices", lambda r: r["notice_id"])


def notices_from_source(ctx: dict) -> tuple[dict[str, dict], bool]:
    """Newest notices of the tracked projects (one listing for all of them), back to NOTICE_WINDOW before the newest
    notice already known; a window, so absence in it is not a removal."""
    from procintel.ingestion import ingest
    from procintel.ingestion.wb_client import WBClient
    newest = ctx.get("newest_notice")
    cutoff = (pd.Timestamp(newest, tz="UTC") - NOTICE_WINDOW) if newest else None
    client = WBClient(fresh_listings=True)
    ids = "^".join(_project_ids())
    out: dict[str, dict] = {}
    for page in range(NOTICE_MAX_PAGES):
        _, batch = client.notices(rows=100, offset=page * 100, project_id=ids)
        if not batch:
            break
        for n in batch:
            row = ingest.notice_row(n)
            out[row["notice_id"]] = row
        last = pd.to_datetime(batch[-1].get("submission_date"), errors="coerce", utc=True)
        if cutoff is not None and pd.notna(last) and last < cutoff:
            break
    return out, False


# --- Project ----------------------------------------------------------------------------------------------------------

PROJECT_FIELDS = ["status", "closing_date", "sector", "commitment_usd", "board_approval"]


def projects_from_db() -> dict[str, dict]:
    return _rows("SELECT * FROM projects", lambda r: r["project_id"])


def projects_from_source(ctx: dict) -> tuple[dict[str, dict], bool]:
    from procintel.ingestion import ingest
    from procintel.ingestion.wb_client import WBClient
    ids = _project_ids()
    _, ps = WBClient(fresh_listings=True).projects(rows=len(ids) + 10, id="^".join(ids))
    rows = {p["id"]: ingest.project_row(p) for p in ps}
    return rows, len(rows) == len(ids)  # complete only when every tracked project came back


# --- ContractAward ----------------------------------------------------------------------------------------------------

CONTRACT_FIELDS = ["signing_date", "amount_usd", "supplier", "contract_ref"]


def contract_key(r: dict) -> str:
    return f"{r['wb_contract_number']}|{r['supplier_id']}"  # unique (checked: 16,414 rows, 16,414 keys)


def contracts_from_db() -> dict[str, dict]:
    return _rows("SELECT * FROM contract_award", contract_key)


def contracts_from_source(ctx: dict) -> tuple[dict[str, dict], bool]:
    from procintel.ingestion import contract_awards
    rows = [contract_awards.to_row(r) for r in contract_awards.fetch_projects(_project_ids())]
    return {contract_key(r): r for r in rows}, True


# --- Indicator --------------------------------------------------------------------------------------------------------

def indicator_key(r: dict) -> str:
    return f"{r['source']}|{r['country_code']}|{r['indicator']}|{r['year']}"


def indicators_from_db() -> dict[str, dict]:
    return _rows("SELECT 'cpia' AS source, * FROM cpia UNION ALL SELECT 'wgi' AS source, * FROM wgi", indicator_key)


def indicators_from_source(ctx: dict) -> tuple[dict[str, dict], bool]:
    """CPIA and WGI per country, bypassing the HTTP cache (it would hide a change). About 800 requests: weekly."""
    from procintel.ingestion import tables, wgi
    from procintel.ingestion.wb_client import INDICATORS, WBClient
    client = WBClient()
    con = db.connect(read_only=True)
    try:
        countries = [c for (c,) in con.execute("SELECT DISTINCT country_code FROM project "
                                               "WHERE country_code IS NOT NULL ORDER BY 1").fetchall()]
    finally:
        con.close()
    out: dict[str, dict] = {}
    for source, codes in (("cpia", tables.CPIA_CODES), ("wgi", wgi.WGI_CODES)):
        for cc in countries:
            for code, short in codes.items():
                d = client._get(f"{INDICATORS}/country/{cc}/indicator/{code}", {"format": "json", "per_page": 80},
                                fresh=True)
                for r in (d[1] or []) if isinstance(d, list) and len(d) > 1 else []:
                    if r.get("value") is not None:
                        row = {"source": source, "country_code": cc, "year": int(r["date"]), "indicator": short,
                               "value": float(r["value"])}
                        out[indicator_key(row)] = row
    return out, True


# --- Document -------------------------------------------------------------------------------------------------------

DOCUMENT_FIELDS = ["doc_type", "doc_date", "title", "txt_url"]
DOCUMENT_PAGE = 50      # completion reports per listing request, newest first
DOCUMENT_MAX_PAGES = 6  # read until every tracked report was seen (new ones appear at the top), at most 300
DOCUMENT_SCOPE = 120    # the corpus: the newest this many reports (as procintel.ingestion.refresh, --icrs 120)


def documents_from_db() -> dict[str, dict]:
    from procintel.ingestion import supervision
    return _rows("SELECT doc_id, project_id, doc_type, doc_date, title, pdf_url, txt_url FROM documents "
                 f"WHERE doc_type NOT IN {supervision.TYPES}", lambda r: r["doc_id"])


def documents_from_source(ctx: dict) -> tuple[dict[str, dict], bool]:
    """The completion reports in the documents listing, newest first, until every tracked report has been seen (a
    window: absence there is not a removal)."""
    from procintel.ingestion.wb_client import ICR_TYPE, WBClient
    client, tracked = WBClient(fresh_listings=True), set(ctx.get("tracked") or [])
    docs: list[dict] = []
    for page in range(DOCUMENT_MAX_PAGES):
        _, batch = client.documents(rows=DOCUMENT_PAGE, offset=page * DOCUMENT_PAGE, docty_exact=ICR_TYPE)
        docs += batch
        if not batch or tracked <= {d["id"] for d in docs}:
            break
    out = {}
    for i, d in enumerate(docs):
        # a report is in scope when it is among the newest DOCUMENT_SCOPE or already tracked: reading on until every
        # tracked report is seen must not turn older reports further down the listing into new ones
        if i >= DOCUMENT_SCOPE and d["id"] not in tracked:
            continue
        if d.get("projectid") and d.get("txturl"):
            out[d["id"]] = {"doc_id": d["id"], "project_id": d["projectid"], "doc_type": d.get("docty"),
                            "doc_date": pd.to_datetime(d.get("docdt"), errors="coerce", utc=True),
                            "title": d.get("display_title"), "pdf_url": d.get("pdfurl"), "txt_url": d["txturl"]}
    return out, False


# --- SupervisionDoc: ISRs and restructuring papers of the tracked projects -----------------------------------------

def supervision_from_db() -> dict[str, dict]:
    from procintel.ingestion import supervision
    return _rows("SELECT doc_id, project_id, doc_type, doc_date, title, pdf_url, txt_url FROM documents "
                 f"WHERE doc_type IN {supervision.TYPES}", lambda r: r["doc_id"])


def supervision_from_source(ctx: dict) -> tuple[dict[str, dict], bool]:
    """The newest ISRs and restructuring papers per tracked project (procintel.ingestion.supervision). A window per
    project (older ones drop out as newer appear), so the read is not complete: absence is not a removal."""
    from procintel.ingestion import supervision
    from procintel.ingestion.wb_client import WBClient
    client = WBClient(fresh_listings=True)
    con = db.connect(read_only=True)
    try:
        projects = [p for (p,) in con.execute("SELECT project_id FROM projects ORDER BY 1").fetchall()]
    finally:
        con.close()
    return {r["doc_id"]: r for p in projects for r in supervision.for_project(client, p)}, False


ENTITY_TYPES: dict[str, EntityType] = {e.name: e for e in [
    EntityType("Notice", timedelta(hours=1), NOTICE_FIELDS, notices_from_source, notices_from_db,
               "World Bank procurement notices API (search.worldbank.org/api/procnotices)", key=lambda r: r["notice_id"]),
    EntityType("Project", timedelta(hours=1), PROJECT_FIELDS, projects_from_source, projects_from_db,
               "World Bank projects API (search.worldbank.org/api/v2/projects)", key=lambda r: r["project_id"]),
    EntityType("ContractAward", timedelta(days=1), CONTRACT_FIELDS, contracts_from_source, contracts_from_db,
               "World Bank Finances One: contract awards dataset", key=contract_key),
    EntityType("Indicator", timedelta(days=7), ["value"], indicators_from_source, indicators_from_db,
               "World Bank indicators API: CPIA and Worldwide Governance Indicators per country", key=indicator_key),
    EntityType("Document", timedelta(hours=1), DOCUMENT_FIELDS, documents_from_source, documents_from_db,
               "World Bank documents API: Implementation Completion Reports, newest first", key=lambda r: r["doc_id"]),
    EntityType("SupervisionDoc", timedelta(days=1), DOCUMENT_FIELDS, supervision_from_source, supervision_from_db,
               "World Bank documents API: the newest ISR and restructuring paper of each tracked project",
               key=lambda r: r["doc_id"]),
]}


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
