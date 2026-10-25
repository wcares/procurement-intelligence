# Pilot rollout plan and KPIs

How the prototype would be piloted with procurement staff, what is measured at each stage, how each measure is
computed, and what has to be built before the pilot can measure it. Baselines are today's measured values
(2026-10-25); targets are proposals to agree with the pilot sponsor, not commitments.

## Phases

| phase | who and what | length | go to the next phase when |
|---|---|---|---|
| 0. Pre-pilot build | the gaps in "Needed before the pilot" below | 2–3 weeks | user ids, package references and response times are logged; the KPI script reports them on test data |
| 1. Shadow | 5–10 procurement specialists ask questions and assess packages they are already planning; nothing they produce depends on the tool | 4–6 weeks | ≥ 150 rated responses; useful share ≥ 60%; flagged-citation rate ≤ 5%; no severe faithfulness incident (an unsupported claim acted on) |
| 2. Assisted planning | planners in one region use Assess when drafting procurement plans for one quarter | 1 quarter | predicted vs actual award time measured on ≥ 30 packages that reached award; planners keep using it (weekly active ≥ 50% of the group) |
| 3. Wider rollout | more regions; scheduled refresh; feedback-driven evaluation updates | ongoing | — |

Stopping rule in any phase: a faithfulness incident, or the useful share falling below 40% for two weeks in a row,
pauses the phase until the cause is found and fixed.

## KPIs

| KPI | definition | computed from | baseline today | proposed pilot target |
|---|---|---|---|---|
| Retrieval precision | share of the top 5 hybrid-search passages judged relevant, averaged over the evaluation questions | `evaluate run` (eval/report.md) | 0.70 (100 questions) | ≥ 0.70, no drop after a refresh |
| Retrieval recall | share of the pooled relevant passages found in the top 10 | `evaluate run` | 0.78 | ≥ 0.75 |
| Answer faithfulness | answer sentences the independent judge finds supported by their citations | `evaluate run` | 282/285 (98.9%) | ≥ 97% |
| Refusal on unanswerable questions | traps and off-topic questions refused | `evaluate run` | 20/20 | 100% |
| Answer coverage | answerable evaluation questions answered | `evaluate run` | 77/80 (79/80 after the 2026-10-25 fix, checked directly) | ≥ 95% |
| Useful share | ratings "useful" / (useful + not useful) on real responses | `python -m procintel.learning.kpi` (feedback log) | no real ratings yet | ≥ 60% in shadow, ≥ 70% assisted |
| Flagged citations | citations users mark as wrong, per 100 responses | `kpi` | no real use yet | ≤ 5 |
| Refusal rate on real questions | Ask responses with no supported answer | `kpi` | 2 of 5 test questions (test traffic, not a baseline) | tracked, read with a sample of refused questions |
| Rating rate | responses that receive any rating | `kpi` | 0% (test traffic) | ≥ 30% (below that the useful share is not trusted) |
| Award-time error | mean absolute error, predicted vs actual tender-to-award days, on pilot packages that reached award | `kpi` (Assess logs the tender reference and its prediction; matched when the tender has an award time) | 79 days in cross-validation (median baseline 85) | below the median baseline on pilot packages |
| Weekly active users | distinct users with ≥ 1 response in the week | `kpi` (pseudonymous user ids) | — | ≥ 50% of the pilot group |
| Response time | median seconds per Ask / Assess response | `kpi` (time per response in the log) | 34 s per question (evaluation, Saluki) | ≤ 40 s; report the share over 60 s |
| Planning cycle time | days from a procurement plan's first draft to its approval, pilot quarter vs the previous quarter | the planners' own system (STEP or plan records) | not available here | shorter, with the confound noted (one quarter, one region) |

Quality KPIs are measured on a fixed question set so changes are comparable; usage KPIs on real traffic. Real
questions that were refused or rated "not useful" are reviewed every two weeks, and the ones with a known answer in
the reports are added to the evaluation set, so the fixed set keeps up with what users ask.

## Needed before the pilot

**Built (2026-10-25):** all four, below; the deletion after 30 days (retention job) is the remaining item and must run
before the pilot starts.

1. **Pseudonymous user id** in each logged response (from the sign-in in front of the app), for active users and
   per-user rating patterns. No names in the logs.
2. **Package reference in Assess** (an optional bid reference field), so a prediction can be matched to the tender
   when its award notice is published; a weekly job then computes the award-time error.
3. **Response time** in the response log.
4. **Data handling note** for participants: what is logged (questions, responses, ratings), retention, and that the
   models run locally with no data sent to outside services. (The web app's /data-handling page, readable without
   signing in and linked from the sign-in page and the footer.)

## Risks

- *Small samples*: a shadow phase with 5–10 users gives a few hundred ratings; differences of a few points are noise.
  Report counts with every share.
- *Raters are not random*: people rate what surprises them. The rating rate is tracked for this reason.
- *Award-time feedback is slow*: the median tender-to-award time is 108 days, so the prediction KPI matures
  late in phase 2.
- *Data gaps*: only about 1 in 6 tendered packages (1,178 of 6,990) has a known tender-to-award time, so predictions
  rest on a selected sample (see docs/TRACKER.md, survival model).
