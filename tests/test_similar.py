import numpy as np

from procintel.answering.answer import terms
from procintel.prediction import similar


def make(rows, vectors):
    s = similar.Similar.__new__(similar.Similar)
    s.rows = [dict(r, terms=terms(r["description"])) for r in rows]
    s.vectors = np.asarray(vectors, dtype=np.float32)
    df = {}
    for r in s.rows:
        for t in r["terms"]:
            df[t] = df.get(t, 0) + 1
    s.idf = {t: np.log(len(s.rows) / c) for t, c in df.items()}
    return s


def row(i, group, desc, days=None):
    return {"package_id": f"k{i}", "project_id": "P1", "project_name": "X", "country_code": "ID", "proc_group": group,
            "method_code": "QCBS", "description": desc, "tender_to_award_days": days, "value_usd": 1e5, "rebid_evidence": None}


ROWS = [row(0, "CS", "Management for EEWS Development", 120), row(1, "CS", "Monitoring Consultant"),
        row(2, "CS", "Safeguards Specialist"), row(3, "CS", "Works Supervision Consultant"),
        row(4, "CS", "Financial Audit"), row(5, "CS", "Communication Specialist"), row(6, "CW", "EEWS station civil works")]
VECS = [[0, 1], [1, 0], [1, 0], [1, 0], [0.9, 0.1], [0.8, 0.2], [0, 1]]


def test_returns_k_of_the_same_group_and_finds_an_acronym_by_its_word(monkeypatch):
    s = make(ROWS, VECS)
    monkeypatch.setattr(similar.embed, "embed", lambda texts: np.array([[1.0, 0.0]]))   # vectors favour generic consultants
    out = s.search("EEWS supervision consultant", "CS", k=5)
    assert len(out) == 5 and all(o["packageId"] != "k6" for o in out)          # CW package never offered for CS
    vec_only = [f"k{i}" for i in np.argsort(-(s.vectors[:6] @ np.array([1.0, 0.0])), kind="stable")]
    assert vec_only[-1] == "k0"                                                # vectors alone rank the EEWS package last
    assert "k0" in [o["packageId"] for o in out[:3]]                           # the word ranking lifts it into the top 3
    assert out[[o["packageId"] for o in out].index("k0")]["tenderToAwardDays"] == 120


def test_nothing_without_a_description_or_vectors(monkeypatch):
    s = make(ROWS, VECS)
    assert s.search("   ", "CS") == []
    s.vectors = None
    assert s.search("EEWS", "CS") == []


def test_contracts_with_a_known_award_time_come_first(monkeypatch):
    s = make(ROWS, VECS)
    monkeypatch.setattr(similar.embed, "embed", lambda texts: np.array([[1.0, 0.0]]))
    out = s.search("consultant", "CS", k=2)
    assert out[0]["packageId"] == "k0" and out[0]["tenderToAwardDays"] == 120   # the only one with a known time
