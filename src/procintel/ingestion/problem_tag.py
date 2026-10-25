"""Two-step problem tags for ICR passages: does the passage describe a problem that happened in the project, and if so
which kind. Asked of the answer LLM, only for passages the decision-model tagger (procintel.ingestion.tag) did not mark "none of
these", since the LLM takes about 3.6 s per passage and that tagger rarely misses a problem.

Measured on 60 passages labelled by hand (30 random, 30 the decision-model tagger marked as a problem; 19 describe a
problem; 2026-10-25):

    problem described?                    precision  recall      type right (10 of the 6 named kinds)
    decision model, one step              0.44       0.79        8
    decision model, two steps (p >= .5)   0.52       0.74        6
    answer LLM, two steps                 0.94       0.79        10
    decision-model prefilter + LLM        0.93       0.68        (as above)
    answer LLM, one combined question     0.91       0.53        9

Full run (2026-10-25, 3,153 passages in 2.6 h): 1,378 describe a problem. Hand check of 30 random results: the
problem/no-problem call was right on 29 (one missed problem), but the kind was right on only 8 of the 13 problems that
could be judged ("funding or payment delays" was given to slow disbursement and procurement delays, fiduciary
weaknesses got a contractor label). So only the problem/no-problem call is shown in the app; the kind is stored.

Stored in table chunk_problem (chunk_id, model, text_hash, problem, kind); re-runs tag only new or changed passages.

    python -m procintel.ingestion.problem_tag      # needs PROCINTEL_LLM_MODEL and a built chunk_tag table
"""
from __future__ import annotations

import time
from pathlib import Path

from procintel.core import db, llm, paths, prompts
from procintel.core.embed import text_hash
from procintel.ingestion.tag import NONE, TAGS

DB_PATH = paths.DB_PATH
KINDS = TAGS[:-1] + ["another kind of problem"]


def classify(text: str) -> tuple[bool, str | None]:
    """(describes a problem, which kind or None if unknown). Raises on an unusable first reply."""
    a = llm.complete(prompts.get("problem_check"), text, max_tokens=4).strip().lower()
    if not a.startswith(("yes", "no")):
        raise RuntimeError(f"step 1 replied {a!r}")
    if a.startswith("no"):
        return False, None
    try:
        b = llm.complete(prompts.get("problem_kind", kinds="; ".join(KINDS)), text, max_tokens=20).strip().lower().rstrip(".")
    except RuntimeError:  # the kind reply ran on past the limit (seen on 1 of 3,154 passages): the problem call stands
        return True, None
    return True, next((k for k in KINDS if k in b), "another kind of problem")


def build(db_path: Path = DB_PATH) -> int:
    """Number of passages tagged now (new or changed text among those the decision model marked as a problem)."""
    if not llm.available():
        raise SystemExit("set PROCINTEL_LLM_MODEL first")
    m = llm.model_name()
    con = db.connect(db_path)
    con.execute("""CREATE TABLE IF NOT EXISTS chunk_problem (
        chunk_id VARCHAR, model VARCHAR, text_hash VARCHAR, problem BOOLEAN, kind VARCHAR)""")
    candidates = con.execute("""SELECT c.chunk_id, c.section, c.text FROM chunk c JOIN chunk_tag t USING (chunk_id)
                                WHERE c.kind = 'text' AND t.tag <> ?""", [NONE]).fetchall()
    have = {(c, h) for c, h in con.execute("SELECT chunk_id, text_hash FROM chunk_problem WHERE model = ?", [m]).fetchall()}
    todo = [(c, text_hash(s, t), t) for c, s, t in candidates if (c, text_hash(s, t)) not in have]
    con.close()  # not held during the hours-long run: DuckDB allows one writer, and the backend must keep reading
    print(f"chunk_problem: {len(candidates) - len(todo)} up to date, {len(todo)} to tag with {m}", flush=True)
    t0, failed, rows = time.time(), 0, []
    for i, (cid, h, text) in enumerate(todo, 1):
        try:
            problem, kind = classify(text)
        except Exception:  # one bad reply or a timeout must not stop a multi-hour run; the passage is retried next time
            failed += 1
            continue
        rows.append((cid, m, h, problem, kind))
        if i % 100 == 0:
            print(f"  {i}/{len(todo)}  {time.time() - t0:.0f}s", flush=True)
    if rows:  # nothing to write when every passage failed (or none was due)
        con = db.connect(db_path)
        con.executemany("DELETE FROM chunk_problem WHERE chunk_id = ? AND model = ?", [(r[0], r[1]) for r in rows])
        con.executemany("INSERT INTO chunk_problem VALUES (?, ?, ?, ?, ?)", rows)
        con.close()
    print(f"done in {time.time() - t0:.0f}s; {failed} failed (retried on the next run)", flush=True)
    return len(todo) - failed


if __name__ == "__main__":
    build()
