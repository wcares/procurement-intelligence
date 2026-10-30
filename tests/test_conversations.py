import pytest

from procintel.learning import conversations as c


@pytest.fixture
def db(tmp_path):
    return tmp_path / "feedback.duckdb"


def test_save_list_open_and_delete(db):
    msgs = [{"id": 1, "role": "user", "content": "Plan roads in Kenya"}, {"id": 2, "role": "assistant", "content": "Got it"}]
    c.save("u1", "abcdef12", "plan", msgs, db)
    assert [i["title"] for i in c.listing("u1", "plan", db)] == ["Plan roads in Kenya"]
    assert c.get("u1", "abcdef12", db)["messages"] == msgs
    c.save("u1", "abcdef12", "plan", msgs + [{"id": 3, "role": "user", "content": "more"}], db)   # same id: replaced
    assert c.listing("u1", "plan", db)[0]["messages"] == 3
    assert c.remove("u1", "abcdef12", db) and c.get("u1", "abcdef12", db) is None


def test_only_the_owner_sees_and_changes_a_conversation(db):
    c.save("u1", "abcdef12", "ask", [{"id": 1, "question": "Why re-tender?"}], db)
    assert c.get("u2", "abcdef12", db) is None and c.listing("u2", "ask", db) == []
    with pytest.raises(ValueError):
        c.save("u2", "abcdef12", "ask", [{"id": 1, "question": "x"}], db)
    assert not c.remove("u2", "abcdef12", db) and c.get("u1", "abcdef12", db)


def test_bad_input_is_refused(db):
    for kind, msgs in (("other", [{"a": 1}]), ("plan", []), ("plan", [{"content": "x" * 2_000_000}])):
        with pytest.raises(ValueError):
            c.save("u1", "abcdef12", kind, msgs, db)
