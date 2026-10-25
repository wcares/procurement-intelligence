"""Hybrid retrieval over the cleaned ICR chunks (table `chunk`, built by procintel.chunk): BM25 via LlamaIndex,
plus vector search over EmbeddingGemma passage vectors (table `chunk_vec`, procintel.embed) when configured.

Each chunk becomes a LlamaIndex TextNode carrying its citation metadata (doc, project, country, section,
paragraph anchor). Only the section heading and the text are indexed; the other metadata is excluded so
that ids and URLs do not match query terms.

Filters (country, procurement group, chunk kind) are applied per query as a weight mask over one shared
index rather than by rebuilding the retriever, which is what BM25Retriever's `filters` argument would need.
The same mask applies to the vector scores. The two rankings are merged by reciprocal rank fusion, so neither
score scale has to be calibrated against the other; each hit records which of the two found it (`via`).
Without PROCINTEL_EMBED_MODEL, or when the embedding server does not answer, retrieval is BM25 only.

    python -m procintel.retrieve "why were contracts terminated" --country KE
"""
from __future__ import annotations

import argparse
import copy
import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
from llama_index.core.schema import TextNode
from llama_index.retrievers.bm25 import BM25Retriever

from procintel import db, embed, paths, procurement_rating, ratings, sectors, vector_index
from procintel.stats import GROUP_TERMS

log = logging.getLogger(__name__)
POOL = 50  # candidates taken from each ranking before fusion
RRF_K = 60  # reciprocal rank fusion constant (Cormack et al. 2009)

DB_PATH = paths.DB_PATH

# a chunk's project can be any of several when one ICR covers more than one project
_QUERY = """
SELECT c.chunk_id, c.doc_id, c.seq, c.section, c.para, c.kind, c.text,
       d.title, d.doc_type, d.pdf_url,
       list(dp.project_id ORDER BY dp.project_id)  AS project_ids,
       list(p.name ORDER BY dp.project_id)          AS project_names,
       list(p.country_code ORDER BY dp.project_id)  AS country_codes
FROM chunk c
JOIN document_m d USING (doc_id)
JOIN document_project dp USING (doc_id)
LEFT JOIN project p USING (project_id)
GROUP BY ALL
ORDER BY c.doc_id, c.seq
"""


@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    title: str
    doc_type: str
    url: str
    section: str
    para: str | None
    kind: str
    text: str
    project_id: str
    project_name: str
    country_code: str
    score: float
    via: str = "bm25"  # "bm25", "vector" or "bm25+vector"
    tag: str | None = None  # main problem type from procintel.tag, if the passage was tagged
    tag_confidence: float = 0.0
    problem: str | None = None  # problem kind from procintel.problem_tag when the passage describes one, else None


