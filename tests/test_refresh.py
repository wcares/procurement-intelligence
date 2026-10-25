from procintel import refresh


def snap(docs, notices, status, labelled=10, chunks=100, model=None):
    return {"docs": docs, "notices": set(notices), "status": status, "labelled_packages": labelled, "chunks": chunks,
            "model": model or {"days_p50_mae": 70.0}}


def test_diff_reports_added_changed_and_removed_items():
    before = snap({"d1": "h1", "d2": "h2", "d3": "h3"}, ["n1", "n2"], {"P1": "Active", "P2": "Active"})
    after = snap({"d1": "h1", "d2": "CHANGED", "d4": "h4"}, ["n1", "n2", "n3", "n4"], {"P1": "Closed", "P2": "Active"},
                 labelled=12, chunks=110, model={"days_p50_mae": 68.0})
    d = refresh.diff(before, after)
    assert d["documents_added"] == ["d4"] and d["documents_changed"] == ["d2"] and d["documents_removed"] == ["d3"]
    assert d["notices_added"] == 2 and d["notices_removed"] == 0
    assert d["projects_status_changed"] == ["P1"]
    assert d["labelled_packages"] == [10, 12] and d["model_metrics"] == {"days_p50_mae": [70.0, 68.0]}


def test_diff_of_identical_snapshots_is_empty():
    s = snap({"d1": "h1"}, ["n1"], {"P1": "Active"})
    d = refresh.diff(s, s)
    assert not (d["documents_added"] or d["documents_changed"] or d["documents_removed"] or d["notices_added"]
                or d["projects_status_changed"])
