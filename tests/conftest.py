import pytest


@pytest.fixture(autouse=True)
def isolated_job_queue(tmp_path, monkeypatch):
    """No test writes to the real job queue (data/jobs.duckdb): the feedback endpoint queues a review job."""
    from procintel.jobs import store
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "jobs.duckdb")


@pytest.fixture(autouse=True)
def isolated_accounts(tmp_path, monkeypatch):
    """Sign-in off unless a test turns it on (tests/test_auth.py); accounts never touch data/auth.duckdb."""
    from procintel.core import paths
    monkeypatch.setattr(paths, "AUTH_DB", tmp_path / "auth.duckdb")
    monkeypatch.setenv("PROCINTEL_AUTH", "off")
