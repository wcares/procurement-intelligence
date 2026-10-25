"""Procurement ratings stated in each ICR, compared with its overall verdict.

ISR tables carry no procurement rating, but the ICR's fiduciary compliance section states it in prose ("At closing, the
Procurement performance was rated Unsatisfactory", "fluctuated between Moderately Unsatisfactory and Moderately
Satisfactory"). A sentence counts when it is in that section and ties the rating to procurement performance or a
procurement rating ("procurement arrangements ... capacity assessment was satisfactory" does not). Per report:

- lowest: the lowest procurement rating stated anywhere in the section;
- closing: the last rating of a sentence about closing or completion, else the rating when only one is stated, else
  unknown (e.g. "mostly Satisfactory, with Moderately Satisfactory at times").

Conflict: procurement fell to the unsatisfactory side (lowest 3 or less) while the outcome, or the last ISR
implementation rating where no outcome is parsed, is satisfactory (4+): the overall rating hides procurement trouble a
planner should know about. Shown with the quoted sentence; neither rating is changed.

    python -m procintel.prediction.procurement_rating      # builds table procurement_check
"""
from __future__ import annotations

import re
from pathlib import Path

import duckdb

from procintel.core import db, paths
from procintel.prediction.ratings import SCALE

DB_PATH = paths.DB_PATH
ABBREV = {"HS": "Highly Satisfactory", "MS": "Moderately Satisfactory", "MU": "Moderately Unsatisfactory",
          "HU": "Highly Unsatisfactory"}
_RATING = re.compile(r"\b(" + "|".join(sorted(SCALE, key=len, reverse=True)) + r")\b", re.I)
_ABBREV = re.compile(r"\b(HS|MS|MU|HU)\b")  # uppercase only: "ms" or "Mu" are not ratings
_ABOUT = re.compile(r"procurement\W+(?:\w+\W+){0,3}?(?:performance|ratings?|rated|was|is|remained)\b"
                    r"|(?:performance|ratings?) (?:of|for) (?:the )?(?:project'?s? )?procurement", re.I)
_NOT_PERFORMANCE = re.compile(r"procurement (?:arrangements|capacity|risk|plan)\b(?![^.]*\b(?:performance|rating|rated)\b)", re.I)
_CLOSING = re.compile(r"\b(?:at|by) (?:project |program )?(?:closing|closure|close|completion)\b|\bultimately\b|"
                      r"\b(?:until|through) (?:project )?(?:closing|closure)\b|\bthereafter\b|\b(?:improved|upgraded|recovered)\b|"
                      r"\breaching\b", re.I)
# ratings counted over the sub-projects of a programme ("51 and 41 projects respectively") are not this report's own
_COUNTS = re.compile(r"\bproportion of projects\b|\b\d+ (?:and \d+ )?projects\b", re.I)


def _ratings(sentence: str) -> list[str]:
    """Ratings stated after the word "procurement", in order of appearance."""
    start = sentence.lower().find("procurement")
    found = [(m.start(), m.group(1).title()) for m in _RATING.finditer(sentence, start)]
    found += [(m.start(), ABBREV[m.group(1)]) for m in _ABBREV.finditer(sentence, start)]
    return [r for _, r in sorted(found)]


def parse(passages: list[str]) -> dict | None:
    """{'closing', 'lowest', 'quote'} from a report's fiduciary-section passages; None when no rating is stated."""
    stated = []  # (is about closing, ratings, sentence)
    for text in passages:
        for s in re.split(r"(?<=[.;])\s+", re.sub(r"\s+", " ", text)):
            if "procurement" not in s.lower() or not _ABOUT.search(s) or _NOT_PERFORMANCE.search(s) or _COUNTS.search(s):
                continue
            rs = _ratings(s)
            if rs:
                stated.append((bool(_CLOSING.search(s)), rs, s.strip()))
    if not stated:
        return None
    every = [r for _, rs, _ in stated for r in rs]
    closing_sentence = next((x for x in stated if x[0]), None)
    if closing_sentence:
        closing = closing_sentence[1][-1]
    else:
        closing = every[0] if len(set(every)) == 1 else None
    lowest = min(every, key=SCALE.get)
    quote = next(s for _, rs, s in stated if lowest in rs)
    return {"closing": closing, "lowest": lowest, "quote": quote}


def check(parsed: dict | None, outcome: str | None, last_ip: str | None) -> dict | None:
    if not parsed:
        return None
    verdict, basis = (outcome, "outcome") if outcome else (last_ip, "last supervision implementation rating")
    conflict = bool(verdict) and verdict in SCALE and SCALE[parsed["lowest"]] <= 3 and SCALE[verdict] >= 4
    closing = f" (at closing: {parsed['closing']})" if parsed["closing"] and parsed["closing"] != parsed["lowest"] else ""
    note = (f"The {basis} is {verdict}, but the report rates procurement as low as {parsed['lowest']}{closing}: "
            f"\"{parsed['quote']}\"") if conflict else ""
    return {**parsed, "verdict": verdict, "conflict": conflict, "note": note}


def build(db_path: Path = DB_PATH) -> None:
    con = db.connect(db_path)
    passages: dict[str, list[str]] = {}
    for doc_id, text in con.execute("""SELECT doc_id, text FROM chunk WHERE kind = 'text'
                                       AND regexp_matches(section, 'Fiduciary', 'i') ORDER BY doc_id, chunk_id""").fetchall():
        passages.setdefault(doc_id, []).append(text)
    overall = {d: (o, ip) for d, o, ip in con.execute("SELECT doc_id, outcome, isr_last_ip FROM rating_check").fetchall()}
    rows = []
    for doc_id, ps in passages.items():
        outcome, ip = overall.get(doc_id, (None, None))
        c = check(parse(ps), outcome, ip if ip in SCALE else None)  # an ambiguous IP cell ("X or Y") is not used
        if c:
            rows.append((doc_id, c["closing"], c["lowest"], c["verdict"], c["conflict"], c["quote"], c["note"]))
    con.execute("""CREATE OR REPLACE TABLE procurement_check (doc_id VARCHAR, closing VARCHAR, lowest VARCHAR,
                   verdict VARCHAR, conflict BOOLEAN, quote VARCHAR, note VARCHAR)""")
    con.executemany("INSERT INTO procurement_check VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    n_docs = con.execute("SELECT count(*) FROM documents").fetchone()[0]
    print(f"procurement_check: {len(rows)} of {n_docs} reports state a procurement rating; "
          f"{sum(r[4] for r in rows)} rate it lower than a satisfactory overall verdict")
    for r in rows:
        if r[4]:
            print(f"  {r[0]}: verdict {r[3]}, procurement lowest {r[2]}, closing {r[1]}")
    con.close()


def load(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """doc_id -> note, for reports whose procurement rating is lower than their satisfactory overall verdict."""
    if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'procurement_check'").fetchone():
        return {}
    return dict(con.execute("SELECT doc_id, note FROM procurement_check WHERE conflict").fetchall())


if __name__ == "__main__":
    build()
