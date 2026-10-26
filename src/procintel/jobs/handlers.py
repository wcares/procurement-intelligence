"""Job kinds. Each is a generator: it yields a cursor (a JSON-able dict) after every step, which the worker saves and
which is passed back in to resume after a pause or restart; its return value is the job's result.

    drift_check   the timeline model on packages that became labelled after it was trained (true out-of-sample
                  data) and how many there are; queues a retrain when they are numerous or the model does worse on
                  them than in cross-validation
    retrain       cross-validate, train, save, then ask the backend to load the new model
    refresh       re-fetch the World Bank sources and rebuild what changed (procintel.ingestion.refresh), then reload the backend
    feedback_review  rebuild the review list and the demoted citations from user feedback (procintel.learning.feedback_review);
                  reload the backend when the demoted set changed
    shadow_build     build an alternative index next to the live one (procintel.learning.shadows), then queue its
                  evaluation; background priority, resumable step by step
    shadow_evaluate  compare live and shadow search quality on the evaluation questions; background
    shadow_promote   swap a shadow in (high priority), sync the vector store, queue index_followup, reload
    index_followup   tag passages that have no tags yet (after a promotion); background
    prompt_evaluate  answer a question sample with the active and a candidate prompt version
                  (procintel.learning.prompt_eval); background, one question per step
    detect_changes   read each due source, record what changed, queue a pipeline_batch for it (procintel.pipeline)
    pipeline_batch   run the actions the rules ask for, one per step, then reload
    retention        delete what is past its retention (procintel.jobs.retention); background, queued daily
    evaluate         the evaluation set (procintel.learning.evaluate): judge passages of new questions, then search
                  quality, and with answers=True the answers too (about 10 minutes); appends to eval/history.jsonl;
                  background
"""
from __future__ import annotations

from typing import Any, Callable, Iterator

from procintel.jobs import store
from procintel.prediction import predict

MIN_NEW = 20          # fewer new packages than this: too few to judge the model on
GROWTH = 0.05         # new packages >= 5% of the training set: retrain to use them
ERROR_RATIO = 1.2     # error on new packages > 1.2x the cross-validated error: the model has drifted

Handler = Callable[[dict, dict | None, dict], Iterator[dict]]
REGISTRY: dict[str, Handler] = {}


def handler(kind: str, priority: str = "normal") -> Callable[[Handler], Handler]:
    """Register a job kind with its default priority (high, normal or background)."""
    store.priority_of(kind, priority)  # rejects an unknown priority name
    def register(f: Handler) -> Handler:
        REGISTRY[kind] = f
        store.DEFAULT_PRIORITY[kind] = priority
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
    from procintel.ingestion import refresh as refresh_mod  # imported here: it pulls in every pipeline module
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
    from procintel.learning import feedback_review as fr
    before = fr.load_demoted(ctx.get("feedback_db"))
    out = fr.build(ctx.get("feedback_db"))
    yield {"step": "built"}
    changed = set(out["demoted"]) != before
    reload: Callable[[], Any] | None = ctx.get("reload")
    if changed and reload:
        reload()
    return {"items": out["items"], "demoted": len(out["demoted"]), "reloaded": bool(changed and reload)}


@handler("shadow_build", priority="background")
def shadow_build(params: dict, cursor: dict | None, ctx: dict) -> Iterator[dict]:
    from procintel.learning import shadows
    name = params["name"]
    yield from shadows.SHADOWS[name].build(cursor)
    jid = store.enqueue("shadow_evaluate", f"shadow {name} built", {"name": name}, db_path=ctx.get("jobs_db"))
    return {"built": name, "evaluation_job": jid}


@handler("shadow_evaluate", priority="background")
def shadow_evaluate(params: dict, cursor: dict | None, ctx: dict) -> Iterator[dict]:
    from procintel.learning import shadows
    out = shadows.evaluate_shadow(params["name"])
    yield {"step": "evaluated"}
    return out


@handler("shadow_promote", priority="high")
def shadow_promote(params: dict, cursor: dict | None, ctx: dict) -> Iterator[dict]:
    from procintel.core import vector_index
    from procintel.learning import shadows
    shadows.promote(params["name"])
    yield {"step": "promoted"}
    if vector_index.backend() == "qdrant":
        vector_index.sync("chunks")
        yield {"step": "vectors synced"}
    jid = store.enqueue("index_followup", f"shadow {params['name']} promoted", db_path=ctx.get("jobs_db"))
    reload: Callable[[], Any] | None = ctx.get("reload")
    if reload:
        reload()
    return {"promoted": params["name"], "followup_job": jid, "reloaded": bool(reload)}


@handler("index_followup", priority="background")
def index_followup(params: dict, cursor: dict | None, ctx: dict) -> Iterator[dict]:
    from procintel.core import decide, llm
    from procintel.ingestion import problem_tag, tag
    tagged = tag.build() if decide.available() else 0
    yield {"step": "tagged"}
    problems = problem_tag.build() if decide.available() and llm.available() else 0
    reload: Callable[[], Any] | None = ctx.get("reload")
    if reload:
        reload()
    return {"tagged": tagged, "problems_tagged": problems, "reloaded": bool(reload)}


@handler("prompt_evaluate", priority="background")
def prompt_evaluate(params: dict, cursor: dict | None, ctx: dict) -> Iterator[dict]:
    from procintel.learning import prompt_eval
    return (yield from prompt_eval.steps(params["name"], params["version"], cursor))


@handler("detect_changes")
def detect_changes(params: dict, cursor: dict | None, ctx: dict) -> Iterator[dict]:
    from procintel.pipeline import detect
    return (yield from detect.detect_steps(params, cursor, ctx))


@handler("pipeline_batch")
def pipeline_batch(params: dict, cursor: dict | None, ctx: dict) -> Iterator[dict]:
    from procintel.pipeline import detect
    return (yield from detect.batch_steps(params, cursor, ctx))


@handler("retention", priority="background")
def retention(params: dict, cursor: dict | None, ctx: dict) -> Iterator[dict]:
    from procintel.jobs import retention as r
    out = r.apply(dry=bool(params.get("dry")))
    yield {"step": "applied"}
    return out


@handler("evaluate", priority="background")
def evaluate_run(params: dict, cursor: dict | None, ctx: dict) -> Iterator[dict]:
    from procintel.answering.retrieve import Retriever
    from procintel.core import llm
    from procintel.learning import evaluate
    r = Retriever()
    if llm.available():   # questions added since the last run get their passages judged first
        evaluate.judge(r)
        yield {"step": "judged"}
    headline = evaluate.report(r, answers=bool(params.get("answers", True)))
    yield {"step": "evaluated"}
    return {k: headline.get(k) for k in ("time", "hybrid_p5", "hybrid_r10", "gate_prec", "answered", "refused_traps")}
