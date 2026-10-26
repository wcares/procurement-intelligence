"""The ongoing portfolio (tracker U9): active World Bank projects whose procurement is under way, so monitoring has
live work to follow. The rest of the data is built around completion reports, i.e. projects that have ended.

`choose` picks active projects (status Active, closing date in the future, approved on or after APPROVED_AFTER, at
least MIN_NOTICES procurement notices, not tracked yet), newest approvals first. `add` reads their project records
and notices and hands them to the event pipeline as Project.added / Notice.added events, so the usual rules write
them and the hourly detection keeps them current from then on (procintel.pipeline). Their ISRs and restructuring
papers follow through the daily SupervisionDoc read.

    python -m procintel.ingestion.ongoing --projects 30
"""
from __future__ import annotations

import argparse
from datetime import date

import pandas as pd

from procintel.core import db
from procintel.ingestion import ingest
from procintel.ingestion.wb_client import WBClient
from procintel.pipeline import detect, entities, store

APPROVED_AFTER = "2021-01-01"
MIN_NOTICES = 10
PAGE = 100


def choose(n: int, client: WBClient | None = None, today: date | None = None) -> list[dict]:
    client = client or WBClient(fresh_listings=True)
    today = pd.Timestamp(today or date.today())
    con = db.connect(read_only=True)
    try:
        tracked = {p for (p,) in con.execute("SELECT project_id FROM projects").fetchall()}
    finally:
        con.close()
    out, offset = [], 0
    while len(out) < n:
        _, ps = client.projects(rows=PAGE, offset=offset, status_exact="Active")
        if not ps:
            break
        offset += PAGE
        for p in ps:
            closing = pd.to_datetime(p.get("closingdate"), errors="coerce")
            approved = pd.to_datetime(p.get("boardapprovaldate"), errors="coerce", utc=True)
            if p["id"] in tracked or pd.isna(closing) or closing <= today or pd.isna(approved) \
                    or approved < pd.Timestamp(APPROVED_AFTER, tz="UTC"):
                continue
            total, _ = client.notices(rows=1, project_id=p["id"])
            if total >= MIN_NOTICES:
                out.append(p)
                if len(out) == n:
                    break
        if offset > 2000:   # the listing is newest first; this far down the approvals are older than wanted
            break
    return out


def add(projects: list[dict], client: WBClient | None = None) -> dict:
    """Queue the projects and their notices into the pipeline; returns the batch, the counts and the job."""
    client = client or WBClient(fresh_listings=True)
    project_rows = {p["id"]: ingest.project_row(p) for p in projects}
    notice_rows = {}
    for pid in project_rows:
        for nt in client.iter_notices(ingest.MAX_NOTICES_PER_PROJECT, project_id=pid):
            r = ingest.notice_row(nt)
            notice_rows[r["notice_id"]] = r
    batch = store.new_batch()
    for name, rows in (("Project", project_rows), ("Notice", notice_rows)):
        et = entities.ENTITY_TYPES[name]
        events = store.diff(name, et.watched, rows, store.states(name), complete=False)
        store.record(name, batch, events, list(rows))
        store.log_detection(batch, name, len(rows), len(events), "ongoing portfolio added")
    job = detect.queue_batch(batch, "ongoing projects and notices added")
    return {"batch": batch, "projects": len(project_rows), "notices": len(notice_rows), "job": job}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--projects", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true", help="only list the projects that would be added")
    a = ap.parse_args()
    chosen = choose(a.projects)
    for p in chosen:
        print(p["id"], str(p.get("boardapprovaldate"))[:10], str(p.get("closingdate"))[:10], (p.get("countryshortname") or "")[:20],
              (p.get("project_name") or "")[:60])
    if not a.dry_run:
        print(add(chosen))


if __name__ == "__main__":
    main()
