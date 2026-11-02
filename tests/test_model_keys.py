import os
import stat

import pytest

from procintel.api import model_keys
from procintel.core import paths


@pytest.fixture
def keys(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(model_keys, "_from_env", {})
    monkeypatch.setenv("PROCINTEL_LLM_API_KEY", "from-dotenv-key")
    monkeypatch.delenv("PROCINTEL_JUDGE_API_KEY", raising=False)
    return tmp_path


def test_a_page_key_replaces_the_env_one_and_removing_it_brings_that_back(keys):
    assert model_keys.status()["llm"] == {"set": True, "from": "environment"}
    model_keys.put("llm", "sk-page-key-12345")
    assert os.environ["PROCINTEL_LLM_API_KEY"] == "sk-page-key-12345"
    assert model_keys.status()["llm"] == {"set": True, "from": "page"}
    assert stat.S_IMODE(os.stat(model_keys.path()).st_mode) == 0o600          # owner only
    model_keys.remove("llm")
    assert os.environ["PROCINTEL_LLM_API_KEY"] == "from-dotenv-key"
    model_keys.put("judge", "judge-key-123456")
    model_keys.remove("judge")
    assert "PROCINTEL_JUDGE_API_KEY" not in os.environ and model_keys.status()["judge"] == {"set": False, "from": None}


def test_status_never_contains_the_key_and_bad_input_is_refused(keys):
    model_keys.put("batch", "secret-batch-key-999")
    assert "secret-batch-key-999" not in repr(model_keys.status())
    for bad in ("short", "has a space in it", ""):
        with pytest.raises(ValueError):
            model_keys.put("llm", bad)
    with pytest.raises(ValueError):
        model_keys.put("nope", "valid-key-123456")


def test_page_keys_are_applied_at_startup(keys, monkeypatch):
    model_keys.put("judge", "judge-key-abcdefg")
    monkeypatch.delenv("PROCINTEL_JUDGE_API_KEY")
    model_keys.load()
    assert os.environ["PROCINTEL_JUDGE_API_KEY"] == "judge-key-abcdefg"


def test_the_model_test_reports_the_reply_and_hides_a_key_in_an_error(keys, monkeypatch):
    from procintel.api.routes import settings
    from procintel.api.schemas import ModelTest
    from procintel.core import llm
    monkeypatch.setenv("PROCINTEL_LLM_MODEL", "anthropic/claude-sonnet-5-5")
    monkeypatch.setenv("PROCINTEL_LLM_API_KEY", "sk-ant-very-secret")
    monkeypatch.setattr(llm, "complete", lambda *a, **k: "A plan of what will be bought, how and when.")
    out = settings.post_model_test(ModelTest(role="llm"))
    assert out["ok"] and out["model"] == "anthropic/claude-sonnet-5-5" and out["reply"].startswith("A plan")

    def refuse(*a, **k):
        raise RuntimeError("AuthenticationError: invalid x-api-key sk-ant-very-secret")
    monkeypatch.setattr(llm, "complete", refuse)
    out = settings.post_model_test(ModelTest(role="llm"))
    assert not out["ok"] and "sk-ant-very-secret" not in out["error"] and "<key>" in out["error"]
