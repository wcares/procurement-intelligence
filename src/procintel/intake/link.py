"""What a document refers to: World Bank project ids (P and six digits) and countries (reported by their name in the
projects table), checked against the projects table. Links to packages and firms come later (a bid reference or supplier name matched against notices)."""
from __future__ import annotations

import re

from procintel.core import db

PROJECT_ID = re.compile(r"\bP\d{6}\b")


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
    return {"projects": [{"id": p, "name": known[p][0] if p in known else None, "country": known[p][1] if p in known
                          else None, "known": p in known} for p in ids],
            "countries": sorted(named)}


def _forms(country: str) -> set[str]:
    """The official name as the projects table has it ("People's Republic of Bangladesh", "Kyrgyz Republic") and
    its short form ("Bangladesh", "Kyrgyz")."""
    short = country.rsplit(" of ", 1)[-1] if " of " in country else re.sub(r" Republic$", "", country)
    short = re.sub(r"^the ", "", short).strip()
    return {country} | ({short} if len(short) > 3 else set())
