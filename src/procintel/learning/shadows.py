"""Shadow builds: an alternative index built next to the live one, compared on the evaluation set, and switched in
only when someone promotes it (docs/event-pipeline-design.md 6c).

A shadow is a registered alternative (SHADOWS). Its build runs as a background job, step by step and resumable; it
writes tables named <live table>__<shadow> (chunk__semantic, chunk_vec__semantic) and chunk_parent__<shadow>, which
names for every new passage the live passages it was made from, so the evaluation labels (which name live passages)
score both indexes. The evaluation compares search quality of live and shadow; promote swaps the tables in and keeps
the old ones as <table>__previous; the promotion is recorded in table shadow, which later builds read (a promoted
semantic shadow makes procintel.ingestion.chunk build semantic passages from then on); discard drops the shadow tables.

    python -m procintel.learning.shadows build semantic | evaluate semantic | promote semantic | discard semantic
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterator

from procintel.core import db, embed
from procintel.ingestion import semantic_chunk

BATCH = 25  # paragraphs per job step (each step embeds their sentences, about 10 s)


@dataclass
class Shadow:
    name: str
    label: str
    build: Callable[[dict | None], Iterator[dict]]
    tables: tuple[str, ...]           # live tables this shadow replaces when promoted


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _state_table(con) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS shadow (name VARCHAR PRIMARY KEY, status VARCHAR, built_at TIMESTAMP,
                   evaluated_at TIMESTAMP, metrics VARCHAR, note VARCHAR)""")
    con.execute("ALTER TABLE shadow ADD COLUMN IF NOT EXISTS promoted_at TIMESTAMP")  # retention of __previous tables


def set_state(name: str, **fields) -> None:
    con = db.connect()
    try:
        _state_table(con)
        if not con.execute("SELECT 1 FROM shadow WHERE name = ?", [name]).fetchone():
            con.execute("INSERT INTO shadow (name, status) VALUES (?, 'building')", [name])
        for k, v in fields.items():
            con.execute(f"UPDATE shadow SET {k} = ? WHERE name = ?", [json.dumps(v) if k == "metrics" else v, name])
    finally:
        con.close()


def states() -> list[dict]:
    from procintel.core import paths
    if db.backend() == "duckdb" and not paths.DB_PATH.exists():
        return []
    con = db.connect(read_only=True)
    try:
        if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'shadow'").fetchone():
            return []
        q = con.execute("SELECT * FROM shadow ORDER BY name")
        cols = [d[0] for d in q.description]
        out = []
        for r in q.fetchall():
            d = dict(zip(cols, r))
            d["metrics"] = json.loads(d["metrics"]) if d["metrics"] else None
            for k in ("built_at", "evaluated_at", "promoted_at"):
                d[k] = d[k].isoformat() + "Z" if d.get(k) else None
            d["label"] = SHADOWS[d["name"]].label if d["name"] in SHADOWS else d["name"]
            out.append(d)
        return out
    finally:
        con.close()


# --- semantic chunking ---------------------------------------------------------------------------------------------

def build_semantic(cursor: dict | None) -> Iterator[dict]:
    """Step 1: embed the sentences of every over-long paragraph (cached), BATCH paragraphs per step. Step 2: write
    chunk__semantic with those paragraphs re-split, chunk_parent__semantic, and the passage vectors (cached)."""
    con = db.connect(read_only=True)
    try:
        n = len(semantic_chunk.groups(con))
    finally:
        con.close()
    start = (cursor or {}).get("group", 0)
    if start == 0:
        set_state("semantic", status="building", note=f"{n} over-long paragraphs to re-split")
    for i in range(start, n, BATCH):
        con = db.connect()
        try:
            for g in semantic_chunk.groups(con)[i:i + BATCH]:
                semantic_chunk.resplit(con, g)
        finally:
            con.close()
        yield {"stage": "sentences", "group": min(i + BATCH, n), "of": n}
    con = db.connect()
    try:
        summary = _write_semantic(con)
    finally:
        con.close()
    set_state("semantic", status="built", built_at=_now(), note=summary)
    yield {"stage": "written", "group": n, "of": n}


def _write_semantic(con) -> str:
    summary = semantic_chunk.write_table(con, "chunk__semantic", "chunk_parent__semantic")
    _write_vectors(con, "chunk__semantic", "chunk_vec__semantic")
    return summary


