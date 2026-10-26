"""Export real values from data/procintel.duckdb into the frontend's mock API fixtures.

The mock API (web/src/app/api/mock/*) serves these so the UI shows real numbers and real ICR passages
before the Python backend exists. Passage extraction here is a rough keyword pass over cleaned ICR text,
NOT the production retriever; the UI labels mock responses as such.

    python -m procintel.tools.export_mock
"""
from __future__ import annotations

import json
import re

from procintel.core import db, paths
from procintel.prediction import stats
from procintel.prediction.stats import GROUP_TERMS, PROC_TERMS

ROOT = paths.ROOT
DB_PATH = paths.DB_PATH
OUT = ROOT / "web" / "src" / "mocks" / "data.json"

# staff lists and supervision-cost annexes match procurement words ("procurement specialist") but hold no lessons
SKIP_SECTIONS = re.compile(r"task team|bank lending|staff time|front matter", re.I)
_HEADING = re.compile(r"^\s*(?:[IVX]+\.|ANNEX\s+\d+\.?|[A-H]\.)?\s*[A-Z][A-Z ,/&()'’-]{8,90}$")


def clean_paragraphs(text: str) -> list[tuple[str, str]]:
    """[(section, paragraph)] from pdf-to-text ICR output."""
    out: list[tuple[str, str]] = []
    section = "Front matter"
    buf: list[str] = []

    def flush() -> None:
        if buf:
            para = re.sub(r"\s+", " ", " ".join(buf)).strip()
            if para:
                out.append((section, para))
            buf.clear()

    for raw in text.replace("\x0c", "\n").split("\n"):
        line = raw.strip()
        if not line:
            flush()
            continue
        # page furniture: footer, repeated running header
        if re.search(r"Official Use Only|Page \d+\s*$|^The World Bank$|ICR DOCUMENT$|\(P\d{6}\)\s*$", line):
            continue
        if "....." in line:  # table of contents line
            continue
        if _HEADING.match(line) and not line.endswith("."):
            flush()
            section = re.sub(r"\s+", " ", line).title()
            continue
        buf.append(line)
    flush()
    return out


def main() -> None:
    con = db.connect(DB_PATH, read_only=True)
    q = lambda s, *a: con.execute(s, *a).fetchall()  # noqa: E731

    opts = stats.options(con)
    benchmarks = stats.benchmarks(con)
    governance = stats.governance(con)

    passages = []
    for doc_id, doc_type, title, pdf_url, text in q(
            "SELECT doc_id, doc_type, title, pdf_url, text FROM documents"):
        links = q("SELECT dp.project_id, p.name, p.country_code, c.region FROM document_project dp "
                  "JOIN project p USING (project_id) JOIN country c USING (country_code) WHERE dp.doc_id = ?", [doc_id])
        if not links:
            continue
        pid, pname, cc, region = links[0]
        scored = []
        for i, (section, para) in enumerate(clean_paragraphs(text)):
            if not (200 <= len(para) <= 900) or SKIP_SECTIONS.search(section):
                continue
            hits = len(PROC_TERMS.findall(para))
            if hits >= 3:
                groups = [g for g, rx in GROUP_TERMS.items() if rx.search(para)]
                scored.append((hits, i, section, para, groups))
        for hits, i, section, para, groups in sorted(scored, reverse=True)[:4]:
            passages.append({
                "id": f"{doc_id}:{i}", "docId": doc_id, "projectId": pid, "projectName": pname,
                "countryCode": cc, "region": region, "docType": doc_type, "title": title,
                "section": section, "quote": para, "url": pdf_url, "procGroups": groups, "score": hits,
            })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "generatedFrom": "data/procintel.duckdb",
        "options": opts,
        "benchmarks": benchmarks,
        "governance": governance,
        "passages": passages,
    }
    OUT.write_text(json.dumps(data, indent=1, default=str))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(opts["countries"])} countries, {len(opts["methods"])} methods, "
          f"{len(benchmarks)} benchmarks, {len(governance)} countries with CPIA, {len(passages)} passages "
          f"from {len({p['docId'] for p in passages})} reports (completion, supervision, restructuring), {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
