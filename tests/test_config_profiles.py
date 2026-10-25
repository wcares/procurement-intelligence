from procintel.answering import answer, retrieve
from procintel.api import config


def test_profile_save_apply_and_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILES", tmp_path / "profiles.json")
    monkeypatch.setattr(retrieve, "RRF_K", 60)
    monkeypatch.setattr(answer, "MAX_PASSAGES", 5)
    assert config.update({"rrf_k": 30, "max_passages": 3}) == {}
    config.save_profile("tight")
    [p] = config.profiles()
    assert p["name"] == "tight" and p["values"]["rrf_k"] == 30
    assert config.update({"rrf_k": 60, "max_passages": 5}) == {}
    assert config.apply_profile("tight") == {} and retrieve.RRF_K == 30 and answer.MAX_PASSAGES == 3
    assert config.apply_profile("missing") == {"name": "no profile with this name"}
    assert config.delete_profile("tight") and config.profiles() == [] and not config.delete_profile("tight")


def test_compare_measures_both_and_restores_the_settings(monkeypatch):
    monkeypatch.setattr(retrieve, "RRF_K", 60)
    out = config.compare({"rrf_k": 10}, lambda: {"k": retrieve.RRF_K})
    assert out == {"before": {"k": 60}, "after": {"k": 10}} and retrieve.RRF_K == 60
    bad = config.compare({"rrf_k": 0}, lambda: {"k": retrieve.RRF_K})   # below the minimum: nothing measured after
    assert "rrf_k" in bad["errors"] and retrieve.RRF_K == 60
