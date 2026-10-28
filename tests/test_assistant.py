"""The planning chat's checks: what the model proposes is validated against the data before it touches the plan."""
from __future__ import annotations

from datetime import date

import pytest

from procintel.assistant import context, interpret, resolve

TODAY = date(2026, 10, 27)
OPTIONS = {
    "countries": [{"code": c, "name": n, "region": "r"} for c, n in [
        ("KE", "Republic of Kenya"), ("TZ", "United Republic of Tanzania"), ("CG", "Republic of Congo"),
        ("GN", "Republic of Guinea"), ("GW", "Republic of Guinea-Bissau"), ("TR", "Republic of Turkiye"),
        ("LA", "Lao People's Democratic Republic"), ("BD", "People's Republic of Bangladesh")]],
    "sectors": ["Rural and Inter-Urban Roads", "Sanitation"],
    "procGroups": [{"code": g, "label": g} for g in ("GO", "CW", "CS", "NC")],
    "methods": [
        {"code": "RFB", "label": "Request for Bids", "procGroups": ["CW", "GO", "NC"], "n": 1},
        {"code": "RFQ", "label": "Request for Quotations", "procGroups": ["CW", "GO", "NC"], "n": 1},
        {"code": "QCBS", "label": "Quality And Cost-Based Selection", "procGroups": ["CS"], "n": 1},
        {"code": "CQS", "label": "Consultant Qualification Selection", "procGroups": ["CS"], "n": 1}],
}


@pytest.mark.parametrize("name,code", [
    ("Kenya", "KE"), ("kenia", "KE"), ("KE", "KE"), ("Tanzania", "TZ"), ("Turkey", "TR"), ("Laos", "LA"),
    ("Congo", "CG"), ("Guinea", "GN"), ("Guinea-Bissau", "GW"), ("Bangladesh", "BD"),
    ("DR Congo", None),      # a different country from Republic of Congo: asking is right, guessing is not
    ("Narnia", None), ("", None), (None, None)])
def test_country_matching(name, code):
    assert resolve.match_country(name, OPTIONS) == code


def test_new_packages_get_checked_methods_and_stated_assumptions():
    raw = {"intent": "update_plan", "country": "Kenya", "packages": [
        {"name": "Road works", "action": "add", "type": "works", "value_usd": 5e6},
        {"name": "Supervision", "action": "add", "type": "consulting", "method": "RFQ"}]}   # RFQ is not a consulting method
    r = resolve.resolve(raw, OPTIONS, {}, TODAY)
    works, sup = r["plan"]["packages"]
    assert r["plan"]["countryCode"] == "KE"
    assert (works["procGroup"], works["methodCode"], works["estimatedValueUsd"]) == ("CW", "RFB", 5e6)
    assert (sup["procGroup"], sup["methodCode"]) == ("CS", "QCBS")
    assert len(r["assumptions"]) == 2 and "not used for consulting" in r["assumptions"][1]
    assert works["id"] != sup["id"]


def test_goods_default_depends_on_value():
    small = resolve.resolve({"intent": "update_plan", "country": "Kenya", "packages": [{"name": "A", "type": "goods", "value_usd": 100e3}]}, OPTIONS, {}, TODAY)
    big = resolve.resolve({"intent": "update_plan", "country": "Kenya", "packages": [{"name": "A", "type": "goods", "value_usd": 2e6}]}, OPTIONS, {}, TODAY)
    assert small["plan"]["packages"][0]["methodCode"] == "RFQ" and big["plan"]["packages"][0]["methodCode"] == "RFB"


def test_dependency_can_point_at_a_package_added_in_the_same_message():
    raw = {"intent": "update_plan", "country": "Kenya", "packages": [
        {"name": "Equipment", "action": "add", "type": "goods", "after": "Works"},
        {"name": "Works", "action": "add", "type": "works"}]}
    pk = {p["name"]: p for p in resolve.resolve(raw, OPTIONS, {}, TODAY)["plan"]["packages"]}
    assert pk["Equipment"]["after"] == pk["Works"]["id"]


def test_unknown_link_target_is_reported_not_invented():
    raw = {"intent": "update_plan", "country": "Kenya", "packages": [{"name": "A", "type": "goods", "after": "Nothing"}]}
    r = resolve.resolve(raw, OPTIONS, {}, TODAY)
    assert "after" not in r["plan"]["packages"][0] and any("Nothing" in n for n in r["notes"])


def test_update_and_remove_touch_the_named_package_only():
    plan = {"countryCode": "KE", "projectStart": "2026-10-27", "packages": [
        {"id": "p1", "name": "Road works", "procGroup": "CW", "methodCode": "RFB"},
        {"id": "p2", "name": "Equipment", "procGroup": "GO", "methodCode": "RFQ", "after": "p1"}]}
    upd = resolve.resolve({"intent": "update_plan", "packages": [{"name": "Road works", "action": "update", "method": "RFQ"}]}, OPTIONS, plan, TODAY)
    assert [p["methodCode"] for p in upd["plan"]["packages"]] == ["RFQ", "RFQ"] and plan["packages"][0]["methodCode"] == "RFB"
    rem = resolve.resolve({"intent": "update_plan", "packages": [{"name": "road", "action": "remove"}]}, OPTIONS, plan, TODAY)
    assert [p["id"] for p in rem["plan"]["packages"]] == ["p2"] and "after" not in rem["plan"]["packages"][0]


def test_a_package_without_a_type_is_a_question_not_a_guess():
    r = resolve.resolve({"intent": "update_plan", "country": "Kenya", "packages": [{"name": "Bridge", "action": "add"}]}, OPTIONS, {}, TODAY)
    assert r["plan"]["packages"] == [] and any("works, goods" in n for n in r["notes"])


