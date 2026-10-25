"""Semantic chunking: paragraphs too long for one passage are cut where the topic shifts, not wherever the size limit
falls (docs/event-pipeline-design.md 6c).

The size chunker (procintel.ingestion.chunk) splits a paragraph over MAX_CHARS at the sentence end nearest the limit.
Here the paragraph's sentences are embedded (EmbeddingGemma, procintel.core.embed) and a cut is placed at a low
similarity between neighbouring sentences once a piece is at least half full; the size limit still applies. Short
paragraphs and tables are unchanged. Every new piece records the size-chunker passages it came from (its parents), so
the evaluation labels, which name those passages, still apply.

Vectors are cached by a hash of the embedded text (table text_vec), so a build that pauses or restarts embeds nothing
twice.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field

import numpy as np

from procintel.core import embed
from procintel.ingestion.chunk import MAX_CHARS, _split_words

SENTENCE = re.compile(r"(?<=[.;])\s+(?=[A-Z0-9])")  # the size chunker's sentence boundary
LOW_QUANTILE = 0.25   # a boundary counts as a topic shift when its similarity is in the paragraph's lowest quarter
MIN_FILL = 0.5        # cut at a topic shift only once the piece holds half the size limit (keeps pieces substantial)
MIN_PIECE = 200       # a last piece shorter than this joins the one before when both fit in the size limit


@dataclass
class Group:
    """One over-long paragraph: the size chunker's passages for it, in order."""
    doc_id: str
    section: str
    para: str
    chunk_ids: list[str]
    texts: list[str]


@dataclass
class Piece:
    text: str
    parents: list[str] = field(default_factory=list)


def sentences(text: str) -> list[str]:
    out = []
    for s in SENTENCE.split(text):
        out.extend(_split_words(s, MAX_CHARS) if len(s) > MAX_CHARS else [s])
    return [s for s in out if s.strip()]


def split(sents: list[str], owners: list[str], vecs: np.ndarray, limit: int = MAX_CHARS) -> list[Piece]:
    """Cut a paragraph's sentences into pieces of at most `limit` characters, preferring low-similarity boundaries."""
    sims = np.einsum("ij,ij->i", vecs[:-1], vecs[1:]) if len(sents) > 1 else np.array([])
    low = float(np.quantile(sims, LOW_QUANTILE)) if len(sims) else 0.0
    pieces: list[Piece] = []
    cur: list[int] = []
    for i, s in enumerate(sents):
        if cur:
            length = len(" ".join(sents[j] for j in cur))
            if length + 1 + len(s) > limit or (length >= MIN_FILL * limit and sims[i - 1] <= low):
                pieces.append(_piece(cur, sents, owners))
                cur = []
        cur.append(i)
    if cur:
        tail = " ".join(sents[i] for i in cur)
        if pieces and len(tail) < MIN_PIECE and len(pieces[-1].text) + 1 + len(tail) <= limit:
            prev = pieces.pop()
            pieces.append(Piece(f"{prev.text} {tail}", list(dict.fromkeys(prev.parents + [owners[i] for i in cur]))))
        else:
            pieces.append(_piece(cur, sents, owners))
    return pieces


def _piece(idx: list[int], sents: list[str], owners: list[str]) -> Piece:
    return Piece(" ".join(sents[i] for i in idx), list(dict.fromkeys(owners[i] for i in idx)))


def groups(con) -> list[Group]:
    """Paragraphs the size chunker split into more than one text passage."""
    rows = con.execute("""
        SELECT doc_id, section, para, list(chunk_id ORDER BY seq), list(text ORDER BY seq)
        FROM chunk WHERE kind = 'text' AND para IS NOT NULL
        GROUP BY doc_id, section, para HAVING count(*) > 1 ORDER BY doc_id, min(seq)""").fetchall()
    return [Group(d, s, p, ids, texts) for d, s, p, ids, texts in rows]


# --- vector cache -------------------------------------------------------------------------------------------------

def _key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def ensure_cache(con) -> None:
    con.execute("CREATE TABLE IF NOT EXISTS text_vec (key VARCHAR, model VARCHAR, dim INTEGER, vec FLOAT[])")


