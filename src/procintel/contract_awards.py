"""Contract awards from the World Bank Finances One data catalog, for the projects in the data.

Dataset DS00005 "Contract Awards in Investment Project Financing (since FY 2020)" (resource RS00005): one row per
signed contract, with the borrower's contract reference (the bid reference the notices use), signing date, supplier,
supplier firm id and amount in USD. It replaces the old Major Contract Awards endpoint
(finances.worldbank.org/resource/kdui-wcs3.json), which now redirects to an HTML page. Queried per project with
filter=project_id='P...' (found 2026-10-25; the API serves up to 1,000 rows per request and pages with skip).

Matched to packages by contract reference (the package id is "<project>/<bid reference>"): 4,341 of 6,990 packages
(2026-10-25). Where a package also has an award notice date, signing follows it by a median of 2 days (90th
percentile 27), so a signing date can stand in for a missing award date: fill_award_dates gives 114 packages without
one a tender-to-award time (marked award_from_contract; 207 matched, 114 signed after their tender started).

    python -m procintel.contract_awards      # builds table contract_award, then fills award dates
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import requests  # as procintel.wb_client: it carries its own certificate bundle

from procintel import db, paths

DB_PATH = paths.DB_PATH
API = "https://datacatalogapi.worldbank.org/dexapps/fone/api/apiservice"
PAGE = 1000
COLUMNS = ["project_id", "borrower_contract_reference_number", "contract_description", "contract_signing_date",
           "procurement_category", "procurement_method", "review_type", "supplier", "supplier_id",
           "supplier_country_code", "supplier_contract_amount_usd", "wb_contract_number", "as_of_date"]


def fetch_project(project_id: str, get=requests.get) -> list[dict]:
    rows, skip = [], 0
    while True:
        r = get(API, params={"datasetId": "DS00005", "resourceId": "RS00005", "type": "json", "top": PAGE,
                             "skip": skip, "filter": f"project_id='{project_id}'"}, timeout=60)
        r.raise_for_status()
        d = r.json()
        batch = d.get("data") or []
        rows += batch
        skip += len(batch)
        if not batch or skip >= d.get("count", 0):
            return rows


def _date(s: str | None) -> str | None:
    return datetime.strptime(s, "%d-%b-%Y").date().isoformat() if s else None


def build(db_path: Path = DB_PATH, pause: float = 0.2) -> dict:
    con = db.connect(db_path)
    projects = [p for (p,) in con.execute("SELECT project_id FROM project ORDER BY 1").fetchall()]
    con.close()  # not held during the ~2 minutes of requests
    rows, failed = [], []
    for pid in projects:
        try:
            for r in fetch_project(pid):
                rows.append([r.get(c) for c in COLUMNS])
        except Exception as e:  # one project failing must not lose the others
            failed.append(f"{pid}: {type(e).__name__}")
        time.sleep(pause)
    for r in rows:
        r[3], r[12] = _date(r[3]), _date(r[12])
        r.append(int(r[8]) if str(r[8] or "").isdigit() else None)  # Bank firm id; some supplier ids are hex keys
    con = db.connect(db_path)
    con.execute("""CREATE OR REPLACE TABLE contract_award (project_id VARCHAR, contract_ref VARCHAR, description VARCHAR,
        signing_date DATE, category VARCHAR, method VARCHAR, review_type VARCHAR, supplier VARCHAR, supplier_id VARCHAR,
        supplier_country VARCHAR, amount_usd DOUBLE, wb_contract_number VARCHAR, as_of_date DATE, firm_id BIGINT)""")
    if rows:
        con.executemany("INSERT INTO contract_award VALUES (" + ", ".join("?" * (len(COLUMNS) + 1)) + ")", rows)
    n_proj = con.execute("SELECT count(DISTINCT project_id) FROM contract_award").fetchone()[0]
    con.close()
    out = {"contracts": len(rows), "projects_with_contracts": n_proj, "projects": len(projects), "failed": failed}
    print(f"contract_award: {out}")
    return out


_MATCH = """
    SELECT k.package_id, min(a.signing_date) AS signing_date
    FROM package k JOIN contract_award a ON a.project_id = k.project_id
     AND upper(regexp_replace(a.contract_ref, '\\s', '', 'g'))
       = upper(regexp_replace(split_part(k.package_id, '/', 2), '\\s', '', 'g'))
    GROUP BY 1"""


def fill_award_dates(db_path: Path = DB_PATH) -> int:
    """Give packages without an award date the contract signing date (only when it is after the tender start)."""
    con = db.connect(db_path)
    try:
        if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'contract_award'").fetchone():
            return 0
        con.execute("ALTER TABLE package ADD COLUMN IF NOT EXISTS award_from_contract BOOLEAN DEFAULT FALSE")
        con.execute(f"CREATE OR REPLACE TEMP TABLE signed AS {_MATCH}")
        n = con.execute("""SELECT count(*) FROM package k JOIN signed s USING (package_id)
                           WHERE k.tender_to_award_days IS NULL AND k.tender_start IS NOT NULL
                             AND s.signing_date > k.tender_start::DATE""").fetchone()[0]
        con.execute("""UPDATE package SET award_date = s.signing_date::TIMESTAMPTZ,
                           tender_to_award_days = date_diff('day', package.tender_start::DATE, s.signing_date),
                           award_from_contract = TRUE
                       FROM signed s
                       WHERE package.package_id = s.package_id AND package.tender_to_award_days IS NULL
                         AND package.tender_start IS NOT NULL AND s.signing_date > package.tender_start::DATE""")
        print(f"package: {n} award dates filled from contract signing dates")
        return n
    finally:
        con.close()


if __name__ == "__main__":
    build()
    fill_award_dates()
