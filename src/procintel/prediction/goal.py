"""Goal seeking (tracker U10): a desired outcome for a package (awarded within N days) and the set-ups that made it
most likely in the past. The fixed inputs (country, sector, what is bought) are held; the choosable ones are tried:
the procurement method (those used for this kind of purchase in the data) and, when a value is given, splitting the
package into 1 to max_lots equal lots (a smaller contract per lot).

Each set-up is scored on the packages awarded with enough follow-up (procintel.prediction.predict.load_frame, the same
history the model trains on): the share of comparable packages awarded within the target, with n and the scope,
comparable being the same group and method, narrowed to lots of similar value (within VALUE_BAND in log10) and the
country's region when each keeps at least MIN_N packages. The timeline model's median and its chance of over 180 days
sit beside it where the model is used. Set-ups ranked by that share; fewer than MIN_N comparable: "not enough evidence".

Two guards, stated on every answer: methods have value thresholds in the Procurement Regulations, so a lot value
outside the range a method was used for in the data is flagged ("check the thresholds") rather than offered as is; and
this is association: packages set up this way were faster, which does not show that changing the set-up makes a given
package faster (smaller and simpler contracts tend to use the faster methods).
"""
from __future__ import annotations

import math
from datetime import date

import pandas as pd

from procintel.prediction import predict
from procintel.prediction.stats import MIN_BENCH_N

MIN_N = MIN_BENCH_N
VALUE_BAND = 0.5   # log10: lots within about x0.3 to x3 of the value
CAVEATS = ["Packages set up this way were awarded faster in the past; that does not show a change of set-up makes "
           "this package faster (smaller and simpler contracts tend to use the faster methods).",
           "The Procurement Regulations' value thresholds decide which methods a contract may use; set-ups whose lot "
           "value lies outside the values a method was used for in the data are flagged."]


def _scope(history: pd.DataFrame, group: str, method: str, log_value: float | None, region: str | None):
    base = history[(history.proc_group == group) & (history.method_code == method)]
    label = f"{group} via {method}"
    f = base
    if log_value is not None:
        near = f[(f.log_value_usd - log_value).abs() <= VALUE_BAND]
        if len(near) >= MIN_N:
            f, label = near, label + ", lots of similar value"
    if region:
        local = f[f.region == region]
        if len(local) >= MIN_N:
            f, label = local, label + f", {region}"
    return f, label


def options(history: pd.DataFrame, req: dict, target_days: int, region: str | None, gov: list[dict],
            bundle: dict | None = None, labels: dict | None = None, max_lots: int = 4) -> dict:
    group = req["procGroup"]
    value = req.get("estimatedValueUsd")
    methods = sorted(m for m, n in history[history.proc_group == group].method_code.value_counts().items() if n >= MIN_N)
    lot_counts = range(1, max_lots + 1) if value else [1]
    out = []
    for m in methods:
        used = history[(history.proc_group == group) & (history.method_code == m)].log_value_usd.dropna()
        lo, hi = (used.quantile(0.05), used.quantile(0.95)) if len(used) >= MIN_N else (None, None)
        for k in lot_counts:
            lot = value / k if value else None
            lv = math.log10(lot) if lot else None
            f, scope = _scope(history, group, m, lv, region)
            days = f.tender_to_award_days.dropna()
            row = {"method": m, "methodLabel": (labels or {}).get(m, m), "lots": k, "lotValueUsd": round(lot) if lot else None,
                   "n": int(len(days)), "scope": scope}
            if len(days) >= MIN_N:
                row |= {"share": round(float((days <= target_days).mean()), 3), "medianDays": round(float(days.median())),
                        "p90Days": round(float(days.quantile(0.9)))}
            else:
                row |= {"share": None, "note": "not enough evidence"}
            if lv is not None and lo is not None and not (lo <= lv <= hi):
                row["flag"] = (f"a lot of about US${lot:,.0f} is outside the values {m} was used for in the data "
                               f"(US${10 ** lo:,.0f} to US${10 ** hi:,.0f}): check the Procurement Regulations' thresholds")
            if bundle:
                p = predict.predict_one(bundle, {"proc_group": group, "method_code": m, "region": region,
                                                 "sector": req.get("sector") or None, "tender_start": date.today().isoformat(),
                                                 "value_usd": lot, **{f"cpia_{g['indicator']}": g["value"] for g in gov},
                                                 **(req.get("project") or {})})
                if p["use"].get("days_p50"):
                    row["modelMedianDays"] = round(float(p["p50"]))
                if p["use"].get("over_180"):
                    row["modelOver180"] = round(float(p["p_long"]), 3)
            out.append(row)
    out.sort(key=lambda r: (r["share"] is None, "flag" in r, -(r["share"] or 0), r["lots"]))
    return {"target": {"days": target_days}, "options": out, "caveats": CAVEATS,
            "note": None if value else "Give an estimated value to compare splitting the package into lots."}
