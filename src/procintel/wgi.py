"""Worldwide Governance Indicators (WGI) per country and year, from the World Bank indicators API (source 3).

CPIA scores exist only for IDA countries: 20 of the 72 countries in the data (Peru, Brazil, Turkey, Kazakhstan, the
Philippines, China ...) have none, and 258 labelled packages come from them. WGI covers nearly every country. The codes
are GOV_WGI_<x>.EST (estimate, about -2.5 to +2.5); the older codes such as CC.EST now return "not found" (checked
2026-10-25), which is why WGI was missing before.

    python -m procintel.wgi      # builds table wgi
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from procintel import db, paths
from procintel.wb_client import WBClient

DB_PATH = paths.DB_PATH
WGI_CODES = {
    "GOV_WGI_CC.EST": "control_of_corruption",
    "GOV_WGI_GE.EST": "government_effectiveness",
    "GOV_WGI_PV.EST": "political_stability",
    "GOV_WGI_RQ.EST": "regulatory_quality",
    "GOV_WGI_RL.EST": "rule_of_law",
    "GOV_WGI_VA.EST": "voice_accountability",
}


def build(db_path: Path = DB_PATH, client: WBClient | None = None) -> dict:
    con = db.connect(db_path)
    countries = [r[0] for r in con.execute("SELECT DISTINCT country_code FROM project WHERE country_code IS NOT NULL").fetchall()]
    con.close()  # not held during the requests
    c = client or WBClient()
    rows = []
    for cc in countries:
        for code, short in WGI_CODES.items():
            for r in c.indicator(cc, code, per_page=80):
                if r.get("value") is not None:
                    rows.append({"country_code": cc, "year": int(r["date"]), "indicator": short, "value": float(r["value"])})
    df = pd.DataFrame(rows, columns=["country_code", "year", "indicator", "value"])
    con = db.connect(db_path)
    con.execute("CREATE OR REPLACE TABLE wgi AS SELECT * FROM df")
    covered = con.execute("SELECT count(DISTINCT country_code) FROM wgi").fetchone()[0]
    con.close()
    out = {"rows": len(df), "countries": len(countries), "countries_covered": covered}
    print(f"wgi: {out}")
    return out


def latest(con: duckdb.DuckDBPyConnection) -> dict[str, list[dict]]:
    """country -> latest value per WGI indicator (same shape as stats.governance)."""
    if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'wgi'").fetchone():
        return {}
    out: dict[str, list[dict]] = {}
    for cc, ind, yr, val in con.execute("""SELECT country_code, indicator, year, value FROM wgi
            QUALIFY row_number() OVER (PARTITION BY country_code, indicator ORDER BY year DESC) = 1
            ORDER BY country_code, indicator""").fetchall():
        out.setdefault(cc, []).append({"indicator": ind, "year": yr, "value": round(val, 2)})
    return out


if __name__ == "__main__":
    build()
