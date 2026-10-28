"""Measure the interpreter on eval/plan_chat_cases.jsonl: for each message, does the checked plan match what a planner meant?

    PYTHONPATH=src python -m procintel.assistant.evaluate [substring of case ids to run]

The model comes from the usual PROCINTEL_LLM_* settings, so the same run measures any model. A case passes when every
field it lists in `expect` matches; the failing fields are printed so the prompt or the model can be fixed on evidence.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

from procintel.assistant import interpret, resolve
from procintel.core import db, llm, paths
from procintel.prediction import stats

CASES = paths.EVAL_DIR / "plan_chat_cases.jsonl"
TODAY = date(2026, 10, 27)   # fixed, so "in March" and "within 12 months" have one right answer


def check(expect: dict, out: dict, options: dict) -> list[str]:
    bad: list[str] = []
    plan = out["plan"]
    if "intent" in expect and out["intent"] != expect["intent"]:
        bad.append(f"intent {out['intent']} != {expect['intent']}")
    if "country" in expect and plan["countryCode"] != expect["country"]:
        bad.append(f"country {plan['countryCode']} != {expect['country']}")
    if expect.get("needs_country") and "country" not in out["needs"] and plan["countryCode"]:
        bad.append("should have asked for the country")
    if "n_packages" in expect and len(plan["packages"]) != expect["n_packages"]:
        bad.append(f"{len(plan['packages'])} packages != {expect['n_packages']}")
    for key in ("start", "deadline"):
        want = expect.get(key)
        got = plan["projectStart"] if key == "start" else plan["deadline"]
        if want and got != want:
            bad.append(f"{key} {got} != {want}")
    for i, want in enumerate(expect.get("packages", [])):
        if i >= len(plan["packages"]):
            bad.append(f"package {i} missing")
            continue
        p = plan["packages"][i]
        if "group" in want and p["procGroup"] != want["group"]:
            bad.append(f"package {i} type {p['procGroup']} != {want['group']}")
        if "method" in want and p["methodCode"] != want["method"]:
            bad.append(f"package {i} method {p['methodCode']} != {want['method']}")
        if "value" in want and abs((p.get("estimatedValueUsd") or 0) - want["value"]) > 0.01 * want["value"]:
            bad.append(f"package {i} value {p.get('estimatedValueUsd')} != {want['value']}")
        if "after" in want and p.get("after") != plan["packages"][want["after"]]["id"]:
            bad.append(f"package {i} should follow package {want['after']}")
    if "stat" in expect and out["statistic"] != expect["stat"]:
        bad.append(f"statistic {out['statistic']} != {expect['stat']}")
    return bad


def run() -> int:
    options = stats.options(db.connect(paths.DB_PATH))
    cases = [json.loads(l) for l in CASES.read_text().splitlines() if l.strip()]
    if len(sys.argv) > 1:
        cases = [c for c in cases if sys.argv[1] in c["id"]]
    passed = 0
    t0 = time.time()
    for c in cases:
        plan = c.get("plan", {})
        history = [{"role": "user", "content": c["message"]}]
        try:
            raw = interpret.interpret(history, options, interpret.with_names(plan, options), c.get("results", ""), TODAY)
            out = resolve.resolve(raw, options, plan, TODAY)
            bad = check(c["expect"], out, options) if raw else ["no JSON from the model"]
        except Exception as e:  # a model that fails to answer is a failed case, not a crashed run
            bad = [f"error: {e}"]
        passed += not bad
        print(f"{'PASS' if not bad else 'FAIL'}  {c['id']:16s} {'; '.join(bad)}", flush=True)
    print(f"\n{passed}/{len(cases)} passed in {time.time() - t0:.0f}s with {llm.model_name()}")
    return len(cases) - passed


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
