"""Tender stages for the Assess timeline (docs/ui-design.md section 2.1): how long each stage typically takes for
comparable packages, and on which stage each risk bites.

Only stages the data can time get a duration: bids and evaluation (first advert to award), award to contract signing
(award notice to the contract's signing date, Finances One contracts matched by bid reference) and the contract itself
(its stated duration). Planning and document preparation have no dates in the data and are shown without one; so is
prequalification (10 notices, none paired with a later stage). Groups follow the award-time benchmark: the package's
procurement type and method, else its type, else all packages, whichever first has MIN_BENCH_N values.
"""
from __future__ import annotations

import duckdb

from procintel.prediction.stats import MIN_BENCH_N, PROC_GROUP_LABELS

STAGES = [  # (key, label, column timed or None)
    ("plan", "Plan and prepare documents", None),
    ("bidding", "Advertise, bids and evaluation", "tender_to_award_days"),
    ("signing", "Award to contract signing", "signing_days"),
    ("contract", "Contract to completion", "contract_duration_days"),
]

# risk flag id -> stage it bites on ("all": across the timeline)
RISK_STAGE = {"long-cycle": "bidding", "spread": "bidding", "model-timeline": "bidding", "model-long": "bidding",
              "rebid": "bidding", "amendment": "contract", "governance": "all", "governance-wgi": "all"}
# problem kind of a precedent passage (procintel.ingestion.problem_tag) -> stage
PROBLEM_STAGE = {"weak specifications or design": "plan", "re-tendering or contract termination": "bidding",
                 "land acquisition or resettlement": "contract", "funding or payment delays": "contract",
                 "contractor performance or capacity": "contract",
                 "external shock such as a pandemic, disaster or conflict": "all"}

_FRAME = """
    SELECT k.proc_group, k.method_code, k.tender_to_award_days, k.contract_duration_days,
           CASE WHEN k.award_date IS NOT NULL AND NOT coalesce(k.award_from_contract, false) AND s.signing_date >= k.award_date::DATE
                THEN date_diff('day', k.award_date::DATE, s.signing_date) END AS signing_days
    FROM package k
    LEFT JOIN (SELECT a.project_id, upper(regexp_replace(a.contract_ref, '\\s', '', 'g')) AS ref, min(a.signing_date) AS signing_date
               FROM contract_award a GROUP BY 1, 2) s
      ON s.project_id = k.project_id AND s.ref = upper(regexp_replace(split_part(k.package_id, '/', 2), '\\s', '', 'g'))"""


def build(con: duckdb.DuckDBPyConnection) -> dict:
    """{scope key ("all", "<group>", "<group>/<method>"): {stage: {median, p90, n}}} for the timed stages."""
    if con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'contract_award'").fetchone():
        df = con.execute(_FRAME).df()
    else:  # no contract data: the signing stage stays without a duration
        df = con.execute("SELECT proc_group, method_code, tender_to_award_days, contract_duration_days, "
                         "NULL::INTEGER AS signing_days FROM package").df()
    out: dict = {}
    keys = [("all", df)] + [(g, f) for g, f in df.groupby("proc_group")] + \
        [(f"{g}/{m}", f) for (g, m), f in df.groupby(["proc_group", "method_code"])]
    for key, f in keys:
        stats = {}
        for stage, _, col in STAGES:
            if col and col in f:
                v = f[col].dropna()
                v = v[v >= 0]
                if len(v) >= MIN_BENCH_N:
                    stats[stage] = {"median": round(float(v.median()), 1), "p90": round(float(v.quantile(0.9)), 1),
                                    "n": int(v.size)}
        out[key] = stats
    return out


def for_package(stats: dict, group: str, method: str) -> list[dict]:
    """The stages in order, each with the narrowest comparable group that has enough values (or no duration)."""
    label = PROC_GROUP_LABELS.get(group, group)
    scopes = ((f"{group}/{method}", f"{label} via {method}"), (group, f"all {label} packages"), ("all", "all packages"))
    out = []
    for key, name, col in STAGES:
        row = {"key": key, "label": name, "median": None, "p90": None, "n": 0, "scope": None}
        for scope_key, scope in scopes if col else ():
            s = stats.get(scope_key, {}).get(key)
            if s:
                row |= s | {"scope": scope}
                break
        out.append(row)
    return out


def stage_of_problem(kind: str | None) -> str | None:
    return PROBLEM_STAGE.get(kind) if kind else None


def place_risks(risks: list[dict]) -> list[dict]:
    """Each risk flag gets the stage it bites on (unknown flags: across the timeline)."""
    for r in risks:
        r["stage"] = RISK_STAGE.get(r["id"], "all")
    return risks
