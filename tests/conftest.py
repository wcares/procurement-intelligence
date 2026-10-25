import pytest


@pytest.fixture(autouse=True)
def isolated_job_queue(tmp_path, monkeypatch):
    """No test writes to the real job queue (data/jobs.duckdb): the feedback endpoint queues a review job."""
    from procintel.jobs import store
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "jobs.duckdb")
