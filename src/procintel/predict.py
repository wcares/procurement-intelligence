"""Tender-to-award prediction for a planned package: gradient-boosted trees trained from scratch on the `package` table.

Three models (scikit-learn HistGradientBoosting, categorical features handled natively):
  days_p50   typical tender-to-award days (quantile regression, q=0.5)
  days_p90   slow case (q=0.9)
  over_180   probability that award takes more than 180 days (classifier)

Features are only what the Assess form supplies before tendering: procurement group and method, region (from the
country), sector, the country's CPIA scores as of the tender year (never later ones), and contract value in USD
(log10). Value: in training, the award price converted at the award year's rate (procintel.fx; 80% of packages have
one); at prediction, the planner's estimate (optional). The award price stands in for an estimate the data does not
have, so value is a little more informative in training than it will be in use. With value, typical-days MAE 79.4 vs
82.0 without, >180 Brier 0.152 vs 0.156 (2026-10-25, 1,154 packages).

Censoring: only awarded tenders have a duration, so recent years look fast (median 258 days for 2019 tenders, 75 for
2025) because their slow tenders are not awarded yet. A tender-year feature learned that artefact and predicted about
70 days for Kenyan civil works where 37% of comparable packages took over 180. So the year is not a feature, and the
models train only on tenders with at least MIN_FOLLOWUP_DAYS before the data snapshot (latest notice date). Tenders
that never got an award are still missing; a survival model that uses them as censored rows is the proper fix.
Project age and project size were tried and dropped:
the form does not ask for them, and without them the CV was about as good (typical-days MAE 78.0 vs 77.3) and the
over-180 risk better (Brier 0.150 vs 0.158).

Evaluation is 5-fold cross-validation grouped by project (all packages of a project are in the same fold), against the
baseline the app already shows: the median / p90 / share over 180 days of the same group+method, else the group, else
all packages, computed on the training folds only. A model is used in /assess only where it beats that baseline.

    python -m procintel.predict      # evaluate, train on all data, save data/models/timeline.joblib
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import brier_score_loss, mean_absolute_error, mean_pinball_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

from procintel import db, paths
from procintel import fx
from procintel.stats import MIN_BENCH_N

ROOT = paths.ROOT
DB_PATH = paths.DB_PATH
MODEL_PATH = paths.MODEL_DIR / "timeline.joblib"
CPIA = ["transparency_corruption", "public_administration", "property_rights_rule_based_gov",
        "business_regulatory_env", "public_sector_mgmt_cluster", "ida_allocation_index"]
CATEGORICAL = ["proc_group", "method_code", "region", "sector"]
NUMERIC = [f"cpia_{c}" for c in CPIA] + ["log_value_usd"]
FEATURES = CATEGORICAL + NUMERIC
LONG_DAYS = 180
MIN_FOLLOWUP_DAYS = 540  # 18 months between tender and data snapshot before a tender is used for training
MIN_GAIN = 0.02  # a model replaces the baseline only if it cuts the baseline's error by at least 2%
SEED = 7

_FRAME = f"""
WITH pk AS (
  SELECT k.package_id, k.project_id, k.proc_group, k.method_code, k.tender_start, k.tender_to_award_days,
         k.price_currency, k.price_amount, year(k.award_date::DATE) AS award_year,
         p.country_code, p.sector, p.commitment_usd, p.board_approval, c.region
  FROM package k JOIN project p USING (project_id) LEFT JOIN country c USING (country_code)
  WHERE k.tender_to_award_days IS NOT NULL AND k.tender_start IS NOT NULL
    AND k.tender_start::DATE <= (SELECT max(notice_date)::DATE FROM notice_m) - INTERVAL {MIN_FOLLOWUP_DAYS} DAY
),
cp AS (  -- latest CPIA score per indicator at or before the tender year
  SELECT pk.package_id, x.indicator, arg_max(x.value, x.year) AS value
  FROM pk JOIN cpia x ON x.country_code = pk.country_code AND x.year <= year(pk.tender_start)
  GROUP BY ALL
)
SELECT pk.*, {", ".join(f"max(CASE WHEN cp.indicator = '{c}' THEN cp.value END) AS cpia_{c}" for c in CPIA)}
FROM pk LEFT JOIN cp USING (package_id)
GROUP BY ALL
"""


def load_frame(db_path: Path = DB_PATH) -> pd.DataFrame:
    con = db.connect(db_path, read_only=True)
    df = con.execute(_FRAME).fetch_df()
    table = fx.rates(con)
    con.close()
    # award price in USD at the award year's rate; at prediction time the planner's estimate takes its place
    df["value_usd"] = [fx.to_usd(a, c, y, table) for a, c, y in zip(df["price_amount"], df["price_currency"], df["award_year"])]
    return add_features(df)


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["tender_year"] = pd.to_datetime(df["tender_start"]).dt.year
    value = pd.to_numeric(df["value_usd"], errors="coerce") if "value_usd" in df else pd.Series(np.nan, index=df.index)
    df["log_value_usd"] = np.log10(value.where(value > 0))  # missing or non-positive -> NaN, which the trees handle
    for c in CATEGORICAL:
        df[c] = df[c].astype("category")
    return df


def _models() -> dict:
    # Conservative trees for ~1,200 rows. Chosen from three settings on the same grouped CV (300/100/150 iterations,
    # leaves 15/15/7, min leaf 20/20/50): this one was best or tied on every metric. Picking on the evaluation folds
    # flatters it slightly, which is one reason for the MIN_GAIN margin below.
    common = dict(categorical_features="from_dtype", max_iter=150, learning_rate=0.05, max_leaf_nodes=7,
                  min_samples_leaf=50, l2_regularization=5.0, random_state=SEED)
    return {
        "days_p50": HistGradientBoostingRegressor(loss="quantile", quantile=0.5, **common),
        "days_p90": HistGradientBoostingRegressor(loss="quantile", quantile=0.9, **common),
        "over_180": HistGradientBoostingClassifier(**common),
    }


def _baseline(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    """The app's current numbers for each test row, computed from the training rows only."""
    y = train["tender_to_award_days"]
    stats = lambda s: (s.median(), s.quantile(0.9), (s > LONG_DAYS).mean())  # noqa: E731
    by_gm = {k: stats(g) for k, g in y.groupby([train["proc_group"], train["method_code"]], observed=True) if len(g) >= MIN_BENCH_N}
    by_g = {k: stats(g) for k, g in y.groupby(train["proc_group"], observed=True) if len(g) >= MIN_BENCH_N}
    overall = stats(y)
    rows = [by_gm.get((g, m)) or by_g.get(g) or overall for g, m in zip(test["proc_group"], test["method_code"])]
    return pd.DataFrame(rows, columns=["p50", "p90", "p_long"], index=test.index)


