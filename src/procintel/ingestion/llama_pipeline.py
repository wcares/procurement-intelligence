"""The ingestion steps as a LlamaIndex IngestionPipeline, for use from LlamaIndex tools and notebooks:

    from procintel.ingestion.llama_pipeline import build_pipeline, documents_from_db
    nodes = build_pipeline().run(documents=documents_from_db(limit=3))

Each step is a TransformComponent wrapping the code the app uses: PassageSplitter (the completion-report chunker, or
the ISR chunker for ISRs), PassageEmbedder (procintel.core.embed, the same document prompt) and PassageTagger
(procintel.ingestion.tag, the decision model's procurement-topic tag). A node's id is "<doc_id>:<seq>", the app's
chunk id, so nodes and the chunk table line up.

The app itself keeps building the tables incrementally (procintel.ingestion.chunk, embed, tag, run by the pipeline's
actions): that path re-cuts only changed documents, keeps vectors, tags and evaluation labels of passages that only
moved, and stores them where search reads them. This wrapper does none of that; it runs the same steps on documents in
memory.
"""
from __future__ import annotations

from typing import Any, Sequence

from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.schema import BaseNode, Document, TextNode, TransformComponent

from procintel.core import db, embed
from procintel.ingestion import chunk, isr_chunk, supervision


class PassageSplitter(TransformComponent):
    """Documents (metadata doc_id, doc_type) -> passages, cut by the chunker for their document type."""

    def __call__(self, nodes: Sequence[BaseNode], **kwargs: Any) -> Sequence[BaseNode]:
        out: list[BaseNode] = []
        for d in nodes:
            doc_id, doc_type = d.metadata.get("doc_id", d.id_), d.metadata.get("doc_type")
            cut = isr_chunk.chunk_isr if doc_type == supervision.ISR_TYPE else chunk.chunk_document
            for i, c in enumerate(cut(d.get_content())):
                out.append(TextNode(id_=f"{doc_id}:{i}", text=c.text, metadata={
                    "doc_id": doc_id, "doc_type": doc_type, "seq": i, "section": c.section, "para": c.para, "kind": c.kind},
                    excluded_embed_metadata_keys=["doc_id", "seq", "para", "kind"]))
        return out


class PassageEmbedder(TransformComponent):
    """Vectors from the configured embedding model, with the app's document prompt (section as the title)."""

    def __call__(self, nodes: Sequence[BaseNode], **kwargs: Any) -> Sequence[BaseNode]:
        if not nodes:
            return nodes
        vecs = embed.embed([embed.format_document(n.get_content(), n.metadata.get("section")) for n in nodes])
        for n, v in zip(nodes, vecs):
            n.embedding = v.tolist()
        return nodes


class PassageTagger(TransformComponent):
    """The decision model's procurement-topic tag for text passages (tables are left untagged, as in the app)."""

    def __call__(self, nodes: Sequence[BaseNode], **kwargs: Any) -> Sequence[BaseNode]:
        from procintel.ingestion import tag
        for n in nodes:
            if n.metadata.get("kind") == "text":
                scores = tag.tag_text(n.get_content())
                best = max(scores, key=scores.get)
                n.metadata.update({"tag": best, "tag_confidence": round(scores[best], 3)})
        return nodes


def build_pipeline(embedding: bool = True, tagging: bool = True) -> IngestionPipeline:
    steps: list[TransformComponent] = [PassageSplitter()]
    if embedding:
        steps.append(PassageEmbedder())
    if tagging:
        steps.append(PassageTagger())
    return IngestionPipeline(transformations=steps, disable_cache=True)


def documents_from_db(limit: int | None = None, doc_type: str | None = None) -> list[Document]:
    """Reports from the documents table as LlamaIndex Documents."""
    con = db.connect(read_only=True)
    try:
        q = "SELECT doc_id, doc_type, title, text FROM documents" + (" WHERE doc_type = ?" if doc_type else "") + \
            " ORDER BY doc_id" + (f" LIMIT {int(limit)}" if limit else "")
        rows = con.execute(q, [doc_type] if doc_type else []).fetchall()
    finally:
        con.close()
    return [Document(id_=d, text=t, metadata={"doc_id": d, "doc_type": dt, "title": ti}) for d, dt, ti, t in rows]
