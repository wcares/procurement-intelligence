"""Re-bidding evidence per project, from two independent sources.

- ICR text: passages that report a re-tender in the project ("re-bid", "retendering", "re-advertised", "relaunched
  tender", "no responsive bids", "failed bidding" ...). Checked by hand on all 35 matching passages (2026-10-25): 33
  report a re-tender in that project, 2 recommend reducing re-tendering; every one of the 19 reports matched has at
  least one genuine report.
- Notice references: packages re-tendered or awarded under the original reference plus "-N" (package.rebid_evidence).

Both miss cases: ICRs summarise (only 4 of the 11 projects with suffix evidence mention re-bidding in their ICR), and
only some agencies number re-tenders. So the evidence is a lower bound ("at least N of M projects"), never a rate.

    python -m procintel.rebid        # builds table project_rebid
"""
from __future__ import annotations

import re
from pathlib import Path

import duckdb

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "procintel.duckdb"
PATTERN = (r"\b(re-?bid(?:ding|s|ded)?|re-?tender(?:ed|ing|s)?|re-?advertis\w*|"
           r"re-?launch(?:ed)? (?:the )?(?:tender|bid|procurement)\w*|"
           r"(?:no|insufficient|few) (?:responsive|compliant|qualified) (?:bids|bidders|offers)|"
           r"(?:tender|bidding) (?:was|were) (?:cancelled|canceled|unsuccessful|declared void)|"
           r"failed (?:tenders?|bidding|procurements?))\b")
# a recommendation to avoid re-tendering is not a report that it happened
_ADVICE = re.compile(r"\b(reduc\w*|avoid\w*|prevent\w*|minimi[sz]\w*)\s+(?:the\s+)?(?:need for\s+)?re-?tender", re.I)


def reports(text: str) -> bool:
    """True when a passage reports a re-tender (not when it only advises against one)."""
    hits = [m for m in re.finditer(PATTERN, text, re.I)]
    return any(not _ADVICE.search(text[max(0, m.start() - 40): m.end()]) for m in hits)


def build(db_path: Path = DB_PATH) -> None:
    con = duckdb.connect(str(db_path))
    rows = []
    for doc_id, chunk_id, text in con.execute(
            "SELECT doc_id, chunk_id, text FROM chunk WHERE kind = 'text' AND regexp_matches(text, ?, 'i')", [PATTERN]).fetchall():
        if reports(text):
            m = re.search(PATTERN, text, re.I)
            # start at a word boundary ~80 characters before the match, so the shown snippet includes the re-tender
            start = max(0, m.start() - 80)
            start = text.find(" ", start) + 1 if start else 0
            quote = text[start: m.end() + 120].strip()
            for (pid,) in con.execute("SELECT project_id FROM document_project WHERE doc_id = ?", [doc_id]).fetchall():
                rows.append((pid, "icr", chunk_id, quote))
    rows += [(pid, "notice_reference", pkg, desc or "") for pid, pkg, desc in con.execute(
        "SELECT project_id, package_id, description FROM package WHERE rebid_evidence IS NOT NULL").fetchall()]
    con.execute("CREATE OR REPLACE TABLE project_rebid (project_id VARCHAR, source VARCHAR, ref VARCHAR, quote VARCHAR)")
    con.executemany("INSERT INTO project_rebid VALUES (?, ?, ?, ?)", rows)
    n = con.execute("""SELECT count(DISTINCT project_id), count(DISTINCT project_id) FILTER (WHERE source = 'icr'),
                       count(DISTINCT project_id) FILTER (WHERE source = 'notice_reference') FROM project_rebid""").fetchone()
    total = con.execute("SELECT count(*) FROM project").fetchone()[0]
    print(f"project_rebid: {n[0]} of {total} projects with re-bid evidence (ICR {n[1]}, notice references {n[2]})")
    con.close()


def by_country(con: duckdb.DuckDBPyConnection) -> dict[str, dict]:
    """country -> {"projects": M, "with_rebid": N, "example": (project_id, quote) from an ICR if any}."""
    if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'project_rebid'").fetchone():
        return {}
    out = {cc: {"projects": n, "with_rebid": 0, "example": None}
           for cc, n in con.execute("SELECT country_code, count(*) FROM project GROUP BY 1").fetchall()}
    for cc, n in con.execute("""SELECT p.country_code, count(DISTINCT r.project_id) FROM project_rebid r
                                JOIN project p USING (project_id) GROUP BY 1""").fetchall():
        out[cc]["with_rebid"] = n
    for cc, pid, quote in con.execute("""SELECT p.country_code, arg_min(r.project_id, r.ref), arg_min(r.quote, r.ref)
                                         FROM project_rebid r JOIN project p USING (project_id)
                                         WHERE r.source = 'icr' GROUP BY 1""").fetchall():
        out[cc]["example"] = (pid, quote)
    return out


def cost(con: duckdb.DuckDBPyConnection) -> tuple[float, float] | None:
    """(median tender-to-award days of re-tendered packages, median of all packages), or None without evidence."""
    r = con.execute("""SELECT median(tender_to_award_days) FILTER (WHERE rebid_evidence IS NOT NULL), median(tender_to_award_days)
                       FROM package WHERE tender_to_award_days IS NOT NULL""").fetchone()
    return (r[0], r[1]) if r[0] is not None else None


if __name__ == "__main__":
    build()