def evaluate(df: pd.DataFrame, folds: int = 5) -> dict:
    """Project-grouped CV of the three models against the baseline. Returns per-metric (model, baseline)."""
    pred = pd.DataFrame(index=df.index, columns=["p50", "p90", "p_long"], dtype=float)
    base = pred.copy()
    y = df["tender_to_award_days"]
    for tr, te in GroupKFold(n_splits=folds).split(df, groups=df["project_id"]):
        train, test = df.iloc[tr], df.iloc[te]
        m = _models()
        m["days_p50"].fit(train[FEATURES], train["tender_to_award_days"])
        m["days_p90"].fit(train[FEATURES], train["tender_to_award_days"])
        m["over_180"].fit(train[FEATURES], train["tender_to_award_days"] > LONG_DAYS)
        pred.loc[test.index, "p50"] = m["days_p50"].predict(test[FEATURES])
        pred.loc[test.index, "p90"] = m["days_p90"].predict(test[FEATURES])
        pred.loc[test.index, "p_long"] = m["over_180"].predict_proba(test[FEATURES])[:, 1]
        base.loc[test.index] = _baseline(train, test)
    long = y > LONG_DAYS
    return {
        "n": len(df), "projects": df["project_id"].nunique(), "folds": folds,
        "days_p50_mae": (mean_absolute_error(y, pred["p50"]), mean_absolute_error(y, base["p50"])),
        "days_p90_pinball": (mean_pinball_loss(y, pred["p90"], alpha=0.9), mean_pinball_loss(y, base["p90"], alpha=0.9)),
        "days_p90_coverage": ((y <= pred["p90"]).mean(), (y <= base["p90"]).mean()),
        "over_180_brier": (brier_score_loss(long, pred["p_long"]), brier_score_loss(long, base["p_long"])),
        "over_180_auc": (roc_auc_score(long, pred["p_long"]), roc_auc_score(long, base["p_long"])),
    }


