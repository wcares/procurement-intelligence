"""Supplier entity resolution: World Bank firm ids that are the same firm, merged into one firm.

The notices name each awarded supplier with a firm id, but one firm is often registered under several ids
("SRS FERTILIZERS CORPORATION", ids 430945 and 430957, both in India). Ids are merged when their names match after
removing case, punctuation and legal-form words (CO, LTD, LIMITED, PVT, LLC, INC, SA ...; and the "M/S" prefix used in
South Asia) AND they won contracts in the same country. Many suppliers are individual consultants, and the same
personal name in two countries need not be one person, so a name is merged across countries only when it is clearly
an organisation (a legal-form word, or words such as UNITED NATIONS, GROUP, CONSULTING, ASSOCIATES, CENTER, FUND).

Checked 2026-10-25: all 99 merges whose spellings differ read by hand, none wrong (3 not confirmable from the name
alone); the 15 names found in several countries were all international organisations (WFP, UNICEF, UNOPS, Sinohydro,
WAPCOS ...), 13 of which the organisation rule now merges.

    supplier_entity   firm_id -> entity_id
    firm              entity_id, name (the most used spelling), firm_ids, n_packages, countries

    python -m procintel.entities
"""
from __future__ import annotations

import re
from pathlib import Path

import duckdb

from procintel import paths

DB_PATH = paths.DB_PATH
LEGAL = {"CO", "COMPANY", "COMPANIES", "LTD", "LIMITED", "PVT", "PVTLTD", "PRIVATE", "LLC", "LLP", "INC",
         "INCORPORATED", "CORP", "CORPORATION", "SA", "SARL", "SAS", "SARLU", "SPA", "SRL", "GMBH", "AG", "PLC", "BV",
         "NV", "PTY", "PT", "JSC", "OJSC", "LLP", "THE", "AND"}
ORG_WORDS = {"UNITED", "NATIONS", "GROUP", "CONSULTING", "CONSULTANTS", "ASSOCIATES", "CENTER", "CENTRE", "FUND",
             "PROGRAMME", "PROGRAM", "FOUNDATION", "ASSOCIATION", "INSTITUTE", "UNIVERSITY", "AGENCY", "ORGANIZATION",
             "ORGANISATION"}


def is_org(name: str) -> bool:
    words = set(re.sub(r"[^A-Z0-9]+", " ", (name or "").upper()).split())
    return bool(words & ((LEGAL - {"THE", "AND"}) | ORG_WORDS))


def key(name: str) -> str:
    """Name with case, punctuation, legal-form words and a leading "M/S" removed; "" if nothing else is left."""
    words = re.sub(r"[^A-Z0-9]+", " ", (name or "").upper()).split()
    if words[:2] == ["M", "S"]:  # "M/S" (messrs) prefix
        words = words[2:]
    return " ".join(w for w in words if w not in LEGAL)


def resolve(rows: list[tuple[int, str, str, int]]) -> dict[int, int]:
    """rows: (firm_id, name, country, n_packages) per firm id and country. Returns firm_id -> entity_id, where the
    entity id is the smallest firm id of the group; ids with an empty key stay on their own."""
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        a, b = find(x), find(y)
        if a != b:
            parent[max(a, b)] = min(a, b)

    by_key: dict[tuple[str, str], int] = {}
    org_keys = {key(n) for _, n, _, _ in rows if is_org(n)}
    first_org: dict[str, int] = {}
    for fid, name, country, _ in rows:
        find(fid)
        k = key(name)
        if not k:
            continue
        union(by_key.setdefault((k, country), fid), fid)
        if k in org_keys:  # an organisation: the same name in another country is the same firm
            union(first_org.setdefault(k, fid), fid)
    return {f: find(f) for f in parent}


def build(db_path: Path = DB_PATH) -> dict:
    con = duckdb.connect(str(db_path))
    rows = con.execute("""
        SELECT s.firm_id, s.name, coalesce(p.country_code, '?') AS country, count(DISTINCT a.package_id)
        FROM supplier s JOIN award_supplier a USING (firm_id) JOIN package k USING (package_id)
        LEFT JOIN project p USING (project_id)
        GROUP BY 1, 2, 3""").fetchall()
    ent = resolve(rows)
    con.execute("CREATE OR REPLACE TABLE supplier_entity (firm_id INTEGER, entity_id INTEGER)")
    con.executemany("INSERT INTO supplier_entity VALUES (?, ?)", list(ent.items()))
    con.execute("""
        CREATE OR REPLACE TABLE firm AS
        SELECT e.entity_id,
               (SELECT arg_max(s2.name, s2.n_packages) FROM supplier s2 JOIN supplier_entity e2 USING (firm_id)
                WHERE e2.entity_id = e.entity_id) AS name,
               list(DISTINCT e.firm_id ORDER BY e.firm_id) AS firm_ids,
               count(DISTINCT a.package_id) AS n_packages,
               list(DISTINCT p.country_code ORDER BY p.country_code) AS countries
        FROM supplier_entity e JOIN award_supplier a USING (firm_id) JOIN package k USING (package_id)
        LEFT JOIN project p USING (project_id)
        GROUP BY e.entity_id""")
    out = {"firm_ids": len(ent), "firms": con.execute("SELECT count(*) FROM firm").fetchone()[0],
           "merged_groups": con.execute("SELECT count(*) FROM firm WHERE len(firm_ids) > 1").fetchone()[0],
           "multi_country_firms": con.execute("SELECT count(*) FROM firm WHERE len(countries) > 1").fetchone()[0]}
    con.close()
    print(f"firm: {out['firm_ids']} firm ids -> {out['firms']} firms ({out['merged_groups']} merged groups, "
          f"{out['multi_country_firms']} working in several countries)")
    return out


if __name__ == "__main__":
    build()
