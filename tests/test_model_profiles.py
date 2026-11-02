import json
import os
import stat

import pytest

from procintel.api import model_keys, model_profiles
from procintel.core import llm, paths, provider_keys


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setenv("PROCINTEL_KEYS_DIR", str(tmp_path))
    monkeypatch.setattr(paths, "PROFILES_FILE", tmp_path / "config_profiles.json")
    monkeypatch.setattr(model_keys, "_from_env", {})
    for v in ("PROCINTEL_LLM_MODEL", "PROCINTEL_LLM_API_BASE", "PROCINTEL_LLM_EXTRA_BODY", "PROCINTEL_LLM_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    return tmp_path


def test_a_hosted_model_uses_its_providers_key_and_a_local_server_never_does(home, monkeypatch):
    provider_keys.put("anthropic", "sk-ant-saved-once")
    assert stat.S_IMODE(os.stat(provider_keys.path()).st_mode) == 0o600
    monkeypatch.setenv("PROCINTEL_LLM_MODEL", "anthropic/claude-sonnet-5-5")
    assert llm._request("s", "u", None, None, llm.ANSWER, {})["api_key"] == "sk-ant-saved-once"
    monkeypatch.setenv("PROCINTEL_LLM_MODEL", "openai/saluki-27b")                  # a local server: no cloud key
    monkeypatch.setenv("PROCINTEL_LLM_API_BASE", "http://127.0.0.1:8080/v1")
    assert llm._request("s", "u", None, None, llm.ANSWER, {})["api_key"] == "local"
    assert provider_keys.provider_of("openai/gpt-5", None) == "openai" and provider_keys.provider_of("openai/x", "http://h") is None
    assert "sk-ant-saved-once" not in json.dumps(provider_keys.status())
    with pytest.raises(ValueError):
        provider_keys.put("nope", "valid-key-123456")


def test_model_profiles_switch_the_model_only(home, monkeypatch):
    from procintel.api import config
    monkeypatch.setattr(config, "SAVED", home / "config.json")
    monkeypatch.setenv("PROCINTEL_LLM_MODEL", "openai/saluki-27b")
    monkeypatch.setenv("PROCINTEL_LLM_API_BASE", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("PROCINTEL_LLM_EXTRA_BODY", '{"a": 1}')
    model_profiles.save("Local")
    config.update({"llm_model": "anthropic/claude-sonnet-5-5", "llm_api_base": "", "llm_extra_body": ""})
    model_profiles.save("Cloud")
    assert model_profiles.apply("Local") == {}
    assert os.environ["PROCINTEL_LLM_API_BASE"] == "http://127.0.0.1:8080/v1" and os.environ["PROCINTEL_LLM_EXTRA_BODY"] == '{"a": 1}'
    assert model_profiles.apply("Cloud") == {} and "PROCINTEL_LLM_API_BASE" not in os.environ
    listed = {p["name"]: p for p in model_profiles.listing()}
    assert listed["Cloud"]["active"] and listed["Cloud"]["provider"] == "anthropic" and listed["Local"]["provider"] is None
    assert model_profiles.remove("Local") and not model_profiles.remove("Local")


def test_migration_moves_the_page_key_to_its_provider_and_copies_the_profiles(home, monkeypatch):
    (home / "config_profiles.json").write_text(json.dumps({
        "Cloud: Claude": {"llm_model": "anthropic/claude-sonnet-5-5", "llm_api_base": "", "llm_extra_body": "", "top_k": 5},
        "No model": {"top_k": 3}}))
    monkeypatch.setenv("PROCINTEL_LLM_MODEL", "anthropic/claude-sonnet-5-5")
    model_keys.put("llm", "sk-ant-from-the-page")
    model_profiles.migrate()
    assert provider_keys.get("anthropic") == "sk-ant-from-the-page" and "llm" not in model_keys._read()
    assert [p["name"] for p in model_profiles.listing()] == ["Cloud: Claude"]
