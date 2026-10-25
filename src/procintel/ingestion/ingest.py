"""Ingest a bounded, joinable slice of World Bank data into DuckDB.

Slice = projects that have an ICR (so structured rows and unstructured evaluations share a project_id).
Tables: projects, documents, notices.   Chunking/indexing is a separate step (chunk.py).

    python -m procintel.ingestion.ingest --icrs 120
"""
from __future__ import annotations

import argparse
import json

import pandas as pd
from bs4 import BeautifulSoup

from procintel.core import db, paths
from . import parse_notice as pn
from procintel.ingestion.wb_client import ICR_TYPE, WBClient

DB_PATH = paths.DB_PATH
MAX_NOTICES_PER_PROJECT = 300


def _num(s) -> float | None:
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return None


def project_row(p: dict) -> dict:
    country = p.get("countryname")
    sector = p.get("sector1") or {}
    return {
        "project_id": p["id"],
        "name": p.get("project_name"),
        "country": country[0] if isinstance(country, list) and country else country,
        "country_code": (p.get("countrycode") or [None])[0] if isinstance(p.get("countrycode"), list) else p.get("countrycode"),
        "region": p.get("regionname"),
        "status": p.get("status"),
        "lending_instrument": p.get("lendinginstr"),
        "commitment_usd": _num(p.get("totalcommamt")),
        "board_approval": pd.to_datetime(p.get("boardapprovaldate"), errors="coerce", utc=True),
        "closing_date": pd.to_datetime(p.get("closingdate"), errors="coerce", utc=True),
        "sector": sector.get("Name") if isinstance(sector, dict) else None,
        "implementing_agency": p.get("impagency"),
    }


def notice_row(n: dict) -> dict:
    text = BeautifulSoup(n.get("notice_text") or "", "html.parser").get_text(" | ", strip=True)
    price = pn.signed_price(text)
    return {
        "notice_id": n["id"],
        "project_id": n.get("project_id"),
        "notice_type": n.get("notice_type"),
        "bid_ref": n.get("bid_reference_no"),
        "description": n.get("bid_description"),
        "proc_group": n.get("procurement_group"),
        "method_code": n.get("procurement_method_code"),
        "method_name": n.get("procurement_method_name"),
        "notice_date": pd.to_datetime(n.get("submission_date"), errors="coerce", utc=True),
        "award_date": pd.to_datetime(pn.award_date(text), errors="coerce", utc=True),
        "duration_days": pn.duration_days(text),
        "notice_version": pn.notice_version(text),
        "price_currency": price[0] if price else None,
        "price_amount": price[1] if price else None,
        "suppliers": json.dumps([{"name": nm, "firm_id": fid} for nm, fid in pn.suppliers(text)]),  # JSON: Postgres has no unnamed structs
        "text": text,
    }


def run(n_icrs: int, fresh: bool = False, keep_existing: bool = False) -> None:
    """fresh: re-fetch listings instead of reading the HTTP cache. keep_existing: start from the documents already in
    the database and add newly listed ones (the listing is newest-first, so a fresh top-N would drop older ICRs)."""
    c = WBClient(fresh_listings=fresh)
    projects: dict[str, dict] = {}
    documents: list[dict] = []
    notices: list[dict] = []
    if keep_existing and DB_PATH.exists():
        con = db.connect(DB_PATH, read_only=True)
        cols = "doc_id, project_id, doc_type, strftime(doc_date, '%Y-%m-%dT%H:%M:%SZ') AS doc_date, title, pdf_url, txt_url"
        documents = [dict(zip(["doc_id", "project_id", "doc_type", "doc_date", "title", "pdf_url", "txt_url"], r))
                     for r in con.execute(f"SELECT {cols} FROM documents").fetchall()]
        for d in documents:  # same type as newly listed rows
            d["doc_date"] = pd.to_datetime(d["doc_date"], errors="coerce", utc=True)
        con.close()
        print(f"keeping {len(documents)} existing documents")
    known = {d["doc_id"] for d in documents}

    print(f"listing {n_icrs} ICRs ...")
    for d in c.iter_documents(n_icrs, docty_exact=ICR_TYPE):
        pid = d.get("projectid")
        if not pid or not d.get("txturl") or d["id"] in known:
            continue
        documents.append({
            "doc_id": d["id"], "project_id": pid, "doc_type": d.get("docty"),
            "doc_date": pd.to_datetime(d.get("docdt"), errors="coerce", utc=True),
            "title": d.get("display_title"), "pdf_url": d.get("pdfurl"), "txt_url": d["txturl"],
        })

    all_pids = sorted({p for d in documents for p in d["project_id"].split(",") if p})  # an ICR can cover several projects
    for i, pid in enumerate(all_pids, 1):
        _, ps = c.projects(rows=1, id=pid)
        if not ps:
            print(f"  [{i}] {pid}: no project record, skipping")
            continue
        projects[pid] = project_row(ps[0])
        for n in c.iter_notices(MAX_NOTICES_PER_PROJECT, project_id=pid):
            notices.append(notice_row(n))
        if i % 10 == 0:
            print(f"  {i} projects, {len(notices)} notices")

    for d in documents:
        if any(p in projects for p in d["project_id"].split(",")):
            d["text"] = c.document_text(d["txt_url"])
    documents = [d for d in documents if d.get("text")]

    con = db.connect(DB_PATH)
    for name, rows in (("projects", list(projects.values())), ("documents", documents), ("notices", notices)):
        df = pd.DataFrame(rows)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM df")
        print(f"{name}: {len(df)} rows")
    con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--icrs", type=int, default=120)
    ap.add_argument("--fresh", action="store_true", help="re-fetch listings instead of using the HTTP cache")
    ap.add_argument("--keep-existing", action="store_true", help="keep documents already in the database")
    a = ap.parse_args()
    run(a.icrs, fresh=a.fresh, keep_existing=a.keep_existing)