def cached_vectors(con, texts: list[str]) -> np.ndarray:
    """Vectors for already formatted texts, embedding only those not in the cache."""
    ensure_cache(con)
    m, d = embed.model_name(), embed.dim()
    keys = [_key(t) for t in texts]
    have = dict(con.execute("SELECT key, vec FROM text_vec WHERE model = ? AND dim = ? AND key IN (SELECT unnest(?))",
                            [m, d, list(set(keys))]).fetchall())
    todo = list(dict.fromkeys(t for t, k in zip(texts, keys) if k not in have))
    if todo:
        new = embed.embed(todo)
        rows = [(_key(t), m, d, v.tolist()) for t, v in zip(todo, new)]
        con.executemany("INSERT INTO text_vec VALUES (?, ?, ?, ?)", rows)
        have.update({k: v for k, _, _, v in rows})
    return np.asarray([have[k] for k in keys], dtype=np.float32)


def resplit(con, g: Group) -> list[Piece]:
    """The group's text cut at topic shifts (sentence vectors from the cache or the embedding server)."""
    sents, owners = [], []
    for cid, text in zip(g.chunk_ids, g.texts):
        for s in sentences(text):
            sents.append(s)
            owners.append(cid)
    vecs = cached_vectors(con, [embed.format_document(s, None) for s in sents])
    return split(sents, owners, vecs)


def write_table(con, target: str, parent_table: str) -> str:
    """Write the passages of table chunk with every over-long paragraph re-split into `target` (same columns), and
    each new passage's parents into `parent_table`; returns a summary. Vectors come from the cache or the server."""
    gs = groups(con)
    replaced = {cid: g for g in gs for cid in g.chunk_ids}
    rows, parents = [], []
    done: set[int] = set()
    live = con.execute("SELECT chunk_id, doc_id, seq, section, para, kind, text FROM chunk ORDER BY doc_id, seq").fetchall()
    for cid, doc, _seq, section, para, kind, text in live:
        g = replaced.get(cid)
        if g is None:
            rows.append([cid, doc, section, para, kind, text])
            continue
        if id(g) in done:
            continue
        done.add(id(g))
        for k, p in enumerate(resplit(con, g)):
            pid = f"{g.chunk_ids[0]}s{k}"
            rows.append([pid, doc, section, para, "text", p.text])
            parents.extend((pid, parent) for parent in p.parents)
    seq: dict[str, int] = {}
    for r in rows:  # renumber within each document, keeping the order
        seq[r[1]] = seq.get(r[1], -1) + 1
        r.insert(2, seq[r[1]])
    con.execute(f"CREATE OR REPLACE TABLE {target} (chunk_id VARCHAR, doc_id VARCHAR, seq INTEGER, section VARCHAR, "
                "para VARCHAR, kind VARCHAR, text VARCHAR, n_chars INTEGER)")
    con.executemany(f"INSERT INTO {target} VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [r + [len(r[6])] for r in rows])
    con.execute(f"CREATE OR REPLACE TABLE {parent_table} (chunk_id VARCHAR, parent_id VARCHAR)")
    con.executemany(f"INSERT INTO {parent_table} VALUES (?, ?)", parents)
    n_new = len({p for p, _ in parents})
    return (f"{len(gs)} paragraphs ({len(replaced)} passages) re-split into {n_new} passages; "
            f"{len(rows)} passages in all (before: {len(live)})")


def active(con) -> bool:
    """Whether builds use semantic passages: PROCINTEL_CHUNKER (size | semantic) when set, else whether the semantic
    shadow was promoted (procintel.learning.shadows records it in table shadow)."""
    choice = os.environ.get("PROCINTEL_CHUNKER", "").strip()
    if choice:
        if choice not in ("size", "semantic"):
            raise ValueError(f"PROCINTEL_CHUNKER must be size or semantic, not {choice!r}")
        return choice == "semantic"
    if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'shadow'").fetchone():
        return False
    return bool(con.execute("SELECT 1 FROM shadow WHERE name = 'semantic' AND status = 'promoted'").fetchone())