def test_missing_or_unknown_country_is_asked_for():
    r = resolve.resolve({"intent": "update_plan", "packages": [{"name": "Bridge", "type": "works"}]}, OPTIONS, {}, TODAY)
    assert r["needs"] == ["country"] and "Which country" in resolve.compose_reply(r)
    r = resolve.resolve({"intent": "update_plan", "country": "Narnia", "packages": [{"name": "Road", "type": "works"}]}, OPTIONS, {}, TODAY)
    assert r["plan"]["countryCode"] is None and "Narnia" in resolve.compose_reply(r)


def test_dates_months_resolve_in_code_not_in_the_model():
    r = resolve.resolve({"intent": "update_plan", "start": "2027-01-31", "deadline_months": 1}, OPTIONS, {}, TODAY)
    assert r["plan"]["projectStart"] == "2027-01-31" and r["plan"]["deadline"] == "2027-02-28"
    bad = resolve.resolve({"intent": "update_plan", "start": "soon", "deadline": "31 June"}, OPTIONS, {"projectStart": "2026-11-01"}, TODAY)
    assert bad["plan"]["projectStart"] == "2026-11-01" and bad["plan"]["deadline"] is None


def test_bad_values_are_ignored():
    raw = {"intent": "update_plan", "country": "Kenya", "packages": [{"name": "A", "type": "works", "value_usd": -5, "sector": "Invented sector"}]}
    p = resolve.resolve(raw, OPTIONS, {}, TODAY)["plan"]["packages"][0]
    assert "estimatedValueUsd" not in p and "sector" not in p


def test_statistics_only_for_the_overviews_measures():
    ok = resolve.resolve({"intent": "ask_statistics", "statistic": {"measure": "delay", "group": "method"}}, OPTIONS, {}, TODAY)
    assert ok["intent"] == "ask_statistics" and ok["statistic"] == {"measure": "delay", "group": "method"}
    moved = resolve.resolve({"intent": "ask_statistics", "statistic": {"measure": "rebid", "group": "method"}}, OPTIONS, {}, TODAY)
    assert moved["statistic"] == {"measure": "rebid", "group": "country"} and "not counted by method" in moved["notes"][0]
    assert resolve.resolve({"intent": "ask_statistics", "statistic": {"measure": "cpia", "group": "sector"}}, OPTIONS, {}, TODAY)["statistic"]["group"] == "country"
    nope = resolve.resolve({"intent": "ask_statistics", "statistic": {"measure": "profit", "group": "method"}, "evidence_question": "Which method is most profitable?"}, OPTIONS, {}, TODAY)
    assert nope["intent"] == "ask_evidence" and nope["statistic"] is None   # no measure fits: the reports may still answer


def test_evidence_without_a_question_is_small_talk():
    assert resolve.resolve({"intent": "ask_evidence"}, OPTIONS, {}, TODAY)["intent"] == "other"
    assert resolve.resolve({"intent": "launch_missiles"}, OPTIONS, {}, TODAY)["intent"] == "other"


def test_plan_size_is_capped():
    raw = {"intent": "update_plan", "country": "Kenya", "packages": [{"name": f"P{i}", "type": "goods"} for i in range(30)]}
    assert len(resolve.resolve(raw, OPTIONS, {}, TODAY)["plan"]["packages"]) == resolve.MAX_PACKAGES


def test_parse_takes_the_first_json_object_in_fenced_or_chatty_text():
    assert interpret.parse('```json\n{"intent": "other"}\n```') == {"intent": "other"}
    assert interpret.parse('Sure! {"intent": "other", "reply": "hi"} hope that helps') == {"intent": "other", "reply": "hi"}
    assert interpret.parse("no json here") == {} and interpret.parse("{broken") == {}


def test_context_guard_warns_then_stops():
    short = context.usage("fixed " * 100, [{"role": "user", "content": "hello"}])
    assert not short["warn"] and not short["full"]
    history = [{"role": "user", "content": "word " * 380}] * 10   # about 1,900 characters each
    near = context.usage("fixed " * 1000, history[:7])
    full = context.usage("fixed " * 1000, history)
    assert near["warn"] and not near["full"] and full["full"]


def test_adding_a_package_never_merges_into_a_similar_name():
    plan = {"countryCode": "KE", "projectStart": "2026-10-27", "packages": [{"id": "p1", "name": "Road works 10", "procGroup": "CW", "methodCode": "RFB"}]}
    r = resolve.resolve({"intent": "update_plan", "packages": [{"name": "Road works 1", "action": "add", "type": "works"}]}, OPTIONS, plan, TODAY)
    assert [p["name"] for p in r["plan"]["packages"]] == ["Road works 10", "Road works 1"]
    two = {"countryCode": "KE", "projectStart": "2026-10-27", "packages": [
        {"id": "p1", "name": "Road works north", "procGroup": "CW", "methodCode": "RFB"}, {"id": "p2", "name": "Road works south", "procGroup": "CW", "methodCode": "RFB"}]}
    amb = resolve.resolve({"intent": "update_plan", "packages": [{"name": "road works", "action": "remove"}]}, OPTIONS, two, TODAY)
    assert len(amb["plan"]["packages"]) == 2 and any("no package called" in n for n in amb["notes"])   # ambiguous: nothing removed


def test_a_blank_package_never_matches_a_name():
    plan = {"countryCode": "KE", "projectStart": "2026-10-27", "packages": [{"id": "p1", "name": "", "procGroup": "CW", "methodCode": "RFB"}]}
    r = resolve.resolve({"intent": "update_plan", "packages": [{"name": "Road works", "action": "add", "type": "works", "value_usd": 5e6}]}, OPTIONS, plan, TODAY)
    assert [p["name"] for p in r["plan"]["packages"]] == ["", "Road works"] and "Added Road works" in r["changes"][0]
