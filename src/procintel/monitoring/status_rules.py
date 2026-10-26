"""The parameters that decide a package's status, by configuration (paths.STATUS_RULES, edited on the Pipeline area's
Status rules tab; absent: DEFAULTS). Validated before saving, like the pipeline rules.

    stale_quantile        no award and open longer than this share of comparable awarded tenders took: stale
    stale_max_days        ... or open longer than this many days, whatever the comparison says (None: no cap)
    contract_end_margin   a contract counts as ended this many days after its award date + stated duration
    estimate_contract_end awarded with no stated duration: use the median duration of comparable contracts
    project_overrides     project facts that end everything in it: "closed" (status Closed), "closing_passed"
                          (closing date in the past), "completion_report" (an ICR published)
"""
from __future__ import annotations

import json

from procintel.core import paths

DEFAULTS = {"stale_quantile": 0.99, "stale_max_days": 730, "contract_end_margin": 90, "estimate_contract_end": True,
            "project_overrides": ["closed", "closing_passed", "completion_report"]}
OVERRIDES = ("closed", "closing_passed", "completion_report")


def active() -> dict:
    f = paths.STATUS_RULES
    saved = json.loads(f.read_text()) if f.exists() else {}
    return DEFAULTS | {k: v for k, v in saved.items() if k in DEFAULTS}


def validate(p: dict) -> list[str]:
    errors = []
    if unknown := set(p) - set(DEFAULTS):
        errors.append(f"unknown parameters {sorted(unknown)}")
    q = p.get("stale_quantile", DEFAULTS["stale_quantile"])
    if not isinstance(q, (int, float)) or not 0.5 <= q < 1:
        errors.append("stale_quantile must be between 0.5 and 1")
    m = p.get("stale_max_days", DEFAULTS["stale_max_days"])
    if m is not None and (not isinstance(m, int) or m < 30):
        errors.append("stale_max_days must be a whole number of days, at least 30, or empty")
    g = p.get("contract_end_margin", DEFAULTS["contract_end_margin"])
    if not isinstance(g, int) or g < 0:
        errors.append("contract_end_margin must be a whole number of days, 0 or more")
    if not isinstance(p.get("estimate_contract_end", True), bool):
        errors.append("estimate_contract_end must be true or false")
    o = p.get("project_overrides", [])
    if not isinstance(o, list) or set(o) - set(OVERRIDES):
        errors.append(f"project_overrides must be a list of {', '.join(OVERRIDES)}")
    return errors


def save(p: dict) -> dict:
    if errors := validate(p):
        raise ValueError("; ".join(errors))
    merged = DEFAULTS | p
    diff = {k: v for k, v in merged.items() if DEFAULTS[k] != v}
    if diff:
        paths.STATUS_RULES.parent.mkdir(parents=True, exist_ok=True)
        paths.STATUS_RULES.write_text(json.dumps(diff, indent=1))
    else:
        paths.STATUS_RULES.unlink(missing_ok=True)
    return active()


def customised() -> bool:
    return paths.STATUS_RULES.exists()
