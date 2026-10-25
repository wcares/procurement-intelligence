"""What user feedback asks for, built by the "feedback_review" background job (procintel.jobs) in idle time.

Tables in data/feedback.duckdb, rebuilt from the full feedback log on every run:

  review_items        one row per thing a person should look at: a citation flagged as wrong (with how many separate
                      responses flagged it and on which question), a question the system refused, a response rated
                      "not useful". These are the candidates for the evaluation set; a person labels them.
  demoted_citations   passages flagged as a wrong citation on at least DEMOTE_MIN separate responses. Search moves
                      them to the end of its results: they stay retrievable, because a passage wrong for one question
                      can be right for another and one click can be a mistake.

    python -m procintel.learning.feedback_review
"""
from __future__ import annotations

import json
from pathlib import Path

from procintel.core import db
from procintel.learning import feedback

DEMOTE_MIN = 2  # separate responses that must flag a passage before search demotes it (Settings page)


def _question(kind: str, request: str) -> str:
    r = json.loads(request)
    if kind == "ask":
        return r.get("question", "")
    return " · ".join(str(r.get(k)) for k in ("countryCode", "procGroup", "methodCode", "description") if r.get(k))


def build(db_path: Path | None = None) -> dict:
    """Rebuild review_items and demoted_citations; returns counts and the demoted chunk ids."""
    path = db_path or feedback.DB_PATH
    with feedback._LOCK:
        con = feedback._connect(path)
        try:
            log = {rid: (kind, req, json.loads(resp), at) for rid, kind, req, resp, at in
                   con.execute("SELECT response_id, kind, request, response, created_at FROM response_log").fetchall()}
            rows = con.execute("""SELECT response_id, rating, citation_id, comment, created_at FROM feedback
                                  ORDER BY created_at""").fetchall()
            items: dict[tuple[str, str], dict] = {}

            def add(kind: str, key: str, question: str, comment: str | None, at, response_id: str) -> None:
                it = items.setdefault((kind, key), {"kind": kind, "key": key, "responses": set(), "questions": [],
                                                    "comments": [], "last_at": at})
                it["responses"].add(response_id)
                if question and question not in it["questions"]:
                    it["questions"].append(question)
                if comment:
                    it["comments"].append(comment)
                it["last_at"] = max(it["last_at"], at)

            for rid, rating, cid, comment, at in rows:
                if rid not in log:
                    continue
                kind, req, _, _ = log[rid]
                q = _question(kind, req)
                if rating == "bad_citation":
                    add("flagged_citation", cid, q, comment, at, rid)
                elif rating == "not_useful":
                    add("not_useful", q.lower().strip(), q, comment, at, rid)
            for rid, (kind, req, resp, at) in log.items():
                if kind == "ask" and resp.get("unsupported"):
                    q = _question(kind, req)
                    add("refused_question", q.lower().strip(), q, None, at, rid)

            con.execute("""CREATE OR REPLACE TABLE review_items (kind VARCHAR, key VARCHAR, n_responses INTEGER,
                           questions JSON, comments JSON, last_at TIMESTAMP)""")
            rows_out = [(it["kind"], it["key"], len(it["responses"]), json.dumps(it["questions"][:5]),
                         json.dumps(it["comments"][:5]), it["last_at"]) for it in items.values()]
            if rows_out:  # executemany refuses an empty list
                con.executemany("INSERT INTO review_items VALUES (?, ?, ?, ?, ?, ?)", rows_out)
            demoted = sorted(it["key"] for it in items.values()
                             if it["kind"] == "flagged_citation" and len(it["responses"]) >= DEMOTE_MIN)
            con.execute("CREATE OR REPLACE TABLE demoted_citations (chunk_id VARCHAR, n_responses INTEGER)")
            if demoted:
                con.executemany("INSERT INTO demoted_citations VALUES (?, ?)",
                                [(c, len(items[("flagged_citation", c)]["responses"])) for c in demoted])
        finally:
            con.close()
    counts = {k: sum(1 for it in items.values() if it["kind"] == k)
              for k in ("flagged_citation", "refused_question", "not_useful")}
    return {"items": counts, "demoted": demoted}


def load_demoted(db_path: Path | None = None) -> set[str]:
    path = db_path or feedback.DB_PATH
    if not Path(path).exists():
        return set()
    con = db.connect(path, read_only=True)
    try:
        if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'demoted_citations'").fetchone():
            return set()
        return {c for (c,) in con.execute("SELECT chunk_id FROM demoted_citations").fetchall()}
    finally:
        con.close()


def items(db_path: Path | None = None, limit: int = 50) -> list[dict]:
    path = db_path or feedback.DB_PATH
    if not Path(path).exists():
        return []
    con = db.connect(path, read_only=True)
    try:
        if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'review_items'").fetchone():
            return []
        q = con.execute("""SELECT kind, key, n_responses, questions, comments FROM review_items
                           ORDER BY n_responses DESC, last_at DESC NULLS LAST LIMIT ?""", [limit])
        return [{"kind": k, "key": key, "responses": n, "questions": json.loads(qs), "comments": json.loads(cs)}
                for k, key, n, qs, cs in q.fetchall()]
    finally:
        con.close()


if __name__ == "__main__":
    print(build())
