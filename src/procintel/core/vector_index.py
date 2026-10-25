"""Vector search behind one interface, so the vector store is a setting.

PROCINTEL_VECTOR_URL selects it:
  (unset)                  vectors loaded from the database into memory and scored with numpy (fine for ~20,000)
  http://host:6333         Qdrant: vectors live in collections, only the ranking comes back. Fill or refresh the
                           collections with `python -m procintel.core.vector_index sync` (refresh does it after embedding).

An index is either a numpy matrix (in memory) or a QdrantIndex; ranking() takes either and returns row positions,
best first, restricted to the rows allowed by a boolean mask.
"""
from __future__ import annotations

import logging
import math
import os
import uuid

import numpy as np
import requests

from procintel.core import db, embed

log = logging.getLogger(__name__)
NAMESPACE = uuid.UUID("6f0c2b55-9a43-4a3e-9d0c-3f7a1a9c2e11")  # point id = uuid5(NAMESPACE, key): stable across syncs
FILTER_MAX = 2000      # up to this many allowed rows, Qdrant filters by id; above it, over-fetch and filter here
BATCH = 512
# current vectors only: a passage's vector must match its present text (as embed.load checks)
SOURCES = {
    "chunks": """SELECT v.chunk_id, v.vec FROM chunk_vec v JOIN chunk c USING (chunk_id)
                 WHERE v.model = ? AND v.dim = ? AND v.text_hash = sha256(c.section || chr(0) || c.text)[:16]""",
    "packages": """SELECT v.package_id, v.vec FROM package_vec v JOIN package k USING (package_id)
                   WHERE v.model = ? AND v.dim = ?""",
}


def url() -> str:
    return os.environ.get("PROCINTEL_VECTOR_URL", "").strip().rstrip("/")


def backend() -> str:
    return "qdrant" if url() else "memory"


def collection(kind: str) -> str:
    prefix = os.environ.get("PROCINTEL_VECTOR_PREFIX", "procintel_")
    return f"{prefix}{kind}_{embed.dim()}"   # one collection per stored dimension


def point_id(key: str) -> str:
    return str(uuid.uuid5(NAMESPACE, key))


class QdrantIndex:
    def __init__(self, kind: str, keys: list[str]):
        self.name, self.keys = collection(kind), keys
        self._pos = {k: i for i, k in enumerate(keys)}

    def count(self) -> int:
        r = requests.post(f"{url()}/collections/{self.name}/points/count", json={"exact": True}, timeout=30)
        return r.json()["result"]["count"] if r.ok else -1

    def ranking(self, q: np.ndarray, mask: np.ndarray, limit: int) -> list[int]:
        allowed = np.flatnonzero(mask)
        body: dict = {"query": [float(x) for x in q], "with_payload": ["key"]}
        if len(allowed) <= FILTER_MAX:
            body |= {"limit": limit, "filter": {"must": [{"has_id": [point_id(self.keys[i]) for i in allowed]}]}}
        else:  # over-fetch in proportion to what the mask removes, then filter here
            body["limit"] = min(len(mask), math.ceil(limit * len(mask) / len(allowed) * 2))
        r = requests.post(f"{url()}/collections/{self.name}/points/query", json=body, timeout=30)
        r.raise_for_status()
        out = []
        for p in r.json()["result"]["points"]:
            i = self._pos.get(p["payload"]["key"])
            if i is not None and mask[i]:
                out.append(i)
        return out[:limit]


def ranking(index, q: np.ndarray, mask: np.ndarray, limit: int) -> list[int]:
    if isinstance(index, np.ndarray):
        scores = np.where(mask, index @ q, -np.inf)
        top = np.argpartition(-scores, min(limit, len(scores) - 1))[:limit]
        return [int(i) for i in top[np.argsort(-scores[top])] if np.isfinite(scores[i])]
    return index.ranking(q, mask, limit)


def open_index(kind: str, keys: list[str], load_memory):
    """The configured index for these keys, or None when it does not hold a current vector for every key."""
    if backend() == "memory":
        return load_memory()
    ix = QdrantIndex(kind, keys)
    n = ix.count()
    if n != len(keys):
        log.warning("Qdrant collection %s holds %d vectors for %d %s; run `python -m procintel.core.vector_index sync`",
                    ix.name, n, len(keys), kind)
        return None
    return ix


def sync(kind: str) -> int:
    """Replace the Qdrant collection for kind with the current vectors of the configured model and dimension."""
    con = db.connect(read_only=True)
    try:
        rows = con.execute(SOURCES[kind], [embed.model_name(), embed.dim()]).fetchall()
    finally:
        con.close()
    name = collection(kind)
    requests.delete(f"{url()}/collections/{name}", timeout=60)
    requests.put(f"{url()}/collections/{name}", json={"vectors": {"size": embed.dim(), "distance": "Dot"}},
                 timeout=60).raise_for_status()  # stored vectors are unit length, so dot product = cosine
    for s in range(0, len(rows), BATCH):
        pts = [{"id": point_id(k), "vector": [float(x) for x in v], "payload": {"key": k}} for k, v in rows[s:s + BATCH]]
        requests.put(f"{url()}/collections/{name}/points?wait=true", json={"points": pts}, timeout=120).raise_for_status()
    print(f"{name}: {len(rows)} vectors")
    return len(rows)


if __name__ == "__main__":
    import sys
    if sys.argv[1:] != ["sync"] or backend() != "qdrant":
        sys.exit("usage: PROCINTEL_VECTOR_URL=http://host:6333 python -m procintel.core.vector_index sync")
    for k in SOURCES:
        sync(k)
