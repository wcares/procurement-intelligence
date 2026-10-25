from procintel.flag_evidence import NOTICE_URL, FlagEvidence


def make(packages, events=None):
    fe = FlagEvidence.__new__(FlagEvidence)
    fe.packages, fe.events = packages, events or {}
    return fe


def pkg(pid, cc, days, group="CW", method="RFB"):
    return {"package_id": pid, "project_id": "P1", "country_code": cc, "proc_group": group, "method_code": method,
            "description": f"works {pid}", "tender_to_award_days": days, "award_year": 2022, "notice_id": f"OP{pid}"}


BENCH = {"CW/RFB": {"n": 12}, "CW": {"n": 30}}
REQ = {"countryCode": "KE", "procGroup": "CW", "methodCode": "RFB"}


def test_timeline_flag_lists_slow_comparable_packages_country_first_with_notice_links():
    fe = make([pkg("a", "BD", 400), pkg("b", "KE", 200), pkg("c", "KE", 100), pkg("d", "BD", 300, method="NCB")])
    [f] = fe.attach([{"id": "long-cycle"}], REQ, BENCH, None, [])
    assert [e["ref"] for e in f["evidence"]] == ["b", "a"]               # over 180 days, same method, Kenya first
    assert f["evidence"][0]["url"] == NOTICE_URL.format("OPb") and "200 days" in f["evidence"][0]["detail"]


def test_rebid_evidence_has_one_item_per_project_report_first():
    rows = [{"project_id": "P1", "source": "icr", "ref": "d1:3", "quote": "the works were re-tendered", "pdf": "u", "notice": None},
            {"project_id": "P1", "source": "icr", "ref": "d1:9", "quote": "again", "pdf": "u", "notice": None},
            {"project_id": "P2", "source": "notice_reference", "ref": "P2/X-1", "quote": "lot 1", "pdf": None, "notice": "OP9"}]
    fe = make([], {"rebid": {"KE": rows}})
    [f, m] = fe.attach([{"id": "rebid"}, {"id": "model-timeline"}], REQ, BENCH, None, [])
    assert [e["ref"] for e in f["evidence"]] == ["d1:3", "P2/X-1"] and f["evidence"][1]["url"] == NOTICE_URL.format("OP9")
    assert m["evidence"] == []                                            # model flags rest on no particular record
