"""What a document refers to: World Bank project ids (P and six digits) and countries (reported by their name in the
projects table), checked against the projects table; packages by their bid reference and firms by their name, both
compared in the form the supplier table uses (upper case, anything not a letter or digit as one space). When the
document names tracked projects, packages and firms are looked for within those projects only; otherwise across all,
with stricter length rules so short references and generic names do not match by chance."""
from __future__ import annotations

import re

from procintel.core import db

PROJECT_ID = re.compile(r"\bP\d{6}\b")
MIN_REF, MIN_REF_ANY = 6, 10        # characters of a normalised bid reference (within named projects / anywhere)
MIN_FIRM, MIN_FIRM_ANY = 8, 14      # characters of a normalised firm name, which also needs two words
MAX_LINKS = 25


def norm(s: str) -> str:
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", s.upper()).split())


def find(text: str) -> dict:
    ids = sorted(set(PROJECT_ID.findall(text)))
    con = db.connect(read_only=True)
    try:
        known = {p: (n, c) for p, n, c in con.execute(
            "SELECT project_id, name, country FROM projects WHERE project_id IN (SELECT unnest(?))", [ids or [""]]
        ).fetchall()}
        # regions and "World" have codes with a digit (1W, 3E): not countries, and "World" is in every Bank document
        countries = [c for (c,) in con.execute("SELECT DISTINCT country FROM projects WHERE country IS NOT NULL "
                                               "AND NOT regexp_matches(coalesce(country_code, ''), '[0-9]')").fetchall()]
    finally:
        con.close()
    named = [c for c in countries if any(re.search(r"\b" + re.escape(form) + r"\b", text) for form in _forms(c))]
    packages, firms = packages_and_firms(text, list(known))
    return {"projects": [{"id": p, "name": known[p][0] if p in known else None, "country": known[p][1] if p in known
                          else None, "known": p in known} for p in ids],
            "countries": sorted(named), "packages": packages, "firms": firms}


def packages_and_firms(text: str, projects: list[str]) -> tuple[list[dict], list[dict]]:
    padded = f" {norm(text)} "
    scoped = bool(projects)
    con = db.connect(read_only=True)
    try:
        if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'supplier'").fetchone():
            return [], []
        where = "WHERE project_id IN (SELECT unnest(?))" if scoped else ""
        args = [projects] if scoped else []
        pk = con.execute(f"SELECT package_id, project_id, description FROM package {where}", args).fetchall()
        fm = con.execute(f"""SELECT DISTINCT s.firm_id, s.name, s.name_key FROM supplier s
                             {"JOIN award_supplier a USING (firm_id) JOIN package k USING (package_id) " + where if scoped
                              else ""}""", args).fetchall()
    finally:
        con.close()
    min_ref, min_firm = (MIN_REF, MIN_FIRM) if scoped else (MIN_REF_ANY, MIN_FIRM_ANY)
    packages = []
    for pid, proj, desc in pk:
        ref = norm(pid.split("/", 1)[-1])
        if len(ref) >= min_ref and any(ch.isdigit() for ch in ref) and f" {ref} " in padded:
            packages.append({"id": pid, "projectId": proj, "ref": pid.split("/", 1)[-1], "description": desc or ""})
    found = []
    for fid, name, key in fm:
        key = " ".join((key or "").split())
        if len(key) >= min_firm and " " in key and f" {key} " in padded:
            found.append({"firmId": int(fid), "name": name})
    return packages[:MAX_LINKS], sorted(found, key=lambda f: f["name"])[:MAX_LINKS]


def _forms(country: str) -> set[str]:
    """The official name as the projects table has it ("People's Republic of Bangladesh", "Kyrgyz Republic") and
    its short form ("Bangladesh", "Kyrgyz")."""
    short = country.rsplit(" of ", 1)[-1] if " of " in country else re.sub(r" Republic$", "", country)
    short = re.sub(r"^the ", "", short).strip()
    return {country} | ({short} if len(short) > 3 else set())
