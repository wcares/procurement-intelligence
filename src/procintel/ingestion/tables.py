"""Build the relational / graph-ready model from the raw ingest tables.

Raw (ingest.py):   projects, documents, notices
Modeled (this):    country, project, package, notice_m, supplier, award_supplier, document_m, cpia
Join keys: project_id (exact), (project_id, bid_ref) -> package, firm_id -> supplier, country_code -> cpia.
See docs/data-model.md for the diagram and the reasoning behind each grain.

    python -m procintel.ingestion.tables
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from procintel.core import db, paths
from procintel.ingestion import contract_awards
from procintel.ingestion.wb_client import WBClient

DB_PATH = paths.DB_PATH
# notices.suppliers is a JSON list (older databases: a list of structs; the ::JSON cast reads both)
SUPPLIERS = '[{"name": "VARCHAR", "firm_id": "INTEGER"}]'

# Verified to return data on 2026-10-23 (EQRE, SPRT did not). Governance / institution-quality ones only.
CPIA_CODES = {
    "IQ.CPA.PUBS.XQ": "public_sector_mgmt_cluster",
    "IQ.CPA.TRAN.XQ": "transparency_corruption",
    "IQ.CPA.PADM.XQ": "public_administration",
    "IQ.CPA.PROP.XQ": "property_rights_rule_based_gov",
    "IQ.CPA.BREG.XQ": "business_regulatory_env",
    "IQ.CPA.IRAI.XQ": "ida_allocation_index",
}

# Notice stages that precede an award. General Procurement Notices are project-level, not package-level.
PRE_AWARD = "('Request for Expression of Interest','Invitation for Bids','Invitation for Prequalification')"


def build_cpia(con: duckdb.DuckDBPyConnection) -> int:
    c = WBClient()
    codes = [r[0] for r in con.execute("SELECT DISTINCT country_code FROM project WHERE country_code IS NOT NULL").fetchall()]
    rows = []
    for cc in codes:
        for code, short in CPIA_CODES.items():
            for r in c.indicator(cc, code, per_page=80):
                if r.get("value") is not None:
                    rows.append({"country_code": cc, "year": int(r["date"]), "indicator": short, "value": float(r["value"])})
    df = pd.DataFrame(rows, columns=["country_code", "year", "indicator", "value"])
    con.execute("CREATE OR REPLACE TABLE cpia AS SELECT * FROM df")
    return len(df)


def build(db_path: Path = DB_PATH) -> None:
    con = db.connect(db_path)

    con.execute("""
    CREATE OR REPLACE TABLE country AS
    SELECT country_code, any_value(country) AS name, any_value(region) AS region
    FROM projects WHERE country_code IS NOT NULL GROUP BY country_code""")

    con.execute("""
    CREATE OR REPLACE TABLE project AS
    SELECT project_id, name, country_code, sector, lending_instrument, commitment_usd,
           board_approval, closing_date, status, implementing_agency
    FROM projects""")

    # A notice belongs to a package. Package = (project_id, bid_ref); a notice with no bid_ref is its own package.
    # Some awards are filed under the tender's reference plus "-N" (e.g. ...-CW-RFB-3, likely the bidding round). Such
    # an award is linked to the tender when the suffixed reference has no tender of its own, the base reference is a
    # tender, and that tender has no dated award; `relinked` marks it so the link can be audited.
    con.execute(f"""
    CREATE OR REPLACE TABLE notice_m AS
    WITH n AS (
        SELECT notice_id, project_id,
               project_id || '/' || COALESCE(NULLIF(bid_ref,''), notice_id) AS package_id,
               notice_type, notice_date, award_date, duration_days, notice_version,
               price_currency, price_amount, proc_group, method_code, method_name, description, suppliers
        FROM notices),
    tenders AS (SELECT DISTINCT package_id FROM n WHERE notice_type IN {PRE_AWARD}),
    dated_awards AS (SELECT DISTINCT package_id FROM n WHERE notice_type = 'Contract Award' AND award_date IS NOT NULL),
    relink AS (
        SELECT DISTINCT package_id AS award_pkg, regexp_replace(package_id, '-[0-9]{{1,2}}$', '') AS base
        FROM n
        WHERE notice_type = 'Contract Award' AND regexp_matches(package_id, '-[0-9]{{1,2}}$')
          AND package_id NOT IN (SELECT package_id FROM tenders)
          AND regexp_replace(package_id, '-[0-9]{{1,2}}$', '') IN (SELECT package_id FROM tenders)
          AND regexp_replace(package_id, '-[0-9]{{1,2}}$', '') NOT IN (SELECT package_id FROM dated_awards))
    SELECT n.* REPLACE (COALESCE(r.base, n.package_id) AS package_id), r.base IS NOT NULL AS relinked
    FROM n LEFT JOIN relink r ON n.package_id = r.award_pkg""")

    con.execute(f"""
    CREATE OR REPLACE TABLE package AS
    WITH pre AS (
        SELECT package_id, MIN(notice_date) AS tender_start,
               arg_min(notice_type, notice_date) AS first_stage
        FROM notice_m WHERE notice_type IN {PRE_AWARD} GROUP BY package_id),
    aw AS (
        SELECT package_id, MIN(award_date) AS award_date, MAX(notice_version) AS max_notice_version,
               COUNT(*) AS n_award_notices, MAX(duration_days) AS contract_duration_days,
               arg_max(price_currency, notice_date) AS price_currency,
               arg_max(price_amount, notice_date) AS price_amount,
               bool_or(relinked) AS award_relinked
        FROM notice_m WHERE notice_type = 'Contract Award' GROUP BY package_id),
    base AS (
        SELECT package_id, any_value(project_id) AS project_id,
               any_value(proc_group) AS proc_group, any_value(method_code) AS method_code,
               arg_max(description, LENGTH(COALESCE(description,''))) AS description,
               COUNT(*) AS n_notices
        FROM notice_m WHERE notice_type <> 'General Procurement Notice' GROUP BY package_id)
    SELECT b.*, pre.tender_start, pre.first_stage, aw.award_date, aw.max_notice_version,
           aw.n_award_notices, aw.contract_duration_days, aw.price_currency, aw.price_amount, aw.award_relinked,
           CASE WHEN pre.tender_start IS NOT NULL AND aw.award_date IS NOT NULL
                 AND aw.award_date >= pre.tender_start
                THEN date_diff('day', pre.tender_start, aw.award_date) END AS tender_to_award_days
    FROM base b LEFT JOIN pre USING (package_id) LEFT JOIN aw USING (package_id)""")

    # Re-bid evidence. Some agencies number a re-tender as the original reference plus "-N": 30 references exist both
    # as X and X-N in the same project (28 of them with X-N later, median 104 days), and 10 awards were filed under
    # "-N" (linked above). This marks the ORIGINAL package. It is positive-only evidence from ~12 of 98 projects
    # (13 pairs from one project): a package without it may still have been re-bid, so it is not a re-bid rate.
    con.execute("""
    ALTER TABLE package ADD COLUMN rebid_evidence VARCHAR;
    UPDATE package SET rebid_evidence = 'award_under_suffix' WHERE award_relinked;
    UPDATE package SET rebid_evidence = 'successor_reference'
    WHERE rebid_evidence IS NULL AND package_id IN (
        SELECT regexp_replace(package_id, '-[0-9]{1,2}$', '') FROM package WHERE regexp_matches(package_id, '-[0-9]{1,2}$'));
    """)

    con.execute(f"""
    CREATE OR REPLACE TABLE supplier AS
    SELECT s.firm_id, arg_max(s.name, LENGTH(s.name)) AS name,
           regexp_replace(upper(arg_max(s.name, LENGTH(s.name))), '[^A-Z0-9]+', ' ', 'g') AS name_key,
           COUNT(DISTINCT n.package_id) AS n_packages
    FROM (SELECT package_id, UNNEST(from_json(suppliers::JSON, '{SUPPLIERS}')) AS s FROM notice_m
          WHERE json_array_length(suppliers::JSON) > 0) n
    GROUP BY s.firm_id""")  # s.firm_id on a struct column; name = longest spelling seen for that firm id

    con.execute(f"""
    CREATE OR REPLACE TABLE award_supplier AS
    SELECT DISTINCT package_id, s.firm_id
    FROM (SELECT package_id, UNNEST(from_json(suppliers::JSON, '{SUPPLIERS}')) AS s FROM notice_m
          WHERE json_array_length(suppliers::JSON) > 0)""")

    con.execute("""
    CREATE OR REPLACE TABLE document_m AS
    SELECT doc_id, doc_type, doc_date, title, pdf_url, txt_url, LENGTH(text) AS n_chars
    FROM documents""")

    # An ICR can cover several projects ("P176278,P179849"), so documents link to projects many-to-many.
    con.execute("""
    CREATE OR REPLACE TABLE document_project AS
    SELECT DISTINCT d.doc_id, TRIM(p) AS project_id
    FROM documents d, UNNEST(string_split(d.project_id, ',')) AS t(p)
    WHERE TRIM(p) IN (SELECT project_id FROM project)""")

    n_cpia = build_cpia(con)
    print(f"cpia: {n_cpia} rows")
    for t in ("country", "project", "package", "notice_m", "supplier", "award_supplier", "document_m", "document_project", "cpia"):
        print(f"{t:15s}", con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    con.close()
    # package was recreated above: give packages without an award notice their contract signing date again
    contract_awards.fill_award_dates(db_path)


if __name__ == "__main__":
    build()
