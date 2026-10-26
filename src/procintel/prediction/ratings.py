"""Conflicting evidence between a completion report (ICR) and the project's supervision ratings (ISR).

Each ICR's data sheet holds both: the RATINGS SUMMARY with the final Outcome rating, and the ISR RATINGS table with
every supervision rating (date, development-objective "DO" rating, implementation-progress "IP" rating). The outcome
and the DO rating judge the same thing, whether the objectives are achieved, so the last DO rating before completion
is compared with the outcome on the six-point scale (Highly Unsatisfactory 1 ... Highly Satisfactory 6).

Conflict: the two fall on opposite sides of the satisfactory line (4+ vs 3-), or are 2+ points apart.

Resolution (shown to users, never averaged): the ICR is the later assessment, written at completion with the final
results evidence, so its rating is the verdict; the ISR history is context, and the disagreement is stated with both
ratings and dates so the reader can weigh it.

    python -m procintel.prediction.ratings      # builds table rating_check
"""
from __future__ import annotations

import re
from pathlib import Path

import duckdb

from procintel.core import db, paths

DB_PATH = paths.DB_PATH
SCALE = {"Highly Unsatisfactory": 1, "Unsatisfactory": 2, "Moderately Unsatisfactory": 3,
         "Moderately Satisfactory": 4, "Satisfactory": 5, "Highly Satisfactory": 6}
# longest first, so "Moderately Satisfactory" is not read as "Satisfactory"
_R = "(" + "|".join(sorted(SCALE, key=len, reverse=True)) + ")"
_ISR_ROW = re.compile(rf"\b(\d{{2}}) (\d{{2}}-[A-Z][a-z]{{2}}-\d{{4}}) {_R} {_R}")
# A cell that wraps ("Moderately" / "Unsatisfactory") is flattened around the row: first word before the row number,
# the rest after the disbursement figure. The other cell stays inline. Which column wrapped is not recoverable.
_ROW_START = re.compile(r"\b(\d{2}) \d{2}-[A-Z][a-z]{2}-\d{4}\b")
_ISR_WRAPPED = re.compile(rf"\b(Moderately|Highly) (\d{{2}}) (\d{{2}}-[A-Z][a-z]{{2}}-\d{{4}}) {_R} [\d,]+\.\d+ (Satisfactory|Unsatisfactory)\b")
_OUTCOME = re.compile(rf"\bOutcome\b.*?{_R}")


def parse(text: str) -> dict:
    """{'outcome': rating or None, 'isr': [(seq, date, do_candidates, ip_candidates), ...]} from one ICR's text.

    A row has one candidate per column when both cells are inline; when one cell wrapped, the column it belongs to is
    unknown and both columns get both ratings as candidates."""
    flat = re.sub(r"\s+", " ", text)
    outcome = None
    i = flat.find("RATINGS SUMMARY")
    if i >= 0:
        j = flat.find("ISR RATINGS", i)
        summary = flat[i: j if j > i else i + 600]
        m = _OUTCOME.search(summary)
        outcome = m.group(1) if m else None
    isr = []
    k = flat.find("ISR RATINGS")
    if k >= 0:
        table = re.split(r"@#&OPS|SECTORS AND THEMES", flat[k: k + 8000])[0]
        rows = {seq: (seq, date, (do,), (ip,)) for seq, date, do, ip in _ISR_ROW.findall(table)}
        for first, seq, date, inline, rest in _ISR_WRAPPED.findall(table):
            wrapped = f"{first} {rest}"
            if wrapped in SCALE and seq not in rows:
                both = tuple(dict.fromkeys((inline, wrapped)))
                rows[seq] = (seq, date, both, both)
        isr = sorted(rows.values(), key=lambda r: int(r[0]))
        # the latest row that carries any rating, parsed or not: if it was not parsed, "last rating" is unknown
        starts = list(_ROW_START.finditer(table))
        rated = [int(m.group(1)) for i, m in enumerate(starts)
                 if re.search(_R, table[m.end(): starts[i + 1].start() if i + 1 < len(starts) else len(table)])]
        last_rated = max(rated, default=0)
    else:
        last_rated = 0
    return {"outcome": outcome, "isr": isr, "last_rated_seq": last_rated}


def check(parsed: dict) -> dict | None:
    """Comparison of the outcome with the last ISR DO rating; None when either is missing."""
    outcome, isr = parsed["outcome"], parsed["isr"]
    if not outcome or not isr:
        return None
    seq, last_date, do_cands, ip_cands = max(isr, key=lambda r: int(r[0]))
    if int(seq) < parsed.get("last_rated_seq", 0):  # a later rated row exists that the parser could not read
        return None
    o = SCALE[outcome]
    disagrees = lambda d: (o >= 4) != (SCALE[d] >= 4) or abs(o - SCALE[d]) >= 2  # noqa: E731
    conflict = all(disagrees(d) for d in do_cands)  # an ambiguous row only conflicts if every reading does
    last_do = " or ".join(do_cands)
    return {"outcome": outcome, "isr_n": len(isr), "isr_last_date": last_date, "isr_last_do": last_do,
            "isr_last_ip": " or ".join(ip_cands),
            "isr_min_do": min((d for r in isr for d in r[2]), key=SCALE.get), "conflict": conflict,
            "note": (f"The completion report rates the outcome {outcome}, but the last supervision rating "
                     f"({last_date}) for the development objective was {last_do}. The completion report is the later, "
                     "evidence-based verdict; the supervision rating is shown for context.") if conflict else ""}


def build(db_path: Path = DB_PATH) -> None:
    con = db.connect(db_path)
    rows = []
    from procintel.ingestion.supervision import completion_reports_only
    icr = completion_reports_only(con)
    for doc_id, text in con.execute(f"SELECT doc_id, text FROM documents WHERE {icr}").fetchall():
        c = check(parse(text))
        if c:
            rows.append((doc_id, c["outcome"], c["isr_n"], c["isr_last_date"], c["isr_last_do"], c["isr_last_ip"],
                         c["isr_min_do"], c["conflict"], c["note"]))
    con.execute("""CREATE OR REPLACE TABLE rating_check (doc_id VARCHAR, outcome VARCHAR, isr_n INTEGER,
        isr_last_date VARCHAR, isr_last_do VARCHAR, isr_last_ip VARCHAR, isr_min_do VARCHAR, conflict BOOLEAN, note VARCHAR)""")
    con.executemany("INSERT INTO rating_check VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    n_docs = con.execute(f"SELECT count(*) FROM documents WHERE {icr}").fetchone()[0]
    n_conf = sum(r[7] for r in rows)
    print(f"rating_check: {len(rows)} of {n_docs} reports have both an outcome and ISR ratings; {n_conf} conflicts")
    for r in con.execute("SELECT doc_id, outcome, isr_last_do, isr_last_date FROM rating_check WHERE conflict").fetchall():
        print(f"  {r[0]}: outcome {r[1]} vs last ISR DO {r[2]} ({r[3]})")
    con.close()


def load(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """doc_id -> conflict note, for reports where the outcome and the last ISR rating disagree."""
    if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'rating_check'").fetchone():
        return {}
    return dict(con.execute("SELECT doc_id, note FROM rating_check WHERE conflict").fetchall())


if __name__ == "__main__":
    build()
