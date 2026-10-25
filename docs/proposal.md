# Procurement Intelligence Platform: technical proposal (MVP write-up)

This answers the four modules of `assessment.md` §4. Each module says what the working prototype does, the design
choices behind it, the measured evidence, and what is not done yet. Every figure comes from a run recorded in a commit,
in `eval/report.md`, or in `docs/TRACKER.md`; the tracker also holds the ordered list of next steps.

Scope of the prototype: 120 Implementation Completion and Results Reports (ICRs), the 121 projects they cover, 10,370
procurement notices and 5,598 CPIA scores for 72 countries, all from World Bank public APIs, stored in DuckDB and
served by a FastAPI backend to a Next.js web app. All models run locally through llama.cpp and are swappable by
configuration.

---

## Module 1: Ingestion and knowledge representation

**What it does.** One pipeline (`ingest → model → chunk → embed → tag`) turns three kinds of source into one
relational model joined on `project_id`:

| source | form | becomes |
|---|---|---|
| Projects API | JSON records | `project` (121 rows), with country, sector, instrument, dates |
| Procurement notices API | JSON + HTML notice text | `notice_m` (10,370), `package` (7,002 tenders keyed `project/bid_ref`, with tender-to-award days), `supplier` (4,702), `award_supplier` (5,913) |
| Documents API (WDS) | ICR plain-text exports, 100+ pages | `document_m` (120), `chunk` (18,992 citable passages), `chunk_vec` (vectors), `chunk_tag` (labels), `rating_check` (ICR vs ISR) |
| Indicators API | CPIA series | `cpia` (5,598 country-year-indicator rows) |

The entity-relationship diagram, grain of every table and measured gaps are in `docs/data-model.md`.

**Design choices.**

- *Linking on stable keys first.* A contract row, its tender, its project and the ICR that evaluates that project all
  share `project_id`; ICRs covering several projects are split into `document_project`. This is exact, which matters
  for citations. Sector and time are carried as attributes for filtering, not used as fuzzy join keys yet.
- *A report-aware chunker instead of generic splitting.* ICRs number their paragraphs, so chunks follow numbered
  paragraphs and keep `section` and `¶` as the citation anchor. Running headers, footers, page numbers and footnote
  blocks are removed first: before that fix 1,360 of 19,169 chunks (7%) contained page furniture; after it, none, while
  keeping 99.8% of the real words (every removed line audited). Text without sentence breaks is capped at 1,400
  characters so it fits an embedding window (107 chunks were over).
- *Embeddings:* EmbeddingGemma 2 with its retrieval prompts, truncated to 256 of 768 dimensions (trained for it),
  stored with the model name and a text hash so a rebuild only embeds new or changed passages (18,992 in 326 s; a
  re-run embeds none).
- *Labels from a decision model:* every passage gets a problem-type tag from Laya, a small model that returns
  calibrated probabilities instead of text (18,140 passages in 653 s).

**Not done yet.** Supplier entity resolution (225 duplicate normalised names are not merged); links by sector and time
proximity; tables are flattened in the text exports (page-image indexing with the multimodal embedding model is the
candidate fix); two sources were unavailable (Major Contract Awards returns HTML, the WGI code was not found).

## Module 2: Predictive and prescriptive engines

**Timeline and risk prediction.** Gradient-boosted trees (scikit-learn HistGradientBoosting, trained from scratch)
predict tender-to-award days (median and 90th percentile, quantile loss) and the probability of exceeding 180 days.
Inputs are what a planner knows before tendering: procurement group and method, region, sector and the country's CPIA
scores as of the tender year.

| metric (5-fold CV grouped by project, 1,145 packages) | model | baseline the app showed before |
|---|---|---|
| typical days, mean absolute error | 74.4 | 81.2 (median of comparable packages) |
| 90th percentile, pinball loss | 25.2 | 26.0 |
| > 180 days, Brier score | 0.147 | 0.167 |
| > 180 days, AUC | 0.81 | 0.74 |

A model is shown only where it beats the baseline by at least 2%, labelled "model" next to the historical statistic.
One finding shaped the design: only awarded tenders have a duration, so recent years look fast (median 258 days for
2019 tenders, 75 for 2025). A first version that used the tender year learned this artefact and predicted 70 days for
Kenyan civil works where 37% of comparable packages took over 180. The year was removed and training requires 18
months of follow-up. The proper fix, a survival model that counts never-awarded tenders as censored, is the next step;
amendment and re-bidding probabilities follow it.

**Retrieval of precedents and lessons.** BM25 (LlamaIndex) and vector search run over the same filtered passages and
are merged by reciprocal rank fusion. On the evaluation set, hybrid precision@5 is 0.77 against 0.64 for BM25, and
pooled recall@10 0.76 against 0.62. Assess shows quoted lessons from comparable projects; passages the tagger is
confident describe no problem (indicator tables, staffing lists) are filtered out. Answers are written by a local
27B model (Underdog-Saluki, Qwen3.8 fine-tune) from at most five passages, in 13–30 s.

