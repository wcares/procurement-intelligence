import json

import duckdb
import pytest
from fastapi.testclient import TestClient

from procintel.core import paths
from procintel.learning import evaluate, feedback_review, labelling


@pytest.fixture
def evalset(tmp_path, monkeypatch):
    q = tmp_path / "questions.jsonl"
    q.write_text('{"id": "q01", "question": "Why delays?", "answerable": true}\n'
                 '{"id": "q02", "question": "Speed of light?", "answerable": false}\n')
    j = tmp_path / "judgments.jsonl"
    j.write_text("".join(json.dumps({"qid": "q01", "chunk_id": f"d:{i}", "relevant": i % 2 == 0, "judge": "m"}) + "\n"
                         for i in range(4)))
    f = tmp_path / "faithfulness.jsonl"
    f.write_text("".join(json.dumps(v) + "\n" for v in [
        {"qid": "q01", "sentence": "A.", "passages": {"d:0": "x"}, "answer_llm": True, "independent": False},
        {"qid": "q01", "sentence": "B.", "passages": {"d:1": "y"}, "answer_llm": True, "independent": True}]))
    monkeypatch.setattr(evaluate, "QUESTIONS", q)
    monkeypatch.setattr(evaluate, "JUDGMENTS", j)
    monkeypatch.setattr(evaluate, "FAITHFULNESS", f)
    monkeypatch.setattr(labelling, "HUMAN_LABELS", tmp_path / "human_labels.jsonl")
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "main.duckdb")
    con = duckdb.connect(str(tmp_path / "main.duckdb"))
    con.execute("CREATE TABLE chunk AS SELECT 'd:' || i AS chunk_id, 'passage ' || i AS text FROM range(4) t(i)")
    con.close()
    monkeypatch.setattr(feedback_review, "items", lambda limit=50: [
        {"kind": "refused_question", "key": "why rebids?", "responses": 2, "questions": ["Why rebids?"], "comments": []},
        {"kind": "not_useful", "key": "why delays?", "responses": 1, "questions": ["Why delays?"], "comments": ["vague"]},
        {"kind": "flagged_citation", "key": "d:1", "responses": 1, "questions": ["x"], "comments": []}])
    return tmp_path


def test_judge_checks_are_a_stable_sample_and_agreement_counts_labels(evalset):
    first = labelling.judge_checks(n=2)
    assert len(first["items"]) == 2 and first["items"] == labelling.judge_checks(n=2)["items"]   # same order each visit
    it = first["items"][0]
    assert it["question"] == "Why delays?" and it["passage"] == "passage " + it["chunkId"][2:]
    labelling.label_judgment(it["qid"], it["chunkId"], it["judge"], "u1")             # agree
    labelling.label_judgment(first["items"][1]["qid"], first["items"][1]["chunkId"], not first["items"][1]["judge"], "u1")
    after = labelling.judge_checks(n=10)
    assert after["agreement"] == {"agree": 1, "labelled": 2} and len(after["items"]) == 2  # labelled ones leave the queue
    with pytest.raises(KeyError):
        labelling.label_judgment("q01", "nope", True, None)


def test_sentence_checks_list_only_disagreements(evalset):
    s = labelling.sentence_checks()
    assert (s["sentences"], s["disagreements"]) == (2, 1) and s["items"][0]["sentence"] == "A."
    labelling.label_sentence(s["items"][0]["key"], False, None)                       # the person sides with the judge
    s = labelling.sentence_checks()
    assert s["items"] == [] and s["decided"] == {"answerModel": 0, "independent": 1, "labelled": 1}


def test_feedback_questions_become_evaluation_questions(evalset):
    c = labelling.question_candidates()
    assert [(x["question"], x["inSet"]) for x in c] == [("Why rebids?", False), ("Why delays?", True)]
    row = labelling.add_question("Why rebids?", True, None)
    assert row["id"] == "q03" and evaluate.questions()[-1]["question"] == "Why rebids?"
    with pytest.raises(ValueError):
        labelling.add_question("why rebids? ", False, None)                           # already in the set


def test_labelling_endpoints(evalset):
    from procintel.api.app import app
    c = TestClient(app, client=("127.0.0.1", 5000))
    q = c.get("/evaluation/labelling").json()
    it = q["judge"]["items"][0]
    r = c.post("/evaluation/labels/judge", json={"qid": it["qid"], "chunkId": it["chunkId"], "relevant": True}).json()
    assert r["judge"]["agreement"]["labelled"] == 1
    assert c.post("/evaluation/questions", json={"question": "Why delays?", "answerable": True}).status_code == 400
    assert c.post("/evaluation/questions", json={"question": "New one?", "answerable": False}).json()["added"]["id"] == "q03"
    assert c.post("/evaluation/labels/sentence", json={"key": "nope", "supported": True}).status_code == 404
