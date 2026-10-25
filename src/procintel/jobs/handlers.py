"""Job kinds. Each is a generator: it yields a cursor (a JSON-able dict) after every step, which the worker saves and
which is passed back in to resume after a pause or restart; its return value is the job's result.

    drift_check   the timeline model on packages that became labelled after it was trained (true out-of-sample
                  data) and how many there are; queues a retrain when they are numerous or the model does worse on
                  them than in cross-validation
    retrain       cross-validate, train, save, then ask the backend to load the new model
    refresh       re-fetch the World Bank sources and rebuild what changed (procintel.refresh), then reload the backend
    feedback_review  rebuild the review list and the demoted citations from user feedback (procintel.feedback_review);
                  reload the backend when the demoted set changed
"""
from __future__ import annotations

from typing import Any, Callable, Iterator

from procintel import predict
from procintel.jobs import store

MIN_NEW = 20          # fewer new packages than this: too few to judge the model on
GROWTH = 0.05         # new packages >= 5% of the training set: retrain to use them
ERROR_RATIO = 1.2     # error on new packages > 1.2x the cross-validated error: the model has drifted

Handler = Callable[[dict, dict | None, dict], Iterator[dict]]
REGISTRY: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(f: Handler) -> Handler:
        REGISTRY[kind] = f
        return f
    return register


def drift_decision(n_trained: int, n_new: int, mae_new: float | None, mae_cv: float) -> tuple[bool, str]:
    """(retrain?, why)."""
    if n_new >= max(MIN_NEW, GROWTH * n_trained):
        return True, f"{n_new} packages labelled since training ({n_new / n_trained:.0%} of {n_trained})"
    if mae_new is not None and n_new >= MIN_NEW and mae_new > ERROR_RATIO * mae_cv:
        return True, f"error on {n_new} new packages {mae_new:.0f} days vs {mae_cv:.0f} in cross-validation"
    return False, (f"{n_new} new packages; " + (f"error {mae_new:.0f} days vs {mae_cv:.0f} in cross-validation"
                                                 if mae_new is not None else "too few to measure the error"))


@handler("drift_check")
def drift_check(params: dict, cursor: dict | None, ctx: dict) -> Iterator[dict]:
    bundle = predict.load()
    if bundle is None or "trained_ids" not in bundle:
        jid = store.enqueue("retrain", "drift check: the saved model does not record its training packages",
                            db_path=ctx.get("jobs_db"))
        yield {"step": "checked"}
        return {"retrain": True, "why": "model has no record of its training packages", "queued": jid}
    df = predict.load_frame(ctx.get("db_path", predict.DB_PATH))
    new = df[~df["package_id"].astype(str).isin(set(bundle["trained_ids"]))]
    mae_new = None
    if len(new) >= MIN_NEW:
        p50 = [predict.predict_one(bundle, row)["p50"] for row in new.to_dict("records")]
        mae_new = float(sum(abs(a - b) for a, b in zip(p50, new["tender_to_award_days"])) / len(new))
    yield {"step": "measured"}
    mae_cv = bundle["metrics"]["days_p50_mae"][0]
    retrain, why = drift_decision(bundle["n"], len(new), mae_new, mae_cv)
    jid = store.enqueue("retrain", f"drift check: {why}", db_path=ctx.get("jobs_db")) if retrain else None
    return {"retrain": retrain, "why": why, "new_packages": len(new), "mae_new": mae_new, "mae_cv": mae_cv,
            "queued": jid}


@handler("retrain")
def retrain(params: dict, cursor: dict | None, ctx: dict) -> Iterator[dict]:
    metrics = predict.retrain(ctx.get("db_path", predict.DB_PATH))
    yield {"step": "trained"}
    reload: Callable[[], Any] | None = ctx.get("reload")
    if reload:
        reload()
    return {"n": metrics["n"], "days_p50_mae": metrics["days_p50_mae"], "reloaded": bool(reload)}


@handler("refresh")
def refresh(params: dict, cursor: dict | None, ctx: dict) -> Iterator[dict]:
    from procintel import refresh as refresh_mod  # imported here: it pulls in every pipeline module
    try:
        changes = refresh_mod.run(fetch=params.get("fetch", True), db_path=ctx.get("db_path", predict.DB_PATH))
    except SystemExit as e:  # refresh signals failure with SystemExit, which must not end the worker thread
        raise RuntimeError("refresh failed; see table refresh_log") from e
    yield {"step": "refreshed"}
    reload: Callable[[], Any] | None = ctx.get("reload")
    if reload:
        reload()
    return {"changes": {k: v for k, v in changes.items() if not isinstance(v, (dict, list))}, "reloaded": bool(reload)}


@handler("feedback_review")
def feedback_review(params: dict, cursor: dict | None, ctx: dict) -> Iterator[dict]:
    from procintel import feedback_review as fr
    before = fr.load_demoted(ctx.get("feedback_db"))
    out = fr.build(ctx.get("feedback_db"))
    yield {"step": "built"}
    changed = set(out["demoted"]) != before
    reload: Callable[[], Any] | None = ctx.get("reload")
    if changed and reload:
        reload()
    return {"items": out["items"], "demoted": len(out["demoted"]), "reloaded": bool(changed and reload)}