def _write_vectors(con, chunk_table: str, vec_table: str) -> None:
    """Vectors for the shadow's passages: the live vector where the text is unchanged, else from the cache/server."""
    m, d = embed.model_name(), embed.dim()
    con.execute(f"CREATE OR REPLACE TABLE {vec_table} (chunk_id VARCHAR, model VARCHAR, dim INTEGER, "
                "text_hash VARCHAR, vec FLOAT[])")
    con.execute(f"""INSERT INTO {vec_table} SELECT v.* FROM chunk_vec v JOIN {chunk_table} c USING (chunk_id)
                    WHERE v.model = ? AND v.dim = ? AND v.text_hash = sha256(c.section || chr(0) || c.text)[:16]""",
                [m, d])
    todo = con.execute(f"""SELECT chunk_id, section, text FROM {chunk_table}
                           WHERE chunk_id NOT IN (SELECT chunk_id FROM {vec_table})""").fetchall()
    for i in range(0, len(todo), 256):
        part = todo[i:i + 256]
        vecs = semantic_chunk.cached_vectors(con, [embed.format_document(t, s) for _, s, t in part])
        con.executemany(f"INSERT INTO {vec_table} VALUES (?, ?, ?, ?, ?)",
                        [(cid, m, d, embed.text_hash(s, t), v.tolist()) for (cid, s, t), v in zip(part, vecs)])


SHADOWS: dict[str, Shadow] = {
    "semantic": Shadow("semantic", "Semantic chunking of over-long paragraphs", build_semantic,
                       tables=("chunk", "chunk_vec")),
}


# --- evaluation, promotion ------------------------------------------------------------------------------------------

def parents_of(name: str | None) -> dict[str, list[str]]:
    """New passage id -> the live passage ids it was made from (empty for the live index without a promoted shadow)."""
    table = f"chunk_parent__{name}" if name else "chunk_parent"
    con = db.connect(read_only=True)
    try:
        if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = ?", [table]).fetchone():
            return {}
        out: dict[str, list[str]] = {}
        for cid, parent in con.execute(f"SELECT chunk_id, parent_id FROM {table}").fetchall():
            out.setdefault(cid, []).append(parent)
        return out
    finally:
        con.close()


def evaluate_shadow(name: str, live=None) -> dict:
    """Search quality of the live index and of the shadow on the evaluation questions (procintel.learning.evaluate)."""
    from procintel.answering.retrieve import Retriever  # imported here: building a retriever loads the index
    from procintel.learning import evaluate
    live = live or Retriever()
    shadow = Retriever(chunk_table=f"chunk__{name}", vec_table=f"chunk_vec__{name}")
    out = {"live": evaluate.retrieval_metrics(live, parents_of(None)),
           "shadow": evaluate.retrieval_metrics(shadow, parents_of(name)),
           "passages": {"live": len(live.records), "shadow": len(shadow.records)}}
    set_state(name, status="evaluated", evaluated_at=_now(), metrics=out)
    return out


def promote(name: str) -> str:
    """Swap the shadow's tables in (old ones kept as <table>__previous) and record the promotion."""
    s = SHADOWS[name]
    con = db.connect()
    try:
        for t in s.tables:
            con.execute(f"DROP TABLE IF EXISTS {t}__previous")
            con.execute(f"ALTER TABLE {t} RENAME TO {t}__previous")
            con.execute(f"ALTER TABLE {t}__{name} RENAME TO {t}")
        con.execute(f"CREATE OR REPLACE TABLE chunk_parent AS SELECT * FROM chunk_parent__{name}")
        con.execute(f"DROP TABLE chunk_parent__{name}")
    finally:
        con.close()
    set_state(name, status="promoted", promoted_at=_now(),
              note=f"promoted {_now():%Y-%m-%d %H:%M} UTC; previous tables kept as __previous")
    return name


def discard(name: str) -> str:
    con = db.connect()
    try:
        for t in SHADOWS[name].tables:
            con.execute(f"DROP TABLE IF EXISTS {t}__{name}")
        con.execute(f"DROP TABLE IF EXISTS chunk_parent__{name}")
    finally:
        con.close()
    set_state(name, status="discarded")
    return name


if __name__ == "__main__":
    import sys
    action, name = sys.argv[1], sys.argv[2]
    if action == "build":
        for c in SHADOWS[name].build(None):
            print(c, flush=True)
    elif action == "evaluate":
        print(json.dumps(evaluate_shadow(name), indent=1))
    elif action == "promote":
        print("promoted", promote(name))
    elif action == "discard":
        print("discarded", discard(name))
