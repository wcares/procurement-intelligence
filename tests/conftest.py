import os

import pytest

# No test starts the backend's background work (job worker, MCP listener): tests/test_api.py's app is created once per
# module, before the per-test isolation below applies, so its worker would run against the live job queue (seen
# 2026-11-02: it put a running evaluation back to pending). Must be set before procintel.api.background is imported.
os.environ["PROCINTEL_JOBS"] = "0"


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


@pytest.fixture(autouse=True)
def isolated_connector_settings(tmp_path, monkeypatch):
    """Connector settings (procintel.pipeline.connector_config) never touch data/connectors.json."""
    from procintel.core import paths
    monkeypatch.setattr(paths, "CONNECTORS_FILE", tmp_path / "connectors.json")
