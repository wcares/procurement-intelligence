"""Tag each ICR passage with the main kind of procurement or implementation problem it describes, using the decision
model (procintel.decide). Stored in table chunk_tag with every option's probability, so a caller can apply its own
confidence floor. Re-runs tag only new or changed passages (same text-hash scheme as procintel.embed).

The question and the seven options are the ones checked on the pre-registered set before choosing the model
(Laya: 6 of 8 passages tagged acceptably). "none of these" marks passages that describe no problem, such as
indicator tables and staffing lists, which make poor precedents.

Measured reliability on the full run (2026-10-24, Laya Q8_0, 18,140 passages, 653 s): the problem-type labels are NOT
reliable enough to show as facts. A hand check of 3 random passages per type found about 7 of 18 right, with wrong
labels up to 0.82 confidence ("capacity building" read as contractor capacity, a project named "Disaster
Resilience" read as an external shock). Only the "none of these" label is used, as a precedent filter at a high
confidence (assess.NOT_A_LESSON_MIN). A two-step question (is a problem described? then which) is the next thing
to try.

    python -m procintel.tag            # needs PROCINTEL_DECIDE_API_BASE
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import duckdb

from procintel import decide
from procintel.embed import text_hash

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "procintel.duckdb"
QUESTION = "What kind of procurement or implementation problem does this passage mainly describe?"
TAGS = ["funding or payment delays", "contractor performance or capacity",
        "external shock such as a pandemic, disaster or conflict", "land acquisition or resettlement",
        "weak specifications or design", "re-tendering or contract termination", "none of these"]
NONE = TAGS[-1]


def model_id() -> str:
    """The decision server's model id (llama-server /v1/models), stored beside the tags."""
    with urllib.request.urlopen(decide.api_base().rstrip("/") + "/v1/models", timeout=10) as r:
        return json.load(r)["data"][0]["id"]


def tag_text(text: str) -> dict[str, float]:
    return decide.choices(f"Passage: {text}", {"tag": (QUESTION, TAGS)})["tag"]


def build(db_path: Path = DB_PATH) -> int:
    """Number of passages tagged now (new or changed text)."""
    if not decide.available():
        raise SystemExit("set PROCINTEL_DECIDE_API_BASE first")
    m = model_id()
    con = duckdb.connect(str(db_path))
    con.execute("""CREATE TABLE IF NOT EXISTS chunk_tag (
        chunk_id VARCHAR, model VARCHAR, text_hash VARCHAR, tag VARCHAR, confidence DOUBLE, probs JSON)""")
    chunks = con.execute("SELECT chunk_id, section, text FROM chunk WHERE kind = 'text'").fetchall()
    have = {(c, h) for c, h in con.execute("SELECT chunk_id, text_hash FROM chunk_tag WHERE model = ?", [m]).fetchall()}
    todo = [(c, text_hash(s, t), t) for c, s, t in chunks if (c, text_hash(s, t)) not in have]
    print(f"chunk_tag: {len(chunks) - len(todo)} up to date, {len(todo)} to tag with {m}")
    t0, rows = time.time(), []

    def flush() -> None:
        con.execute("DELETE FROM chunk_tag WHERE model = ? AND chunk_id IN (SELECT unnest(?))", [m, [r[0] for r in rows]])
        con.executemany("INSERT INTO chunk_tag VALUES (?, ?, ?, ?, ?, ?)", rows)
        rows.clear()

    failed = []
    for i, (cid, h, text) in enumerate(todo, 1):
        try:
            p = tag_text(text)
        except Exception as e:  # one bad passage must not stop the run; it stays untagged and is retried next run
            failed.append((cid, str(e)[:120]))
            continue
        best = max(p, key=p.get)
        rows.append((cid, m, h, best, p[best], json.dumps(p)))
        if len(rows) == 500:
            flush()
            print(f"  {i}/{len(todo)}  {time.time() - t0:.0f}s")
    if rows:
        flush()
    gone = con.execute("DELETE FROM chunk_tag WHERE chunk_id NOT IN (SELECT chunk_id FROM chunk) RETURNING 1").fetchall()
    dist = con.execute("SELECT tag, count(*), round(avg(confidence), 2) FROM chunk_tag WHERE model = ? GROUP BY 1 ORDER BY 2 DESC", [m]).fetchall()
    print(f"chunk_tag: done in {time.time() - t0:.0f}s; {len(gone)} stale removed; {len(failed)} failed (untagged)")
    for cid, err in failed[:10]:
        print(f"  failed {cid}: {err}")
    for tag, n, conf in dist:
        print(f"  {n:6d}  mean confidence {conf}  {tag}")
    con.close()
    return len(todo) - len(failed)


if __name__ == "__main__":
    build()
