"""Passage and query embeddings for semantic retrieval. The model is configuration, not code (as in procintel.core.llm).

Environment:
  PROCINTEL_EMBED_MODEL     LiteLLM model string, e.g. openai/embeddinggemma-2 for a local llama.cpp server:
                              llama-server -m embeddinggemma-2-Q8_0.gguf --embedding --alias embeddinggemma-2 \
                                --host 127.0.0.1 --port 8081 -c 8192 -b 2048 -ub 2048 -np 4
  PROCINTEL_EMBED_API_BASE  e.g. http://127.0.0.1:8081/v1
  PROCINTEL_EMBED_API_KEY   optional; a local server ignores it
  PROCINTEL_EMBED_DIM       stored dimensions, default 256 (EmbeddingGemma is trained for truncation to 768/512/256/128;
                            its model card reports 256 as close to lossless)

If PROCINTEL_EMBED_MODEL is unset, `available()` is False and retrieval is keyword-only (BM25).

    python -m procintel.core.embed        # embeds new or changed chunks into table chunk_vec
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import duckdb
import numpy as np

from procintel.core import db, paths

DB_PATH = paths.DB_PATH
BATCH = 64

# EmbeddingGemma is trained with a task prefix (google/embeddinggemma-2 model card, "Prompt Instructions");
# llama-server does not add it, and leaving it out lowers retrieval quality without any error.
_PROMPTS = {
    "embeddinggemma": ("task: question answering | query: {text}", "title: {title} | text: {text}"),
}


def model_name() -> str | None:
    return os.environ.get("PROCINTEL_EMBED_MODEL") or None


def available() -> bool:
    return model_name() is not None


def dim() -> int:
    return int(os.environ.get("PROCINTEL_EMBED_DIM", "256"))


def _prompts() -> tuple[str, str]:
    m = (model_name() or "").lower()
    return next((p for key, p in _PROMPTS.items() if key in m), ("{text}", "{text}"))


def format_query(q: str) -> str:
    return _prompts()[0].format(text=q)


def format_document(text: str, title: str | None) -> str:
    return _prompts()[1].format(text=text, title=title or "none")


def embed(texts: list[str]) -> np.ndarray:
    """Unit vectors, one row per text, truncated to dim() and renormalised. Texts must already be formatted."""
    m = model_name()
    if m is None:
        raise RuntimeError("PROCINTEL_EMBED_MODEL is not set")
    import litellm  # imported lazily: slow to import, not needed when embeddings are off

    out = []
    for i in range(0, len(texts), BATCH):
        resp = litellm.embedding(model=m, input=texts[i:i + BATCH], api_base=os.environ.get("PROCINTEL_EMBED_API_BASE"),
                                 api_key=os.environ.get("PROCINTEL_EMBED_API_KEY") or "local")
        out.extend(d["embedding"] for d in sorted(resp.data, key=lambda d: d["index"]))
    v = np.asarray(out, dtype=np.float32)
    if v.shape[0] != len(texts):
        raise RuntimeError(f"embedding server returned {v.shape[0]} vectors for {len(texts)} texts")
    if v.shape[1] < dim():
        raise RuntimeError(f"model returns {v.shape[1]} dimensions, fewer than PROCINTEL_EMBED_DIM={dim()}")
    v = v[:, :dim()]
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def text_hash(section: str, text: str) -> str:
    return hashlib.sha256(f"{section}\x00{text}".encode()).hexdigest()[:16]


def build(db_path: Path = DB_PATH) -> int:
    """Number of chunks embedded. Embed every chunk whose (model, dim, text hash) is not stored yet; drop vectors of chunks that no longer exist."""
    m, d = model_name(), dim()
    if m is None:
        raise SystemExit("set PROCINTEL_EMBED_MODEL (and PROCINTEL_EMBED_API_BASE) first")
    con = db.connect(db_path)
    con.execute("""CREATE TABLE IF NOT EXISTS chunk_vec (
        chunk_id VARCHAR, model VARCHAR, dim INTEGER, text_hash VARCHAR, vec FLOAT[])""")
    chunks = con.execute("SELECT chunk_id, section, text FROM chunk").fetchall()
    have = {(cid, h) for cid, h in con.execute(
        "SELECT chunk_id, text_hash FROM chunk_vec WHERE model = ? AND dim = ?", [m, d]).fetchall()}
    todo = [(cid, s, t, text_hash(s, t)) for cid, s, t in chunks if (cid, text_hash(s, t)) not in have]
    print(f"chunk_vec: {len(chunks) - len(todo)} up to date, {len(todo)} to embed with {m} (dim {d})")
    t0 = time.time()
    for i in range(0, len(todo), 1024):
        part = todo[i:i + 1024]
        vecs = embed([format_document(t, s) for _, s, t, _ in part])
        ids = [cid for cid, *_ in part]
        con.execute("DELETE FROM chunk_vec WHERE model = ? AND dim = ? AND chunk_id IN (SELECT unnest(?))", [m, d, ids])
        con.executemany("INSERT INTO chunk_vec VALUES (?, ?, ?, ?, ?)",
                        [(cid, m, d, h, v.tolist()) for (cid, _, _, h), v in zip(part, vecs)])
        print(f"  {i + len(part)}/{len(todo)}  {time.time() - t0:.0f}s")
    gone = con.execute("DELETE FROM chunk_vec WHERE chunk_id NOT IN (SELECT chunk_id FROM chunk) RETURNING 1").fetchall()
    n = con.execute("SELECT count(*) FROM chunk_vec WHERE model = ? AND dim = ?", [m, d]).fetchone()[0]
    print(f"chunk_vec: {n} vectors for {m}; {len(gone)} stale removed; {time.time() - t0:.0f}s")
    con.close()
    return len(todo)


def build_packages(db_path: Path = DB_PATH) -> int:
    """Embed the description of every awarded package (table package_vec), only new or changed ones; returns how many
    were embedded. Used to show planners the most similar past contracts and how they went."""
    m, d = model_name(), dim()
    if m is None:
        raise SystemExit("set PROCINTEL_EMBED_MODEL (and PROCINTEL_EMBED_API_BASE) first")
    con = db.connect(db_path)
    con.execute("""CREATE TABLE IF NOT EXISTS package_vec (
        package_id VARCHAR, model VARCHAR, dim INTEGER, text_hash VARCHAR, vec FLOAT[])""")
    rows = con.execute("""SELECT package_id, proc_group, description FROM package
                          WHERE description IS NOT NULL AND (award_date IS NOT NULL OR price_amount IS NOT NULL)""").fetchall()
    have = {(p, h) for p, h in con.execute("SELECT package_id, text_hash FROM package_vec WHERE model = ? AND dim = ?", [m, d]).fetchall()}
    todo = [(p, text_hash(g or "", t), t) for p, g, t in rows if (p, text_hash(g or "", t)) not in have]
    print(f"package_vec: {len(rows) - len(todo)} up to date, {len(todo)} to embed")
    for i in range(0, len(todo), 1024):
        part = todo[i:i + 1024]
        vecs = embed([format_document(t, None) for _, _, t in part])
        con.execute("DELETE FROM package_vec WHERE model = ? AND dim = ? AND package_id IN (SELECT unnest(?))",
                    [m, d, [p for p, _, _ in part]])
        con.executemany("INSERT INTO package_vec VALUES (?, ?, ?, ?, ?)", [(p, m, d, h, v.tolist()) for (p, h, _), v in zip(part, vecs)])
    con.execute("DELETE FROM package_vec WHERE package_id NOT IN (SELECT package_id FROM package)")
    con.close()
    return len(todo)


def load(con: duckdb.DuckDBPyConnection, chunk_ids: list[str], chunk_table: str = "chunk",
         vec_table: str = "chunk_vec") -> np.ndarray | None:
    """Matrix aligned with chunk_ids for the configured model and dim, or None if any chunk lacks a current vector.
    The table names select a shadow build (procintel.learning.shadows) instead of the live index."""
    m, d = model_name(), dim()
    if m is None or not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = ?", [vec_table]).fetchone():
        return None
    rows = dict(con.execute(f"""SELECT v.chunk_id, v.vec FROM {vec_table} v JOIN {chunk_table} c USING (chunk_id)
        WHERE v.model = ? AND v.dim = ? AND v.text_hash = sha256(c.section || chr(0) || c.text)[:16]""", [m, d]).fetchall())
    if len(rows) < len(chunk_ids):
        return None
    return np.asarray([rows[c] for c in chunk_ids], dtype=np.float32)


if __name__ == "__main__":
    build()
    build_packages()
