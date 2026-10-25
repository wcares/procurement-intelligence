"""Sector families and contract-to-report links by sector and time.

Projects carry a detailed World Bank sector (42 in the data, mostly 1 to 7 projects each), too fine to match on. Each
is mapped by hand to its World Bank major sector ("Public Administration - Education" to Education; general public
administration stays Public Administration).

Table package_icr_link connects each contract package to completion reports (ICRs) it can learn from:
  same_project         the ICR of the package's own project (the exact link used so far)
  same_sector_period   ICRs of other projects in the same sector family that were running when the package was
                       tendered (board approval <= tender start <= closing date)

    python -m procintel.sectors
"""
from __future__ import annotations

from pathlib import Path

import duckdb

from procintel import paths

DB_PATH = paths.DB_PATH

FAMILY = {
    "Agricultural Extension, Research, and Other Support Activities": "Agriculture, Fishing and Forestry",
    "Agricultural markets, commercialization and agri-business": "Agriculture, Fishing and Forestry",
    "Fisheries": "Agriculture, Fishing and Forestry",
    "Forestry": "Agriculture, Fishing and Forestry",
    "Irrigation and Drainage": "Agriculture, Fishing and Forestry",
    "Livestock": "Agriculture, Fishing and Forestry",
    "Other Agriculture, Fishing and Forestry": "Agriculture, Fishing and Forestry",
    "Public Administration - Agriculture, Fishing & Forestry": "Agriculture, Fishing and Forestry",
    "Primary Education": "Education",
    "Tertiary Education": "Education",
    "Workforce Development and Vocational Education": "Education",
    "Public Administration - Education": "Education",
    "Energy Transmission and Distribution": "Energy and Extractives",
    "Mining": "Energy and Extractives",
    "Oil and Gas": "Energy and Extractives",
    "Other Energy and Extractives": "Energy and Extractives",
    "Renewable Energy Geothermal": "Energy and Extractives",
    "Renewable Energy Solar": "Energy and Extractives",
    "Renewable Energy Wind": "Energy and Extractives",
    "Public Administration - Energy and Extractives": "Energy and Extractives",
    "Other Non-bank Financial Institutions": "Financial Sector",
    "Public Administration - Financial Sector": "Financial Sector",
    "Health": "Health",
    "Manufacturing": "Industry, Trade and Services",
    "Tourism": "Industry, Trade and Services",
    "ICT Infrastructure": "Information and Communications Technologies",
    "ICT Services": "Information and Communications Technologies",
    "Public Administration - Information and Communications Technologies": "Information and Communications Technologies",
    "Central Government (Central Agencies)": "Public Administration",
    "Law and Justice": "Public Administration",
    "Other Public Administration": "Public Administration",
    "Sub-National Government": "Public Administration",
    "Social Protection": "Social Protection",
    "Public Administration - Social Protection": "Social Protection",
    "Aviation": "Transportation",
    "Rural and Inter-Urban Roads": "Transportation",
    "Public Administration - Transportation": "Transportation",
    "Other Water Supply, Sanitation and Waste Management": "Water, Sanitation and Waste Management",
    "Sanitation": "Water, Sanitation and Waste Management",
    "Waste Management": "Water, Sanitation and Waste Management",
    "Water Supply": "Water, Sanitation and Waste Management",
}


def family(sector: str | None) -> str | None:
    """Major sector for a detailed sector name (or a major sector name itself); None if unknown or empty."""
    if not sector:
        return None
    return FAMILY.get(sector) or (sector if sector in set(FAMILY.values()) else None)


def project_families(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """project_id -> major sector; {} when the project table has no sector column."""
    if not con.execute("""SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'project' AND column_name = 'sector'""").fetchone():
        return {}
    return {pid: f for pid, s in con.execute("SELECT project_id, sector FROM project").fetchall() if (f := family(s))}


def build(db_path: Path = DB_PATH) -> dict:
    con = duckdb.connect(str(db_path))
    fam = project_families(con)
    con.execute("CREATE OR REPLACE TEMP TABLE pfam (project_id VARCHAR, family VARCHAR)")
    con.executemany("INSERT INTO pfam VALUES (?, ?)", list(fam.items()))
    con.execute("""
        CREATE OR REPLACE TABLE package_icr_link AS
        SELECT k.package_id, dp.doc_id, dp.project_id AS icr_project_id, 'same_project' AS relation
        FROM package k JOIN document_project dp ON dp.project_id = k.project_id
        UNION ALL
        SELECT k.package_id, dp.doc_id, dp.project_id, 'same_sector_period'
        FROM package k
        JOIN pfam a ON a.project_id = k.project_id
        JOIN pfam b ON b.family = a.family AND b.project_id <> k.project_id
        JOIN project p ON p.project_id = b.project_id
        JOIN document_project dp ON dp.project_id = b.project_id
        WHERE k.tender_start IS NOT NULL AND p.board_approval IS NOT NULL
          AND k.tender_start::DATE BETWEEN p.board_approval::DATE AND coalesce(p.closing_date::DATE, DATE '2100-01-01')""")
    out = dict(con.execute("SELECT relation, count(*) FROM package_icr_link GROUP BY 1").fetchall())
    out["packages_with_sector_link"] = con.execute(
        "SELECT count(DISTINCT package_id) FROM package_icr_link WHERE relation = 'same_sector_period'").fetchone()[0]
    out["projects_with_family"] = len(fam)
    con.close()
    print(f"package_icr_link: {out}")
    return out


if __name__ == "__main__":
    build()
