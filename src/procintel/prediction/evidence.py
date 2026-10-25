"""Per-project evidence of procurement events (re-bidding, contract amendments) from ICR text and notices.

Each kind is a regular expression over ICR passages plus filters for matches that do not report an event in the project:
advice ("reduce re-tendering", "timely contract amendments") and look-alikes (the amendment of a law). A kind can add
evidence from notices (SQL returning project_id, ref, quote). Matches were read by hand for every kind before use, and
both sources miss cases, so the evidence is a lower bound ("at least N of M projects"), never a rate.

    python -m procintel.prediction.evidence      # builds table project_evidence for every kind
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import duckdb

from procintel.core import db, paths

DB_PATH = paths.DB_PATH


@dataclass(frozen=True)
class Kind:
    name: str
    pattern: str                     # matched against ICR text passages, case-insensitive
    advice: str = r"(?!x)x"          # in the same sentence, within 80 characters before a match: advice, not a report
    exclude: str = r"(?!x)x"         # in the 40 characters after a match: a look-alike (e.g. a law), not this event
    notice_sql: str | None = None    # extra evidence: SELECT project_id, ref, quote


def reports(kind: Kind, text: str) -> bool:
    """True when the passage reports the event in its project, not only advice or a look-alike."""
    for m in re.finditer(kind.pattern, text, re.I):
        before, after = text[max(0, m.start() - 80): m.start()], text[m.end(): m.end() + 40]
        if not re.search(kind.advice, before, re.I) and not re.search(kind.exclude, after, re.I):
            return True
    return False


def _quote(kind: Kind, text: str) -> str:
    m = re.search(kind.pattern, text, re.I)
    start = max(0, m.start() - 80)
    start = text.find(" ", start) + 1 if start else 0  # word boundary ~80 characters before, so the phrase is shown
    return text[start: m.end() + 120].strip()


def build(kinds: list[Kind], db_path: Path = DB_PATH) -> None:
    con = db.connect(db_path)
    con.execute("""CREATE TABLE IF NOT EXISTS project_evidence (kind VARCHAR, project_id VARCHAR, source VARCHAR,
                   ref VARCHAR, quote VARCHAR)""")
    total = con.execute("SELECT count(*) FROM project").fetchone()[0]
    for kind in kinds:
        rows = []
        for doc_id, chunk_id, text in con.execute(
                "SELECT doc_id, chunk_id, text FROM chunk WHERE kind = 'text' AND regexp_matches(text, ?, 'i')",
                [kind.pattern]).fetchall():
            if reports(kind, text):
                for (pid,) in con.execute("SELECT project_id FROM document_project WHERE doc_id = ?", [doc_id]).fetchall():
                    rows.append((kind.name, pid, "icr", chunk_id, _quote(kind, text)))
        if kind.notice_sql:
            rows += [(kind.name, pid, "notice_reference", ref, quote or "") for pid, ref, quote in con.execute(kind.notice_sql).fetchall()]
        con.execute("DELETE FROM project_evidence WHERE kind = ?", [kind.name])
        con.executemany("INSERT INTO project_evidence VALUES (?, ?, ?, ?, ?)", rows)
        n = con.execute("""SELECT count(DISTINCT project_id), count(DISTINCT project_id) FILTER (WHERE source = 'icr'),
                           count(DISTINCT project_id) FILTER (WHERE source = 'notice_reference')
                           FROM project_evidence WHERE kind = ?""", [kind.name]).fetchone()
        print(f"project_evidence[{kind.name}]: {n[0]} of {total} projects (ICR {n[1]}, notice references {n[2]})")
    con.close()


def by_country(con: duckdb.DuckDBPyConnection, kind: str) -> dict[str, dict]:
    """country -> {"projects": M, "with_event": N, "example": (project_id, quote) from an ICR if any}."""
    if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'project_evidence'").fetchone():
        return {}
    out = {cc: {"projects": n, "with_event": 0, "example": None}
           for cc, n in con.execute("SELECT country_code, count(*) FROM project GROUP BY 1").fetchall()}
    for cc, n in con.execute("""SELECT p.country_code, count(DISTINCT e.project_id) FROM project_evidence e
                                JOIN project p USING (project_id) WHERE e.kind = ? GROUP BY 1""", [kind]).fetchall():
        out[cc]["with_event"] = n
    for cc, pid, quote in con.execute("""SELECT p.country_code, arg_min(e.project_id, e.ref), arg_min(e.quote, e.ref)
                                         FROM project_evidence e JOIN project p USING (project_id)
                                         WHERE e.kind = ? AND e.source = 'icr' GROUP BY 1""", [kind]).fetchall():
        out[cc]["example"] = (pid, quote)
    return out


REBID = Kind(
    name="rebid",
    pattern=(r"\b(re-?bid(?:ding|s|ded)?|re-?tender(?:ed|ing|s)?|re-?advertis\w*|"
             r"re-?launch(?:ed)? (?:the )?(?:tender|bid|procurement)\w*|"
             r"(?:no|insufficient|few) (?:responsive|compliant|qualified) (?:bids|bidders|offers)|"
             r"(?:tender|bidding) (?:was|were) (?:cancelled|canceled|unsuccessful|declared void)|"
             r"failed (?:tenders?|bidding|procurements?))\b"),
    advice=r"\b(reduc\w*|avoid\w*|prevent\w*|minimi[sz]\w*)\b[^.;]*$",
    notice_sql="SELECT project_id, package_id, description FROM package WHERE rebid_evidence IS NOT NULL",
)

AMENDMENT = Kind(
    name="amendment",
    pattern=(r"\b(contract (?:amendments?|variations?|modifications?|time extensions?|extensions?)|"
             r"amend(?:ed|ments? to|ing) (?:the |these |several |some )?(?:\w+ )?contracts?|"
             r"variation orders?|change orders?|"
             r"extensions? (?:of|to) (?:the |their |several |some )?(?:\w+ )?contracts?|"
             r"contracts? (?:was|were|had to be|required) (?:amended|extended|modified))\b"),
    advice=r"\b(timely|reduc\w*|frequency of|management of|avoid\w*|minimi[sz]\w*|submission of all)\b[^.;]*$",
    exclude=r"^\s*(?:and \w+ )?(?:Act|Law|Code|Regulations?)\b",
)

KINDS = [REBID, AMENDMENT]

if __name__ == "__main__":
    build(KINDS)