def beats_baseline(metrics: dict) -> dict[str, bool]:
    """Which models to use: at least MIN_GAIN lower error than the baseline on their main metric."""
    better = lambda k: metrics[k][0] < metrics[k][1] * (1 - MIN_GAIN)  # noqa: E731
    return {"days_p50": better("days_p50_mae"), "days_p90": better("days_p90_pinball"), "over_180": better("over_180_brier")}


def train(df: pd.DataFrame, metrics: dict) -> dict:
    m = _models()
    m["days_p50"].fit(df[FEATURES], df["tender_to_award_days"])
    m["days_p90"].fit(df[FEATURES], df["tender_to_award_days"])
    m["over_180"].fit(df[FEATURES], df["tender_to_award_days"] > LONG_DAYS)
    known = df.dropna(subset=["log_value_usd"])
    value_median = {"all": float(known["log_value_usd"].median())}
    value_median |= {g: float(v) for g, v in known.groupby("proc_group", observed=True)["log_value_usd"].median().items()}
    value_median |= {f"{g}/{mth}": float(v) for (g, mth), v in
                     known.groupby(["proc_group", "method_code"], observed=True)["log_value_usd"].median().items()}
    return {"models": m, "metrics": metrics, "use": beats_baseline(metrics), "features": FEATURES,
            "value_median": value_median,
            "categories": {c: list(df[c].cat.categories) for c in CATEGORICAL},
            "n": len(df), "trained_at": datetime.now(timezone.utc).isoformat(),
            # so packages labelled later can test it out of sample (procintel.jobs drift check)
            "trained_ids": sorted(df["package_id"].astype(str)) if "package_id" in df else []}


def load(path: Path = MODEL_PATH) -> dict | None:
    return joblib.load(path) if path.exists() else None


def predict_one(bundle: dict, row: dict) -> dict:
    """Predictions for one planned package; row holds the raw columns of load_frame (proc_group, method_code, ...)."""
    df = add_features(pd.DataFrame([row]))
    if pd.isna(df.loc[0, "log_value_usd"]) and "value_median" in bundle:
        # no estimate: use the typical value of this group/method. Training rows without a price were mostly small
        # packages, so leaving it missing would read as "small contract" and make the prediction optimistic.
        vm = bundle["value_median"]
        df.loc[0, "log_value_usd"] = vm.get(f"{row['proc_group']}/{row['method_code']}", vm.get(row["proc_group"], vm["all"]))
    for c in CATEGORICAL:  # same category codes as in training, else the trees read the wrong categories
        known = bundle["categories"][c]
        values = [v if v in known else None for v in df[c].astype(object)]  # unseen -> missing (pandas will refuse it)
        df[c] = pd.Categorical(values, categories=known)
    for c in FEATURES:
        if c not in df:
            df[c] = np.nan
    X = df[bundle["features"]]
    m = bundle["models"]
    return {"p50": float(m["days_p50"].predict(X)[0]), "p90": float(m["days_p90"].predict(X)[0]),
            "p_long": float(m["over_180"].predict_proba(X)[0, 1])}


def main() -> None:
    retrain()


def retrain(db_path: Path = DB_PATH, path: Path = MODEL_PATH) -> dict:
    """Cross-validate, train on all labelled packages and save; returns the metrics."""
    df = load_frame(db_path)
    metrics = evaluate(df)
    use = beats_baseline(metrics)
    print(f"{metrics['n']} packages, {metrics['projects']} projects, {metrics['folds']}-fold CV grouped by project")
    print(f"{'metric':22s} {'model':>9s} {'baseline':>9s}")
    for k in ["days_p50_mae", "days_p90_pinball", "days_p90_coverage", "over_180_brier", "over_180_auc"]:
        mv, bv = metrics[k]
        print(f"{k:22s} {mv:9.3f} {bv:9.3f}")
    print("use model for:", {k: v for k, v in use.items()})
    bundle = train(df, metrics)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path)
    print(f"saved {path}")
    return metrics


if __name__ == "__main__":
    main()