class Retriever:
    def __init__(self, db_path: Path = DB_PATH):
        con = db.connect(db_path, read_only=True)
        rows = con.execute(_QUERY).fetchall()
        cols = [d[0] for d in con.description]
        if not rows:
            con.close()
            raise ValueError("no chunks to index; run `python -m procintel.chunk` first")
        ids = [r[0] for r in rows]
        # a numpy matrix (in memory) or a Qdrant index, by PROCINTEL_VECTOR_URL (procintel.vector_index)
        self.vectors = vector_index.open_index("chunks", ids, lambda: embed.load(con, ids)) if embed.available() else None
        tags = _load_tags(con)
        problems = _load_problems(con)
        self.rating_conflicts = ratings.load(con)  # doc_id -> note where the ICR outcome and last ISR rating disagree
        self.procurement_conflicts = procurement_rating.load(con)  # doc_id -> note where procurement rated below it
        self.project_family = sectors.project_families(con)  # project_id -> major sector (procintel.sectors)
        self.demoted: set[str] = set()  # set by the backend from the feedback review
        con.close()
        if embed.available() and self.vectors is None:
            log.warning("PROCINTEL_EMBED_MODEL is set but chunk_vec is missing or stale; run `python -m procintel.embed`")

        self.records = [dict(zip(cols, r)) for r in rows]
        for r in self.records:
            r["country_codes"] = [c or "" for c in r["country_codes"]]  # aligned with project_ids
            r["groups"] = {g for g, rx in GROUP_TERMS.items() if rx.search(r["text"])}
            r["tag"], r["tag_confidence"] = tags.get(r["chunk_id"], (None, 0.0))
            r["problem"] = problems.get(r["chunk_id"])

        nodes = []
        for r in self.records:
            meta = {"chunk_id": r["chunk_id"], "doc_id": r["doc_id"], "section": r["section"], "para": r["para"]}
            nodes.append(TextNode(
                id_=r["chunk_id"], text=r["text"], metadata=meta,
                excluded_embed_metadata_keys=["chunk_id", "doc_id", "para"],
                excluded_llm_metadata_keys=["chunk_id", "doc_id", "para"],
            ))
        self._index = {r["chunk_id"]: i for i, r in enumerate(self.records)}
        self._bm25 = BM25Retriever.from_defaults(nodes=nodes, similarity_top_k=10)

    def search(self, query: str, k: int = 8, country: str | None = None, proc_group: str | None = None,
               kinds: tuple[str, ...] = ("text",)) -> list[Hit]:
        mask = np.array([r["kind"] in kinds
                         and (country is None or country in r["country_codes"])
                         and (proc_group is None or proc_group in r["groups"])
                         for r in self.records])
        if not mask.any():
            return []
        ranked = {"bm25": self._bm25_ranking(query, mask)}
        if self.vectors is not None:
            try:
                ranked["vector"] = self._vector_ranking(query, mask)
            except Exception as e:  # server down or misconfigured: keyword results are still valid evidence
                log.warning("vector search failed, using BM25 only: %s", e)
        fused: dict[int, float] = {}
        found_by: dict[int, list[str]] = {}
        for name, idx in ranked.items():
            for rank, i in enumerate(idx):
                fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank + 1)
                found_by.setdefault(i, []).append(name)
        hits = []
        order = sorted(fused, key=fused.get, reverse=True)
        if self.demoted:  # passages users repeatedly flagged as wrong citations go last (procintel.feedback_review)
            order.sort(key=lambda i: self.records[i]["chunk_id"] in self.demoted)
        for i in order[:k]:
            rec = self.records[i]
            j = _project_index(rec, country)
            hits.append(Hit(
                chunk_id=rec["chunk_id"], doc_id=rec["doc_id"], title=rec["title"], doc_type=rec["doc_type"],
                url=rec["pdf_url"], section=rec["section"], para=rec["para"], kind=rec["kind"], text=rec["text"],
                project_id=rec["project_ids"][j], project_name=rec["project_names"][j] or "",
                country_code=rec["country_codes"][j], score=fused[i], via="+".join(found_by[i]),
                tag=rec["tag"], tag_confidence=rec["tag_confidence"], problem=rec["problem"],
            ))
        return hits

    def _bm25_ranking(self, query: str, mask: np.ndarray) -> list[int]:
        # shallow copy shares the index and corpus; only the mask and k differ per query
        r = copy.copy(self._bm25)
        r.corpus_weight_mask = mask.astype(int).tolist()
        r.similarity_top_k = min(POOL, len(mask))
        # zero score = masked out or no term overlap; bm25s still fills the k slots with them
        return [self._index[n.node.node_id] for n in r.retrieve(query) if n.score > 0]

    def _vector_ranking(self, query: str, mask: np.ndarray) -> list[int]:
        q = embed.embed([embed.format_query(query)])[0]
        return vector_index.ranking(self.vectors, q, mask, POOL)


def _load_tags(con: duckdb.DuckDBPyConnection) -> dict[str, tuple[str, float]]:
    """chunk_id -> (tag, confidence) for tags computed on the passage's current text; {} if never tagged."""
    if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'chunk_tag'").fetchone():
        return {}
    rows = con.execute("""SELECT t.chunk_id, t.tag, t.confidence FROM chunk_tag t JOIN chunk c USING (chunk_id)
        WHERE t.text_hash = sha256(c.section || chr(0) || c.text)[:16]
        QUALIFY row_number() OVER (PARTITION BY t.chunk_id ORDER BY t.model) = 1""").fetchall()
    return {c: (t, conf) for c, t, conf in rows}


def _load_problems(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """chunk_id -> problem kind, for passages the two-step tagger found to describe a problem in their current text."""
    if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'chunk_problem'").fetchone():
        return {}
    return dict(con.execute("""SELECT p.chunk_id, coalesce(p.kind, 'unknown kind') FROM chunk_problem p JOIN chunk c USING (chunk_id)
        WHERE p.problem AND p.text_hash = sha256(c.section || chr(0) || c.text)[:16]
        QUALIFY row_number() OVER (PARTITION BY p.chunk_id ORDER BY p.model) = 1""").fetchall())


def _project_index(rec: dict, country: str | None) -> int:
    """Which of the document's projects to cite: the one in the filtered country, else the first."""
    return 0 if country is None else next((i for i, c in enumerate(rec["country_codes"]) if c == country), 0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--country")
    ap.add_argument("--group")
    ap.add_argument("-k", type=int, default=5)
    a = ap.parse_args()
    for h in Retriever().search(a.query, k=a.k, country=a.country, proc_group=a.group):
        anchor = f" ¶{h.para}" if h.para else ""
        print(f"{h.score:6.4f} {h.via:12s} {h.project_id} {h.country_code}  {h.section}{anchor}\n        {h.text[:220]}\n")


if __name__ == "__main__":
    main()
