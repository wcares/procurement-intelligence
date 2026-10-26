"""Kaplan-Meier survival for the time from tender to award, with tenders still open counted as censored (waiting at
least their age so far) instead of being left out, which made the award forecast lean early. The still-open signal is
the package status (procintel.monitoring.status): active packages in bidding are censored; stale ones (open past any
normal time, outcome unknown) stay out, since many are awarded without a published notice.

    curve(durations, observed)       -> (times, S): S[i] = P(still unawarded after times[i])
    after(times, S, age)             -> the curve given that the tender is still open at `age`
"""
from __future__ import annotations

import numpy as np


def curve(durations, observed) -> tuple[np.ndarray, np.ndarray]:
    d = np.asarray(durations, dtype=float)
    e = np.asarray(observed, dtype=bool)
    times = np.unique(d[e])
    s, out = 1.0, []
    for t in times:
        at_risk = (d >= t).sum()
        events = ((d == t) & e).sum()
        s *= 1 - events / at_risk
        out.append(s)
    return times, np.asarray(out)


def survival_at(times: np.ndarray, S: np.ndarray, t: float) -> float:
    i = np.searchsorted(times, t, side="right") - 1
    return 1.0 if i < 0 else float(S[i])


def remaining_quantile(times: np.ndarray, S: np.ndarray, age: float, q: float) -> float | None:
    """Days after `age` by which a share q of the tenders still open at `age` were awarded; None beyond the data."""
    s_age = survival_at(times, S, age)
    if s_age <= 0:
        return None
    later = times > age
    hit = np.nonzero(later & (S / s_age <= 1 - q + 1e-12))[0]
    return float(times[hit[0]] - age) if len(hit) else None


def within(times: np.ndarray, S: np.ndarray, age: float, days: float) -> float | None:
    s_age = survival_at(times, S, age)
    return None if s_age <= 0 else 1 - survival_at(times, S, age + days) / s_age


def at_risk(durations, age: float) -> int:
    return int((np.asarray(durations, dtype=float) > age).sum())
