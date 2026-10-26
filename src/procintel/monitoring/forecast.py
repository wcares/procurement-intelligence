"""Forecasts from where a package is now (tracker U9 b, c). One entry point, `forecast(facts, history)`, for a package
in the data and for one a planner describes: what is known so far (group, method, tender date, award date if any,
stated contract duration, whether a notice was re-issued, the project's closing date) against the history of comparable
awarded packages.

    still in bidding, open a days: a Kaplan-Meier estimate (procintel.monitoring.survival) over comparable tenders,
        awarded ones as events and ones still open today as censored at their age, given that this one is still open
        at a days: median and 1 in 10 remaining, the chance of an award within 30 and 90 days, the expected award
        date. Stale tenders (open past any normal time) stay out. Without package statuses in the history (tests,
        older callers): the comparable awarded tenders that took longer than a, as before.
    awarded: the expected contract end, from the stated duration or the median of comparable contracts.
    then: the expected signing (median award-to-signing of comparable packages) and contract end after a forecast award.

Warnings: slower than 9 in 10 comparable tenders already; a notice re-issued; the expected contract end after the
project's closing date; a downgrade in the project's newest ISR (procintel.monitoring.isr_ratings). Every number says
how many comparable packages it rests on; fewer than MIN_N: no forecast ("not enough comparable packages").
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from procintel.monitoring import survival

MIN_N = 10
SIGNING_DEFAULT = None   # award-to-signing has its own history column (stages); used when given


def _comparable(history: pd.DataFrame, group: str, method: str | None, col: str, cond=None) -> tuple[pd.Series, str]:
    """Values of col for the narrowest comparable scope with at least MIN_N (after cond): group + method, then group."""
    for label, f in ((f"{group} via {method}", history[(history.proc_group == group) & (history.method_code == method)])
                     if method else (None, None), (f"all {group}", history[history.proc_group == group])):
        if f is None:
            continue
        s = f[col].dropna()
        if cond is not None:
            s = s[cond(s)]
        if len(s) >= MIN_N:
            return s, label
    return pd.Series(dtype=float), "not enough comparable packages"


def _survival(history: pd.DataFrame, group: str, method: str | None, age: int):
    """Kaplan-Meier over the narrowest comparable scope with at least MIN_N tenders still unawarded at `age`: awarded
    tenders as events, active ones in bidding as censored at their age (needs the status columns; None without)."""
    if "phase" not in history or "age_days" not in history:
        return None
    for label, f in (((f"{group} via {method}", history[(history.proc_group == group) & (history.method_code == method)]),)
                     if method else ()) + ((f"all {group}", history[history.proc_group == group]),):
        done = f.tender_to_award_days.dropna()
        open_ = pd.to_numeric(f[(f.phase == "bidding") & f.award_date.isna()].age_days, errors="coerce").dropna() \
            if "award_date" in f else pd.Series(dtype=float)
        d = np.concatenate([done.to_numpy(float), open_.to_numpy(float)])
        e = np.concatenate([np.ones(len(done), bool), np.zeros(len(open_), bool)])
        n_risk = survival.at_risk(d, age)
        if n_risk >= MIN_N and len(done):
            times, S = survival.curve(d, e)
            return times, S, n_risk, int((open_ > age).sum()), label
    return None


def _when(today: pd.Timestamp, days: float | None) -> str | None:
    return (today + pd.Timedelta(days=round(days))).date().isoformat() if days is not None else None


def forecast(facts: dict, history: pd.DataFrame, today: date | None = None, isr: dict | None = None) -> dict:
    """facts: proc_group, method_code, tender_start (date or None), award_date (None if not awarded), contract_duration_days,
    reissued (bool), closing_date. history: packages with tender_to_award_days and contract_duration_days (status.frame)."""
    today = pd.Timestamp(today or date.today())
    g, m = facts["proc_group"], facts.get("method_code")
    start = pd.Timestamp(facts["tender_start"]) if facts.get("tender_start") else None
    award = pd.Timestamp(facts["award_date"]) if facts.get("award_date") else None
    closing = pd.Timestamp(facts["closing_date"]) if facts.get("closing_date") else None
    out: dict = {"asOf": today.date().isoformat(), "stages": [], "warnings": [], "caveats": []}

    award_days = None
    if award is None:
        if start is None:
            out["caveats"].append("No tender date: the time already spent is unknown, so nothing is forecast.")
            return out
        age = (today - start).days
        all_awarded, scope_all = _comparable(history, g, m, "tender_to_award_days")
        longer, scope = _comparable(history, g, m, "tender_to_award_days", lambda s: s > age)
        out["stages"].append({"stage": "bidding", "start": start.date().isoformat(), "status": "in progress",
                              "elapsedDays": age})
        if len(all_awarded) and age > all_awarded.quantile(0.9):
            out["warnings"].append({"kind": "slow", "text": f"Open {age} days: slower already than 9 in 10 comparable "
                                    f"tenders ({scope_all}, n={len(all_awarded)}; 1 in 10 took over "
                                    f"{all_awarded.quantile(0.9):.0f} days)."})
        km = _survival(history, g, m, age)
        if km is not None:
            times, S, n_risk, n_open, kscope = km
            med = survival.remaining_quantile(times, S, age, 0.5)
            p90 = survival.remaining_quantile(times, S, age, 0.9)
            award_days = med
            out["award"] = {"medianDays": round(med) if med is not None else None,
                            "p90Days": round(p90) if p90 is not None else None,
                            "date": _when(today, med), "p90Date": _when(today, p90),
                            "within30": round(survival.within(times, S, age, 30), 2),
                            "within90": round(survival.within(times, S, age, 90), 2),
                            "basis": f"{n_risk} comparable tenders still unawarded after {age} days, {n_open} of them "
                                     f"still open today ({kscope}); survival estimate"}
            out["caveats"].append("Tenders still open count as waiting (censored), so they no longer pull the forecast "
                                  "early; tenders open past any normal time are left out, as many were awarded without a "
                                  "published notice." + ("" if p90 is not None else " Beyond the data for the slow case: "
                                                         "fewer than 1 in 10 of those tenders had been awarded."))
            if med is None:
                out["caveats"].append("Fewer than half of the comparable tenders open this long were awarded in the "
                                      "data: no median award date.")
        elif len(longer):   # no package statuses in the history: the earlier estimate from awarded tenders only
            rest = longer - age
            award_days = float(rest.median())
            out["award"] = {"medianDays": round(award_days), "p90Days": round(float(rest.quantile(0.9))),
                            "date": _when(today, award_days), "p90Date": _when(today, float(rest.quantile(0.9))),
                            "within30": round(float((rest <= 30).mean()), 2), "within90": round(float((rest <= 90).mean()), 2),
                            "basis": f"comparable packages still open after {age} days ({scope}, n={len(longer)})"}
            out["caveats"].append("The history holds only tenders with a recorded award; some that look open were "
                                  "awarded without a published notice, so the award forecast leans early.")
        else:
            out["award"] = None
            out["caveats"].append(f"Fewer than {MIN_N} comparable tenders were still open after {age} days: no award "
                                  "forecast. A tender this old may be awarded without a published award, or stale.")
        expected_award = today + pd.Timedelta(days=award_days) if award_days is not None else None
    else:
        expected_award = award
        out["stages"].append({"stage": "bidding", "start": start.date().isoformat() if start is not None else None,
                              "end": award.date().isoformat(), "status": "done"})

    if facts.get("reissued"):
        out["warnings"].append({"kind": "reissued", "text": "A notice for this package was re-issued: often changed "
                                "requirements, an extended deadline or a re-tender."})

    stated = facts.get("contract_duration_days")
    dur, dscope = (float(stated), "stated in the award notice") if stated else (None, None)
    if dur is None:
        s, dscope = _comparable(history, g, m, "contract_duration_days")
        dur = float(s.median()) if len(s) else None
        dscope = f"median of comparable contracts ({dscope}, n={len(s)})" if len(s) else None
    if expected_award is not None and dur is not None:
        end = expected_award + pd.Timedelta(days=dur)
        out["stages"].append({"stage": "contract", "start": expected_award.date().isoformat(), "end": end.date().isoformat(),
                              "status": "forecast" if award is None else ("in progress" if end > today else "done"),
                              "durationDays": round(dur), "basis": dscope})
        out["contractEnd"] = end.date().isoformat()
        if closing is not None and end > closing:
            out["warnings"].append({"kind": "after_closing", "text": f"The contract would end about {end.date()}, "
                                    f"after the project closes on {closing.date()}: it may not finish in time, or "
                                    "needs an extension."})
    elif award is None and dur is not None and closing is not None and today + pd.Timedelta(days=dur) > closing:
        # no award forecast (too old for the history): even an award today would end after closing
        out["warnings"].append({"kind": "after_closing", "text": f"Even if awarded today, a contract of about {dur:.0f} "
                                f"days would end after the project closes on {closing.date()}."})
    if isr and isr.get("downgrades"):
        out["warnings"].append({"kind": "isr_downgrade", "text": f"The newest ISR ({isr['date']}) downgraded: "
                                + "; ".join(isr["downgrades"]) + "."})
    return out
