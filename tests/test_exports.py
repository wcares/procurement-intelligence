import io

from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient

from procintel.api.routes import exports
from procintel.reports import word

PLAN = {"title": "Rural roads plan", "projectStart": "2026-11-01", "deadline": "2027-06-30",
        "packages": [{"id": "a", "name": "Civil works lot 1", "procGroup": "CW", "methodCode": "RFB"},
                     {"id": "b", "name": "Supervision consultant", "procGroup": "CS", "methodCode": "QCBS", "after": "a"}],
        "forecasts": {"a": {"p50": 120, "p90": 210, "pLong": 0.2, "basis": "model", "n": 215, "scope": "KE", "highRisks": 1,
                            "risks": ["Re-tendering (high)"]}},
        "plan": {"rows": [{"id": "a", "start50": "2026-11-01", "award50": "2027-03-01", "award90": "2027-05-30", "p90Missing": False, "waitsFor": None},
                          {"id": "b", "start50": "2027-03-01", "award50": "2027-07-15", "award90": "2027-09-01", "p90Missing": True, "waitsFor": "a"}],
                 "end50": "2027-07-15", "end90": "2027-09-01", "bottleneck": "b", "loops": []}}

ASSESS = {"request": {"countryCode": "KE", "procGroup": "CW", "methodCode": "RFB", "description": "Feeder roads"},
          "response": {"timeline": {"metric": "tender_to_award_days", "scope": "Kenya, CW, RFB", "n": 215, "median": 112,
                                    "p25": 80, "p75": 160, "p90": 240},
                       "risks": [{"id": "r", "label": "Re-tendering", "level": "high", "basis": "statistic", "detail": "1 in 4 re-bid"}],
                       "governance": [{"indicator": "Transparency", "year": 2024, "value": 3.0}],
                       "precedents": [{"citation": {"id": "d:1", "docId": "d", "docType": "ICR", "title": "t", "section": "Lessons ¶12",
                                                   "quote": "Splitting the works into smaller lots attracted local bidders.",
                                                   "url": "https://example.org/r.pdf", "projectId": "P1", "projectName": "Roads",
                                                   "countryCode": "KE"}, "relevance": 1, "matchedOn": []}],
                       "similarPackages": [], "prediction": {"basis": "model", "days_p50": 118, "days_p90": 230, "p_long": 0.25},
                       "meta": {"source": "live", "generatedAt": "x", "caveats": ["Recent years are incomplete."]}}}


def _text(data: bytes) -> str:
    d = Document(io.BytesIO(data))
    return "\n".join([p.text for p in d.paragraphs] + [c.text for t in d.tables for r in t.rows for c in r.cells])


def test_the_plan_file_has_the_summary_deadline_check_and_every_package():
    text = _text(word.plan_docx(PLAN, "planner-7"))
    assert "Rural roads plan" in text and "by planner-7" in text
    assert "15 Jul 2027" in text and "Supervision consultant" in text and "Re-tendering (high)" in text
    assert "Typical award date after the deadline: Supervision consultant." in text
    assert "no slow-case estimate" in text and "not commitments" in text
    assert "121 days to spare, slow case 31 days to spare" in text          # lot 1 vs 30 Jun 2027
    assert "Why this number: A model trained on past World Bank packages (215 packages, KE): 120 days typical" in text
    assert "Treat the project dates as a planning aid" in text


def test_the_assessment_file_has_the_forecast_risks_and_quoted_lessons_with_their_source():
    text = _text(word.assessment_docx(ASSESS))
    assert "median 112 days" in text and "118 days typical" in text and "more than 180 days 25%" in text
    assert "Re-tendering" in text and "Transparency" in text
    assert "Splitting the works into smaller lots" in text and "https://example.org/r.pdf" in text
    assert "Recent years are incomplete." in text
    kept = {**ASSESS, "accepted": [{"id": "m1", "kind": "mitigation", "title": "Re-tendering: what past projects did",
                                     "sentences": [{"text": "Bidding documents were simplified.", "citations": [0]}],
                                     "citations": [{"projectName": "Roads", "projectId": "P1", "section": "Lessons", "url": "https://example.org/l.pdf"}]}]}
    text = _text(word.assessment_docx(kept))
    assert "Accepted mitigations" in text and "Bidding documents were simplified." in text and "https://example.org/l.pdf" in text


def test_the_routes_return_word_files_and_refuse_bad_bodies():
    app = FastAPI()
    app.include_router(exports.router)
    c = TestClient(app)
    r = c.post("/export/plan", json=PLAN)
    assert r.status_code == 200 and r.headers["content-type"] == exports.DOCX
    assert 'filename="Rural-roads-plan-' in r.headers["content-disposition"] and r.content[:2] == b"PK"
    assert c.post("/export/assessment", json=ASSESS).status_code == 200
    assert c.post("/export/plan", json={"packages": "x"}).status_code == 400
    assert c.post("/export/assessment", json={}).status_code == 400
