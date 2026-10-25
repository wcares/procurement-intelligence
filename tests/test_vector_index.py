import numpy as np

from procintel import vector_index as vi


class FakeResponse:
    def __init__(self, body):
        self.body, self.ok = body, True

    def json(self):
        return self.body

    def raise_for_status(self):
        pass


def test_memory_ranking_respects_the_mask():
    m = np.array([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]], dtype=np.float32)
    assert vi.ranking(m, np.array([1.0, 0.0]), np.array([False, True, True]), 5) == [1, 2]


def test_qdrant_filters_by_id_for_small_masks_and_over_fetches_for_large(monkeypatch):
    monkeypatch.setenv("PROCINTEL_VECTOR_URL", "http://q:6333")
    keys = [f"k{i}" for i in range(10)]
    sent = []

    def post(url, json, timeout):
        sent.append(json)
        return FakeResponse({"result": {"points": [{"payload": {"key": k}} for k in ("k3", "k1", "k7", "zz")]}})

    monkeypatch.setattr(vi.requests, "post", post)
    ix = vi.QdrantIndex("chunks", keys)
    small = np.zeros(10, bool); small[[1, 3]] = True
    assert ix.ranking(np.ones(2), small, 5) == [3, 1]                         # k7 masked out, unknown key ignored
    assert sent[-1]["filter"]["must"][0]["has_id"] == [vi.point_id("k1"), vi.point_id("k3")]
    monkeypatch.setattr(vi, "FILTER_MAX", 1)
    big = np.ones(10, bool); big[7] = False
    assert ix.ranking(np.ones(2), big, 2) == [3, 1]
    assert "filter" not in sent[-1] and sent[-1]["limit"] >= 2


def test_open_index_refuses_an_incomplete_collection(monkeypatch):
    monkeypatch.setenv("PROCINTEL_VECTOR_URL", "http://q:6333")
    monkeypatch.setattr(vi.QdrantIndex, "count", lambda self: 3)
    assert vi.open_index("chunks", ["a", "b", "c", "d"], lambda: "memory") is None
    monkeypatch.delenv("PROCINTEL_VECTOR_URL")
    assert vi.open_index("chunks", ["a"], lambda: "memory") == "memory"
