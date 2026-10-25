from procintel.api import config
from procintel.ingestion import chunk
from procintel.jobs import handlers


def test_index_and_drift_thresholds_are_settings_that_take_effect(monkeypatch):
    for name in ("FLAT_NUMBERS", "MAX_CHARS"):
        monkeypatch.setattr(chunk, name, getattr(chunk, name))       # restored after the test
    monkeypatch.setattr(handlers, "MIN_NEW", handlers.MIN_NEW)
    numbers = "Cost 12 34 56 78 90 total budget amounts were spent on works goods and other items in the year"
    assert chunk.is_flat_table(numbers)                               # 5 of 18 tokens are numbers: over 0.2 ...
    assert config.update({"flat_numbers": 0.9, "flat_numbers_no_sentence": 0.9}) == {}
    assert not chunk.is_flat_table(numbers)                           # ... no longer a table with the new thresholds
    assert config.update({"chunk_max_chars": 500}) == {}
    assert all(len(p) <= 500 for p in chunk._split_long("A sentence of words here. " * 60))
    assert config.update({"drift_min_new": 5}) == {} and handlers.MIN_NEW == 5
    assert "drift_growth" in config.update({"drift_growth": 3})      # outside its range: refused
    config.update({"flat_numbers": 0.3, "flat_numbers_no_sentence": 0.2, "chunk_max_chars": 1400, "drift_min_new": 20})
