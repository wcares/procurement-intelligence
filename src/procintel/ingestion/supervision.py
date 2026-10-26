"""Supervision reports (ISRs) and restructuring papers of the tracked projects: the brief's "supervision notes and
amendments". Completion reports say what went wrong at the end; these say it while it happened and what was changed.

For every tracked project, the newest ISR_PER_PROJECT ISRs and the newest RESTRUCTURING_PER_PROJECT restructuring
papers (settings, environment PROCINTEL_ISR_PER_PROJECT / PROCINTEL_RESTRUCTURING_PER_PROJECT). Restructuring papers
are listed by the documents API as "Project Paper", a type shared with additional-financing papers; only titles that
name a restructuring count, and they are stored as RESTRUCTURING_TYPE. Read by the pipeline's SupervisionDoc entity
(procintel.pipeline.entities); their passages are cut by procintel.ingestion.isr_chunk (ISRs) and the completion-report
chunker (restructuring papers, which share that layout).
"""
from __future__ import annotations

import os
import re

import pandas as pd

ISR_TYPE = "Implementation Status and Results Report"
PROJECT_PAPER = "Project Paper"
RESTRUCTURING_TYPE = "Restructuring Paper"
TYPES = (ISR_TYPE, RESTRUCTURING_TYPE)
ISR_PER_PROJECT = int(os.environ.get("PROCINTEL_ISR_PER_PROJECT", "1"))
RESTRUCTURING_PER_PROJECT = int(os.environ.get("PROCINTEL_RESTRUCTURING_PER_PROJECT", "1"))
_RESTRUCTURING = re.compile(r"restructuring", re.I)


def row(d: dict, doc_type: str, project_id: str) -> dict:
    return {"doc_id": d["id"], "project_id": project_id, "doc_type": doc_type,
            "doc_date": pd.to_datetime(d.get("docdt"), errors="coerce", utc=True),
            "title": d.get("display_title"), "pdf_url": d.get("pdfurl"), "txt_url": d["txturl"]}


def for_project(client, project_id: str) -> list[dict]:
    """The newest ISRs and restructuring papers of one project that have a text version."""
    out = []
    if ISR_PER_PROJECT:
        _, docs = client.documents(rows=ISR_PER_PROJECT * 2, docty_exact=ISR_TYPE, projectid=project_id)
        out += [row(d, ISR_TYPE, project_id) for d in docs if d.get("txturl")][:ISR_PER_PROJECT]
    if RESTRUCTURING_PER_PROJECT:
        _, docs = client.documents(rows=10, docty_exact=PROJECT_PAPER, projectid=project_id)
        papers = [d for d in docs if d.get("txturl") and _RESTRUCTURING.search(d.get("display_title") or "")]
        out += [row(d, RESTRUCTURING_TYPE, project_id) for d in papers[:RESTRUCTURING_PER_PROJECT]]
    return out