**Not done yet.** Retrieval is single-pass, not the multi-step ("agentic") loop the brief describes; similar past
specifications are not matched yet; precedents can still include tables for countries with one ICR.

## Module 3: Guardrails, faithfulness and attribution

**Layers, in order.**

1. *Citation by construction:* every answer sentence carries the passage numbers it rests on; the UI shows each
   passage with project, section, paragraph and a link to the source PDF, and highlights the quoted sentence.
2. *Evidence gate:* a passage counts as evidence only if the decision model judges it relevant to the question.
   If none qualifies, the question is refused with a reason instead of answered.
3. *Sentence fact-check:* each generated sentence is checked against the passages it cites; unsupported ones are
   dropped and the drop is reported. In a live run this caught "Firms stopped showing up to bid because the cancellation
   was substantial", which its source does not say; word overlap would have passed it.
4. *Honest caveats:* each response names the retrieval and checking method actually used, flags a cut-off model
   output as a failure, and falls back to quoted sentences when a model fails.

The decision model was chosen by a test written before any run (26 labelled decisions): Laya (0.45 GB) was the only
candidate without a PyTorch dependency to pass every bar (fact-check 12/12, relevance 6/6, tagging 6/8, 29 ms per
decision).

**Conflicting evidence.** Each ICR's outcome rating is compared with the project's last supervision (ISR)
development-objective rating, both parsed from the report. A disagreement (opposite sides of satisfactory, or 2+
points apart) appears as a caveat wherever that report is cited, with both ratings and the ISR date. Method: the ICR is
the later, evidence-based verdict and is treated as final; the ISR is shown as context; the two are never averaged.
104 of 120 reports could be judged; 11 disagree. Where a table row could not be read reliably, no verdict is given.

**Measured faithfulness.** 15/15 answerable questions answered, 53/55 answer sentences supported by their citations,
5/5 unanswerable questions refused, including three that sound like procurement questions but are not covered. The
relevance labels behind these numbers agree with a hand check on 28 of 30.

**Not done yet.** The faithfulness judge is the model that wrote the answers (an independent judge is next);
procurement-specific conflicts (ISR tables carry no procurement rating); a larger evaluation set.

## Module 4: Continuous learning and implementation

**The loop that runs today.**

```
World Bank APIs ──► refresh ──► only new/changed passages embedded and tagged ──► models retrained ──► evaluation
       ▲                                                                                                │
       └────────────── planners use Assess / Ask ──► feedback (useful, not useful, flagged citation) ◄───┘
```

- `python -m procintel.refresh` re-fetches listings, keeps existing reports, rebuilds what depends on them, retrains
  the prediction models and logs what changed (documents, notices, passages, metrics before and after). Measured:
  2.9 min with fetching, 6 s without.
- Every answer and assessment is logged with an id; feedback attaches to that exact response. Flagged citations are
  listed in the evaluation report as candidates for the test set or the chunker.
- The evaluation report compares each run with the previous one (`eval/history.jsonl`), so a refresh that degrades
  retrieval is visible.
- A settings page tunes models, endpoints and thresholds live, validated, with saving; model servers release their
  memory after 5 idle minutes.

**Pilot rollout (proposed; full plan with entry and exit criteria, KPI definitions and baselines in
`docs/pilot-plan.md`, measurable KPIs from the logs via `python -m procintel.kpi`).**

| phase | who | what is measured |
|---|---|---|
| 1. Shadow (4–6 weeks) | 5–10 procurement specialists, current packages | retrieval precision of flagged vs accepted citations; share of answers rated useful; refusal rate on real questions |
| 2. Assisted planning (one region, one quarter) | planners use Assess when preparing procurement plans | predicted vs actual tender-to-award time on packages tendered in the pilot; planning time per package against the prior quarter |
| 3. Wider rollout | more regions, scheduled refresh | weekly active users; feedback volume; evaluation trend after each refresh |

KPIs and how each is computed: retrieval precision/recall from the evaluation set plus flagged citations; answer
faithfulness from the sentence checks; prediction error on packages awarded after the model was trained; planning
cycle time from timestamps of plan drafts (needs the planners' system); adoption from the response log.

**Not done yet.** Scheduled refresh and live reload of the backend; retraining triggered by feedback or evaluation
drift; feedback-driven additions to the evaluation set.

## Summary

| module | MVP status | strongest evidence | biggest gap |
|---|---|---|---|
| 1 Ingestion | done | 0 leaky passages after cleaning, 99.8% of words kept | supplier entity resolution |
| 2 Prediction & retrieval | done | award-time error 74 vs 81 days; hybrid P@5 0.77 vs 0.64 | censoring (survival model) |
| 3 Guardrails | done | 53/55 sentences supported, 5/5 refusals, fabrication caught live | independent faithfulness judge |
| 4 Continuous learning | done | one-command refresh with change log; feedback in the evaluation report | scheduling and drift-triggered retraining |
