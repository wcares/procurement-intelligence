"""Raw files by key: uploaded documents ("uploads/<id>.<format>") and the World Bank API cache ("cache/http/<hash>.json"),
in the data folder or in object storage, chosen by configuration (docs/architecture-principles.md):

    PROCINTEL_BLOB_URL   empty: the data folder (paths.DATA_DIR/<key>, the layout used so far, so nothing moves)
                         s3://bucket/prefix: S3 or an S3-compatible store (MinIO); credentials the standard AWS way
                         (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY, never in our settings), and
    PROCINTEL_S3_ENDPOINT  for MinIO or another S3-compatible service, e.g. http://minio:9000

Tables and vectors are not here: they live in DuckDB or Postgres and the vector index (procintel.core.db, vector_index).
"""
from __future__ import annotations

import contextlib
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Protocol

from procintel.core import paths


class Store(Protocol):
    def get(self, key: str) -> bytes | None: ...
    def put(self, key: str, data: bytes) -> None: ...
    def delete(self, key: str) -> None: ...
    def list(self, prefix: str) -> list[tuple[str, datetime]]: ...   # (key, last modified, naive UTC)


class LocalStore:
    def __init__(self, root: Path | None = None):
        self.root = root

    def _path(self, key: str) -> Path:
        return (self.root or paths.DATA_DIR) / key   # read at call time: tests and settings move DATA_DIR

    def get(self, key: str) -> bytes | None:
        p = self._path(key)
        return p.read_bytes() if p.exists() else None

    def put(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def list(self, prefix: str) -> list[tuple[str, datetime]]:
        base = self._path(prefix)
        if not base.exists():
            return []
        root = self.root or paths.DATA_DIR
        return [(str(p.relative_to(root)), datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).replace(tzinfo=None))
                for p in base.rglob("*") if p.is_file()]


class S3Store:
    def __init__(self, bucket: str, prefix: str = "", client=None):
        import boto3   # installed with litellm; only needed when object storage is configured
        self.bucket, self.prefix = bucket, prefix.strip("/")
        self.s3 = client or boto3.client("s3", endpoint_url=os.environ.get("PROCINTEL_S3_ENDPOINT") or None)

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def get(self, key: str) -> bytes | None:
        try:
            return self.s3.get_object(Bucket=self.bucket, Key=self._key(key))["Body"].read()
        except self.s3.exceptions.NoSuchKey:
            return None

    def put(self, key: str, data: bytes) -> None:
        self.s3.put_object(Bucket=self.bucket, Key=self._key(key), Body=data)

    def delete(self, key: str) -> None:
        self.s3.delete_object(Bucket=self.bucket, Key=self._key(key))

    def list(self, prefix: str) -> list[tuple[str, datetime]]:
        out, cut = [], len(self.prefix) + 1 if self.prefix else 0
        for page in self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=self._key(prefix)):
            out += [(o["Key"][cut:], o["LastModified"].astimezone(timezone.utc).replace(tzinfo=None))
                    for o in page.get("Contents", [])]
        return out


_store: Store | None = None
_url: str | None = None


def store() -> Store:
    """The configured store (rebuilt when PROCINTEL_BLOB_URL changes)."""
    global _store, _url
    url = os.environ.get("PROCINTEL_BLOB_URL", "")
    if _store is None or url != _url:
        if url.startswith("s3://"):
            bucket, _, prefix = url[5:].partition("/")
            _store = S3Store(bucket, prefix)
        elif url:
            raise ValueError(f"PROCINTEL_BLOB_URL must be empty or s3://bucket/prefix, not {url!r}")
        else:
            _store = LocalStore()
        _url = url
    return _store


def backend() -> str:
    return "s3" if os.environ.get("PROCINTEL_BLOB_URL", "").startswith("s3://") else "local"


@contextlib.contextmanager
def local_copy(key: str, suffix: str = "") -> Iterator[Path]:
    """A file path for readers that need one (pdf, docx): the file itself locally, a temporary copy from S3."""
    s = store()
    if isinstance(s, LocalStore):
        yield s._path(key)
        return
    data = s.get(key)
    if data is None:
        raise FileNotFoundError(key)
    with tempfile.NamedTemporaryFile(suffix=suffix) as f:
        f.write(data)
        f.flush()
        yield Path(f.name)
