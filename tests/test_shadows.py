import duckdb
import numpy as np

from procintel.core import embed, paths
from procintel.ingestion import semantic_chunk as sc
from procintel.learning import shadows


def test_split_prefers_a_topic_shift_and_respects_the_limit():
    sents = ["A" * 400 + ".", "B" * 400 + ".", "C" * 400 + ".", "D" * 400 + "."]   # 1,604 chars: over the limit
    owners = ["c0", "c0", "c1", "c1"]
    same, other = np.array([1.0, 0.0]), np.array([0.0, 1.0])
    vecs = np.array([same, same, other, other])              # the topic changes between the 2nd and 3rd sentence
    pieces = sc.split(sents, owners, vecs, limit=1400)
    assert [len(p.text) for p in pieces] == [803, 803] and [p.parents for p in pieces] == [["c0"], ["c1"]]
    long = sc.split(sents * 2, owners * 2, np.array([same] * 8), limit=1000)  # no shift: cut by size only
    assert all(len(p.text) <= 1000 for p in long)


def test_a_short_last_piece_joins_the_one_before():
    sents = ["A" * 700 + ".", "B" * 50 + "."]
    pieces = sc.split(sents, ["c0", "c1"], np.array([[1.0, 0.0], [0.0, 1.0]]), limit=1400)
    assert len(pieces) == 1 and pieces[0].parents == ["c0", "c1"]


def test_build_promote_and_later_builds_follow_the_promotion(tmp_path, monkeypatch):
    db_file = tmp_path / "p.duckdb"
    monkeypatch.setattr(paths, "DB_PATH", db_file)
    monkeypatch.delenv("PROCINTEL_CHUNKER", raising=False)
    monkeypatch.setattr(embed, "model_name", lambda: "fake")
    monkeypatch.setattr(embed, "embed", lambda texts: np.array([[1.0, 0.0] if "A" in t else [0.0, 1.0] for t in texts]))
    con = duckdb.connect(str(db_file))
    para = ["A" * 600 + ". " + "A" * 600 + ".", "B" * 600 + ". " + "B" * 300 + "."]   # one paragraph, split by size
    con.execute("CREATE TABLE chunk (chunk_id VARCHAR, doc_id VARCHAR, seq INTEGER, section VARCHAR, para VARCHAR, "
                "kind VARCHAR, text VARCHAR, n_chars INTEGER)")
    con.executemany("INSERT INTO chunk VALUES (?, 'd', ?, 'S', '1', 'text', ?, ?)",
                    [(f"d:{i}", i, t, len(t)) for i, t in enumerate(para)])
    con.execute("INSERT INTO chunk VALUES ('d:2', 'd', 2, 'S', '2', 'text', 'short one.', 10)")
    con.execute("CREATE TABLE chunk_vec (chunk_id VARCHAR, model VARCHAR, dim INTEGER, text_hash VARCHAR, vec FLOAT[])")
    con.close()
    steps = list(shadows.build_semantic(None))
    assert steps[-1]["stage"] == "written"
    con = duckdb.connect(str(db_file))
    assert con.execute("SELECT count(*) FROM chunk__semantic").fetchone()[0] == con.execute(
        "SELECT count(*) FROM chunk_vec__semantic").fetchone()[0]
    assert {p for (p,) in con.execute("SELECT DISTINCT parent_id FROM chunk_parent__semantic").fetchall()} == {"d:0", "d:1"}
    assert not sc.active(con)
    con.close()
    shadows.promote("semantic")
    con = duckdb.connect(str(db_file))
    assert con.execute("SELECT count(*) FROM chunk__previous").fetchone()[0] == 3
    assert sc.active(con)                                      # later builds use semantic passages
    con.close()
    assert shadows.states()[0]["status"] == "promoted" and shadows.parents_of(None)
    monkeypatch.setenv("PROCINTEL_CHUNKER", "size")
    con = duckdb.connect(str(db_file))
    assert not sc.active(con)                                  # the setting overrides the recorded promotion
    con.close()
