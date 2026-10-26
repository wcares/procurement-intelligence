from pathlib import Path

import numpy as np
from llama_index.core.schema import Document

from procintel.ingestion import chunk, llama_pipeline, supervision, tag

ISR = (Path(__file__).parent / "fixtures" / "isr_P105680.txt").read_text()
REPORT = ("I. PROJECT STATUS\n\n1.      The civil works contract was re-tendered after the first bids exceeded the cost estimate by "
          "forty percent, which delayed the award by five months.\n2.      Procurement was rated Moderately Satisfactory.\n")


def test_the_pipeline_cuts_by_document_type_and_matches_the_apps_chunk_ids(monkeypatch):
    monkeypatch.setattr(llama_pipeline.embed, "embed", lambda texts: np.ones((len(texts), 4), dtype=np.float32))
    monkeypatch.setattr(tag, "tag_text", lambda text: {"re-tendering or contract termination": 0.8, "none of these": 0.2})
    docs = [Document(id_="d1", text=REPORT, metadata={"doc_id": "d1", "doc_type": "Implementation Completion and Results Report"}),
            Document(id_="i1", text=ISR, metadata={"doc_id": "i1", "doc_type": supervision.ISR_TYPE})]
    nodes = llama_pipeline.build_pipeline().run(documents=docs)
    report_nodes = [n for n in nodes if n.metadata["doc_id"] == "d1"]
    expected = chunk.chunk_document(REPORT)
    assert [n.id_ for n in report_nodes] == [f"d1:{i}" for i in range(len(expected))]   # the app's chunk ids
    assert [n.text for n in report_nodes] == [c.text for c in expected] and expected
    assert len([n for n in nodes if n.metadata["doc_id"] == "i1"]) == 4               # the ISR chunker, as in the app
    assert all(n.embedding == [1.0] * 4 for n in nodes)
    text_nodes = [n for n in nodes if n.metadata["kind"] == "text"]
    assert text_nodes and all(n.metadata["tag"] == "re-tendering or contract termination" for n in text_nodes)
    assert all("tag" not in n.metadata for n in nodes if n.metadata["kind"] == "table")


def test_steps_can_be_left_out():
    nodes = llama_pipeline.build_pipeline(embedding=False, tagging=False).run(
        documents=[Document(id_="d1", text=REPORT, metadata={"doc_id": "d1"})])
    assert len(nodes) == len(chunk.chunk_document(REPORT)) and nodes[0].embedding is None and "tag" not in nodes[0].metadata
