from datetime import datetime, timedelta, timezone

import boto3
import pytest
from moto import mock_aws

from procintel.core import blob, paths
from procintel.intake import process, store as upload_store
from procintel.jobs import retention


@pytest.fixture
def s3(monkeypatch):
    with mock_aws():
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
        boto3.client("s3").create_bucket(Bucket="procintel")
        monkeypatch.setenv("PROCINTEL_BLOB_URL", "s3://procintel/raw")
        yield boto3.client("s3")


def test_the_local_store_keeps_the_existing_data_folder_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.delenv("PROCINTEL_BLOB_URL", raising=False)
    s = blob.store()
    s.put("cache/http/a.json", b"{}")
    assert (tmp_path / "cache" / "http" / "a.json").read_bytes() == b"{}" and blob.backend() == "local"
    assert s.get("cache/http/a.json") == b"{}" and s.get("nope") is None
    assert [k for k, _ in s.list("cache/http")] == ["cache/http/a.json"]
    s.delete("cache/http/a.json")
    assert s.list("cache/http") == []


def test_object_storage_puts_lists_and_deletes_under_its_prefix(s3):
    s = blob.store()
    assert blob.backend() == "s3"
    s.put("uploads/x.txt", b"hello")
    assert s3.get_object(Bucket="procintel", Key="raw/uploads/x.txt")["Body"].read() == b"hello"
    assert s.get("uploads/x.txt") == b"hello" and s.get("uploads/none.txt") is None
    assert [k for k, _ in s.list("uploads")] == ["uploads/x.txt"]
    with blob.local_copy("uploads/x.txt", ".txt") as p:
        assert p.read_text() == "hello"
    s.delete("uploads/x.txt")
    assert s.list("uploads") == []


def test_an_upload_and_the_http_cache_retention_work_on_object_storage(s3, tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PIPELINE_DB", tmp_path / "pipeline.duckdb")
    up = upload_store.save("note.txt", b"x" * 100, "txt", None)
    assert up["path"] == f"uploads/{up['upload_id']}.txt"
    assert s3.get_object(Bucket="procintel", Key=f"raw/{up['path']}")["Body"].read() == b"x" * 100
    assert process.run(up["upload_id"])["status"] == "needs_review"   # read back from S3: too little text, no crash
    blob.store().put("cache/http/old.json", b"{}")
    assert retention.http_cache(datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1), dry=True) == 1   # everything is "old" then
    assert retention.http_cache(datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1), dry=False) == 0
    assert retention.http_cache(datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1), dry=False) == 1
    assert blob.store().list("cache/http") == []


def test_a_bad_blob_url_is_refused(monkeypatch):
    monkeypatch.setenv("PROCINTEL_BLOB_URL", "ftp://somewhere")
    with pytest.raises(ValueError):
        blob.store()
