"""One command that brings everything up to date with the World Bank sources and logs what changed.

    python -m procintel.refresh                # fetch new listings, then rebuild what depends on them
    python -m procintel.refresh --skip-fetch   # rebuild from the data already in the database

Steps: ingest (listings re-fetched, existing ICRs kept, document texts cached) → model tables → chunks → embeddings
(new or changed passages only) → tags (same) → ICR/ISR rating check → prediction models (retrained, metrics compared)
→ evaluation report (retrieval metrics and user feedback; eval/report.md, eval/history.jsonl).
Embedding and tagging are the slow steps and are incremental; the others rebuild in seconds to a minute.
Each run appends a row to table refresh_log with the changes and per-step times. A running backend keeps its old
data in memory until it is restarted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from procintel import (chunk, decide, embed, evidence, fx, ingest, llm, model, predict, problem_tag,
                       procurement_rating, ratings, tag)

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "procintel.duckdb"


def snapshot(db_path: Path = DB_PATH) -> dict:
    """What the change log compares: document text hashes, notice ids, project statuses, sizes, model metrics."""
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        docs = {d: hashlib.sha256(t.encode()).hexdigest()[:16] for d, t in con.execute("SELECT doc_id, text FROM documents").fetchall()}
        notices = {n for (n,) in con.execute("SELECT notice_id FROM notices").fetchall()}
        status = dict(con.execute("SELECT project_id, coalesce(status, '') FROM projects").fetchall())
        labelled = con.execute("SELECT count(*) FROM package WHERE tender_to_award_days IS NOT NULL").fetchone()[0]
        chunks = con.execute("SELECT count(*) FROM chunk").fetchone()[0]
    finally:
        con.close()
    bundle = predict.load()
    return {"docs": docs, "notices": notices, "status": status, "labelled_packages": labelled, "chunks": chunks,
            "model": {k: v[0] for k, v in bundle["metrics"].items() if isinstance(v, tuple)} if bundle else {}}


def diff(before: dict, after: dict) -> dict:
    b, a = before["docs"], after["docs"]
    return {
        "documents_added": sorted(set(a) - set(b)),
        "documents_changed": sorted(d for d in set(a) & set(b) if a[d] != b[d]),
        "documents_removed": sorted(set(b) - set(a)),
        "notices_added": len(after["notices"] - before["notices"]),
        "notices_removed": len(before["notices"] - after["notices"]),
        "projects_status_changed": sorted(p for p in set(after["status"]) & set(before["status"])
                                          if after["status"][p] != before["status"][p]),
        "labelled_packages": [before["labelled_packages"], after["labelled_packages"]],
        "chunks": [before["chunks"], after["chunks"]],
        "model_metrics": {k: [before["model"].get(k), after["model"].get(k)] for k in after["model"]},
    }


def run(n_icrs: int = 120, fetch: bool = True, db_path: Path = DB_PATH) -> dict:
    started = datetime.now(timezone.utc)
    before = snapshot(db_path)
    steps: list[tuple[str, float]] = []
    counts: dict[str, int] = {}

    def step(name, fn):
        t = time.time()
        print(f"== {name}", flush=True)
        out = fn()
        steps.append((name, round(time.time() - t, 1)))
        return out

    status, error = "ok", None
    try:
        if fetch:
            step("ingest (fresh listings, keep existing ICRs)", lambda: ingest.run(n_icrs, fresh=True, keep_existing=True))
        step("model tables", model.build)
        step("chunks", chunk.build)
        if embed.available():
            counts["embedded"] = step("embeddings (new or changed passages)", embed.build)
            counts["packages_embedded"] = step("package description embeddings", embed.build_packages)
        if decide.available():
            counts["tagged"] = step("tags (new or changed passages)", tag.build)
        if decide.available() and llm.available():
            counts["problems_tagged"] = step("two-step problem tags (new or changed passages)", problem_tag.build)
        step("ICR / ISR rating check", ratings.build)
        step("ICR procurement rating check", procurement_rating.build)
        step("re-bid and amendment evidence", lambda: evidence.build(evidence.KINDS))
        if fetch:
            step("exchange rates", fx.build)
        step("prediction models", predict.main)
        # retrieval metrics + user feedback; answering every question takes ~10 min, run `evaluate run` for that
        counts["evaluation"] = step("evaluation report (retrieval + feedback)", lambda: _evaluate())
    except Exception as e:  # record the failed step, then re-raise so the command exits non-zero
        status, error = "failed", f"{type(e).__name__}: {e}"
    after = snapshot(db_path) if status == "ok" else before
    changes = diff(before, after) | counts
    con = duckdb.connect(str(db_path))
    con.execute("""CREATE TABLE IF NOT EXISTS refresh_log (started_at TIMESTAMP, finished_at TIMESTAMP, status VARCHAR,
        fetched BOOLEAN, steps JSON, changes JSON, error VARCHAR)""")
    con.execute("INSERT INTO refresh_log VALUES (?, ?, ?, ?, ?, ?, ?)",
                [started.replace(tzinfo=None), datetime.now(timezone.utc).replace(tzinfo=None), status, fetch,
                 json.dumps(steps), json.dumps(changes), error])
    con.close()
    _print(changes, steps, status, error)
    if error:
        raise SystemExit(1)
    return changes


def _evaluate() -> int:
    from procintel import evaluate  # imported here: it loads the retriever, which reads the refreshed tables
    from procintel.retrieve import Retriever
    evaluate.report(Retriever(), answers=False)
    return 1


def _print(changes: dict, steps: list, status: str, error: str | None) -> None:
    print(f"\nrefresh {status}" + (f": {error}" if error else ""))
    for name, secs in steps:
        print(f"  {secs:7.1f}s  {name}")
    c = changes
    print(f"documents: +{len(c['documents_added'])} changed {len(c['documents_changed'])} removed {len(c['documents_removed'])}; "
          f"notices: +{c['notices_added']} -{c['notices_removed']}; project status changes: {len(c['projects_status_changed'])}")
    print(f"labelled packages {c['labelled_packages'][0]} -> {c['labelled_packages'][1]}; chunks {c['chunks'][0]} -> {c['chunks'][1]}; "
          f"embedded {c.get('embedded', '-')}, tagged {c.get('tagged', '-')}")
    for k, (b, a) in c["model_metrics"].items():
        print(f"  {k:20s} {b if b is None else round(b, 3)} -> {round(a, 3)}")
    print("restart the backend to serve the refreshed data")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--icrs", type=int, default=120, help="how many of the newest ICRs to list (already-known ones are kept)")
    ap.add_argument("--skip-fetch", action="store_true", help="rebuild from data already in the database")
    a = ap.parse_args()
    run(a.icrs, fetch=not a.skip_fetch)
