"""Export real values from data/procintel.duckdb into the frontend's mock API fixtures.

The mock API (web/src/app/api/mock/*) serves these so the UI shows real numbers and real ICR passages
before the Python backend exists. Passage extraction here is a rough keyword pass over cleaned ICR text,
NOT the production retriever; the UI labels mock responses as such.

    python -m procintel.export_mock
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "procintel.duckdb"
OUT = ROOT / "web" / "src" / "mocks" / "data.json"

PROC_GROUP_LABELS = {"GO": "Goods", "CW": "Civil Works", "CS": "Consulting Services", "NC": "Non-Consulting Services"}
PROC_TERMS = re.compile(
    r"\b(procurement|tender|re-?tender|bid(?:ding|der|s)?|contract(?:or|s)?|award(?:ed)?|supplier|consultant|"
    r"specification|terms of reference|cancel(?:led|lation)?|delay(?:s|ed)?)\b", re.I)
GROUP_TERMS = {
    "CW": re.compile(r"\b(works?|construction|contractor|civil|rehabilitation|road)\b", re.I),
    "GO": re.compile(r"\b(goods|equipment|supply|supplies|vehicles?|medicines?)\b", re.I),
    "CS": re.compile(r"\b(consultan(?:t|cy|cies)|firm|terms of reference|technical assistance|study)\b", re.I),
    "NC": re.compile(r"\b(services?|maintenance|logistics|training)\b", re.I),
}
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
    con = duckdb.connect(str(DB_PATH), read_only=True)
    q = lambda s, *a: con.execute(s, *a).fetchall()  # noqa: E731

    countries = [{"code": c, "name": n, "region": r} for c, n, r in
                 q("SELECT country_code, name, region FROM country ORDER BY name")]
    sectors = [s for (s,) in q("SELECT DISTINCT sector FROM project WHERE sector IS NOT NULL AND sector <> '' ORDER BY 1")]
    labels = dict(q("SELECT method_code, mode(method_name) FROM notice_m WHERE method_code IS NOT NULL GROUP BY 1"))
    methods = [{"code": m, "label": labels.get(m) or m, "procGroups": gs, "n": n} for m, gs, n in q("""
        SELECT method_code, list(DISTINCT proc_group ORDER BY proc_group), COUNT(*)
        FROM package WHERE method_code IS NOT NULL AND proc_group IS NOT NULL
        GROUP BY 1 HAVING COUNT(*) >= 10 ORDER BY 3 DESC""")]
    def bench(where: str, params: list) -> dict | None:
        r = q(f"""SELECT COUNT(*), median(tender_to_award_days), quantile_cont(tender_to_award_days, .25),
                         quantile_cont(tender_to_award_days, .75), quantile_cont(tender_to_award_days, .9),
                         AVG(CASE WHEN tender_to_award_days > 180 THEN 1 ELSE 0 END)
                  FROM package WHERE tender_to_award_days IS NOT NULL {where}""", params)[0]
        if r[0] == 0:
            return None
        return {"n": r[0], "median": r[1], "p25": r[2], "p75": r[3], "p90": r[4], "shareOver180": r[5]}

    benchmarks: dict[str, dict] = {"all": bench("", [])}
    for (g,) in q("SELECT DISTINCT proc_group FROM package WHERE proc_group IS NOT NULL"):
        benchmarks[g] = bench("AND proc_group = ?", [g])
    for (g, m) in q("SELECT DISTINCT proc_group, method_code FROM package WHERE proc_group IS NOT NULL AND method_code IS NOT NULL"):
        b = bench("AND proc_group = ? AND method_code = ?", [g, m])
        if b and b["n"] >= 10:
            benchmarks[f"{g}/{m}"] = b

    governance = {}
    for cc, ind, yr, val in q("""SELECT country_code, indicator, year, value FROM cpia
                                 QUALIFY row_number() OVER (PARTITION BY country_code, indicator ORDER BY year DESC) = 1"""):
        governance.setdefault(cc, []).append({"indicator": ind, "year": yr, "value": val})

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
        "options": {
            "countries": countries,
            "sectors": sectors,
            "procGroups": [{"code": k, "label": v} for k, v in PROC_GROUP_LABELS.items()],
            "methods": methods,
        },
        "benchmarks": benchmarks,
        "governance": governance,
        "passages": passages,
    }
    OUT.write_text(json.dumps(data, indent=1, default=str))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(countries)} countries, {len(methods)} methods, "
          f"{len(benchmarks)} benchmarks, {len(governance)} countries with CPIA, {len(passages)} passages "
          f"from {len({p['docId'] for p in passages})} ICRs, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
