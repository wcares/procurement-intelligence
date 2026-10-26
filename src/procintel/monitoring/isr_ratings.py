"""Previous and current ratings from a project's newest ISR ("Overall Ratings" passage, procintel.ingestion.isr_chunk):
progress towards the development objective (PDO), implementation progress (IP) and overall risk. A downgrade from
previous to current is an early warning for the project's packages."""
from __future__ import annotations

import re

from procintel.core import db

PERFORMANCE = ["Highly Satisfactory", "Satisfactory", "Moderately Satisfactory", "Moderately Unsatisfactory",
               "Unsatisfactory", "Highly Unsatisfactory"]          # best first
RISK = ["Low", "Moderate", "Substantial", "High"]                  # best first
MEASURES = {"pdo": ("Progress towards achievement of PDO", PERFORMANCE),
            "ip": ("Overall Implementation Progress (IP)", PERFORMANCE),
            "risk": ("Overall Risk Rating", RISK)}


def parse(text: str) -> dict[str, tuple[str, str]]:
    out = {}
    for key, (label, scale) in MEASURES.items():
        alt = "|".join(sorted(map(re.escape, scale), key=len, reverse=True))   # "Moderately Satisfactory" before "Satisfactory"
        m = re.search(re.escape(label) + rf"\s+({alt})\s+({alt})", text)
        if m:
            out[key] = (m.group(1), m.group(2))
    return out


def downgrades(ratings: dict[str, tuple[str, str]]) -> list[str]:
    out = []
    for key, (prev, cur) in ratings.items():
        scale = MEASURES[key][1]
        if scale.index(cur) > scale.index(prev):
            out.append(f"{MEASURES[key][0]}: {prev} -> {cur}")
    return out


def latest(project_ids: list[str]) -> dict[str, dict]:
    """{project_id: {"date", "doc_id", "ratings", "downgrades"}} from each project's newest ISR with a ratings passage."""
    if not project_ids:
        return {}
    con = db.connect(read_only=True)
    try:
        rows = con.execute("""
            SELECT d.project_id, d.doc_id, d.doc_date::DATE::VARCHAR, c.text
            FROM documents d JOIN chunk c USING (doc_id)
            WHERE d.doc_type = 'Implementation Status and Results Report' AND c.section = 'Overall Ratings'
              AND d.project_id IN (SELECT unnest(?))
            QUALIFY row_number() OVER (PARTITION BY d.project_id ORDER BY d.doc_date DESC) = 1""", [project_ids]).fetchall()
    finally:
        con.close()
    out = {}
    for pid, doc, day, text in rows:
        r = parse(text)
        out[pid] = {"date": day, "doc_id": doc, "ratings": r, "downgrades": downgrades(r)}
    return out
