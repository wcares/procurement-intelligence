"""BM25 retrieval over the cleaned ICR chunks (table `chunk`, built by procintel.chunk), via LlamaIndex.

Each chunk becomes a LlamaIndex TextNode carrying its citation metadata (doc, project, country, section,
paragraph anchor). Only the section heading and the text are indexed; the other metadata is excluded so
that ids and URLs do not match query terms.

Filters (country, procurement group, chunk kind) are applied per query as a weight mask over one shared
index rather than by rebuilding the retriever, which is what BM25Retriever's `filters` argument would need.

    python -m procintel.retrieve "why were contracts terminated" --country KE
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
from pathlib import Path

import duckdb
from llama_index.core.schema import TextNode
from llama_index.retrievers.bm25 import BM25Retriever

from procintel.export_mock import GROUP_TERMS

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "procintel.duckdb"

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


class Retriever:
    def __init__(self, db_path: Path = DB_PATH):
        con = duckdb.connect(str(db_path), read_only=True)
        rows = con.execute(_QUERY).fetchall()
        cols = [d[0] for d in con.description]
        con.close()
        if not rows:
            raise ValueError("no chunks to index; run `python -m procintel.chunk` first")

        self.records = [dict(zip(cols, r)) for r in rows]
        for r in self.records:
            r["country_codes"] = [c or "" for c in r["country_codes"]]  # aligned with project_ids
            r["groups"] = {g for g, rx in GROUP_TERMS.items() if rx.search(r["text"])}

        nodes = []
        for r in self.records:
            meta = {"chunk_id": r["chunk_id"], "doc_id": r["doc_id"], "section": r["section"], "para": r["para"]}
            nodes.append(TextNode(
                id_=r["chunk_id"], text=r["text"], metadata=meta,
                excluded_embed_metadata_keys=["chunk_id", "doc_id", "para"],
                excluded_llm_metadata_keys=["chunk_id", "doc_id", "para"],
            ))
        self._by_id = {r["chunk_id"]: r for r in self.records}
        self._bm25 = BM25Retriever.from_defaults(nodes=nodes, similarity_top_k=10)

    def search(self, query: str, k: int = 8, country: str | None = None, proc_group: str | None = None,
               kinds: tuple[str, ...] = ("text",)) -> list[Hit]:
        mask = [int(r["kind"] in kinds
                    and (country is None or country in r["country_codes"])
                    and (proc_group is None or proc_group in r["groups"]))
                for r in self.records]
        if not any(mask):
            return []
        # shallow copy shares the index and corpus; only the mask and k differ per query
        r = copy.copy(self._bm25)
        r.corpus_weight_mask = mask
        r.similarity_top_k = min(k, len(mask))
        hits = []
        for nws in r.retrieve(query):
            if nws.score <= 0:  # masked-out or no term overlap; bm25s still fills k slots with them
                continue
            rec = self._by_id[nws.node.node_id]
            i = _project_index(rec, country)
            hits.append(Hit(
                chunk_id=rec["chunk_id"], doc_id=rec["doc_id"], title=rec["title"], doc_type=rec["doc_type"],
                url=rec["pdf_url"], section=rec["section"], para=rec["para"], kind=rec["kind"], text=rec["text"],
                project_id=rec["project_ids"][i], project_name=rec["project_names"][i] or "",
                country_code=rec["country_codes"][i],
                score=float(nws.score),
            ))
        return hits


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
        print(f"{h.score:6.2f}  {h.project_id} {h.country_code}  {h.section}{anchor}\n        {h.text[:220]}\n")


if __name__ == "__main__":
    main()
