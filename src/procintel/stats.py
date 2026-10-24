"""Historical statistics shared by the live API and the mock-fixture export: dropdown options,
tender-to-award benchmarks per procurement group / method, and latest CPIA scores per country."""
from __future__ import annotations

import re

import duckdb

PROC_GROUP_LABELS = {"GO": "Goods", "CW": "Civil Works", "CS": "Consulting Services", "NC": "Non-Consulting Services"}
PROC_TERMS = re.compile(
    r"\b(procurement|tender|re-?tender|bid(?:ding|der|s)?|contract(?:or|s)?|award(?:ed)?|supplier|consultant|"
    r"specification|terms of reference|cancel(?:led|lation)?|delay(?:s|ed)?)\b", re.I)
GROUP_TERMS = {
    "CW": re.compile(r"\b(works?|construction|contractor|civil|rehabilitation|road)\b", re.I),
    "GO": re.compile(r"\b(goods|equipment|supply|supplies|vehicles?|medicines?)\b", re.I),
    "CS": re.compile(r"\b(consultan(?:t|cy|cies)|firm|terms of reference|technical assistance|study)\b", re.I),
    "NC": re.compile(r"\b(services?|maintenance|logistics|training)\b", re.I),
}
MIN_BENCH_N = 10


def options(con: duckdb.DuckDBPyConnection) -> dict:
    q = lambda s, *a: con.execute(s, *a).fetchall()  # noqa: E731
    countries = [{"code": c, "name": n, "region": r} for c, n, r in
                 q("SELECT country_code, name, region FROM country ORDER BY name")]
    sectors = [s for (s,) in q("SELECT DISTINCT sector FROM project WHERE sector IS NOT NULL AND sector <> '' ORDER BY 1")]
    labels = dict(q("SELECT method_code, mode(method_name) FROM notice_m WHERE method_code IS NOT NULL GROUP BY 1"))
    methods = [{"code": m, "label": labels.get(m) or m, "procGroups": gs, "n": n} for m, gs, n in q("""
        SELECT method_code, list(DISTINCT proc_group ORDER BY proc_group), COUNT(*)
        FROM package WHERE method_code IS NOT NULL AND proc_group IS NOT NULL
        GROUP BY 1 HAVING COUNT(*) >= 10 ORDER BY 3 DESC""")]
    return {
        "countries": countries,
        "sectors": sectors,
        "procGroups": [{"code": k, "label": v} for k, v in PROC_GROUP_LABELS.items()],
        "methods": methods,
    }


def benchmarks(con: duckdb.DuckDBPyConnection) -> dict[str, dict | None]:
    """Keys: "all", "<group>", "<group>/<method>" (the last only when n >= MIN_BENCH_N)."""
    q = lambda s, *a: con.execute(s, *a).fetchall()  # noqa: E731

    def bench(where: str, params: list) -> dict | None:
        r = q(f"""SELECT COUNT(*), median(tender_to_award_days), quantile_cont(tender_to_award_days, .25),
                         quantile_cont(tender_to_award_days, .75), quantile_cont(tender_to_award_days, .9),
                         AVG(CASE WHEN tender_to_award_days > 180 THEN 1 ELSE 0 END)
                  FROM package WHERE tender_to_award_days IS NOT NULL {where}""", params)[0]
        if r[0] == 0:
            return None
        return {"n": r[0], "median": r[1], "p25": r[2], "p75": r[3], "p90": r[4], "shareOver180": r[5]}

    out: dict[str, dict | None] = {"all": bench("", [])}
    for (g,) in q("SELECT DISTINCT proc_group FROM package WHERE proc_group IS NOT NULL"):
        out[g] = bench("AND proc_group = ?", [g])
    for (g, m) in q("SELECT DISTINCT proc_group, method_code FROM package WHERE proc_group IS NOT NULL AND method_code IS NOT NULL"):
        b = bench("AND proc_group = ? AND method_code = ?", [g, m])
        if b and b["n"] >= MIN_BENCH_N:
            out[f"{g}/{m}"] = b
    return out


def governance(con: duckdb.DuckDBPyConnection) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for cc, ind, yr, val in con.execute("""SELECT country_code, indicator, year, value FROM cpia
            QUALIFY row_number() OVER (PARTITION BY country_code, indicator ORDER BY year DESC) = 1""").fetchall():
        out.setdefault(cc, []).append({"indicator": ind, "year": yr, "value": val})
    return out
