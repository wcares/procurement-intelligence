# Procurement Intelligence Platform: technical proposal

This proposal answers the four modules of the assessment brief (§4, not included in this repository) with a design that runs: a working prototype on World Bank
public data, built and measured alongside the design. Each module states the design, what the prototype does, the
measured evidence, and the open gaps. Every figure comes from the running system as of 2026-10-26 (tables in DuckDB,
`eval/report.md`, `eval/history.jsonl`, the saved model, or a run recorded in `docs/TRACKER.md`). The design documents
behind it: `docs/architecture-principles.md`, `docs/data-model.md`, `docs/event-pipeline-design.md`,
`docs/ui-design.md`, `docs/pilot-plan.md`, `docs/pipeline-overview.md`. The MVP write-up this replaces is in the git history.

---

## 1. The problem and who it serves

When a World Bank-financed project buys works, goods or services, each tender (a *package*) has to be planned: which
procurement method, how long it will realistically take, what is likely to go wrong. That knowledge exists, but in
three silos: procurement registries record what happened (notices, awards, contracts), supervision and completion
reports explain why it went well or badly, and governance indicators describe the context. Planners reconcile them by
hand and repeat past mistakes: unrealistic schedules, re-tenders, cancellations, mismatched specifications.

The platform serves two roles, enforced in the backend:

| role | who | uses |
|---|---|---|
| **planner** | World Bank task teams and procurement specialists, borrower implementing agencies | assess a planned package; ask questions of the evidence; follow ongoing projects; recommendations and goal seeking |
| **admin** | the team running the platform | everything above, plus data pipeline, connectors, rules, evaluation, prompts, models, users |

It supports the planner's decision and never makes it: it does not choose a bidder, and the Procurement Regulations
still decide which methods a contract may use.

**What a planner gets, for a package.** How comparable packages went (timeline by stage, typical and slow case); a
forecast for this package (a gradient-boosted model where it beats the historical median, else the median); risk flags
(slow award, re-tendering, amendments, governance), each with its evidence; quoted lessons from comparable projects;
similar past contracts; recommendations drawn only from statistics and cited passages; for a package already under
way, a forecast from where it is now; and, working backwards from a target ("awarded within 90 days"), the set-ups that
met it most often.

---

## 2. Architecture

```
 World Bank APIs ─┐                                        ┌─► Assess · Ask · Insights · package pages (planners)
 (projects, notices, │   connectors     event pipeline      │
  documents, contracts,├─► poll / push ─► detect changes ─► rules ─► actions ─► tables · passages · vectors · tags
  indicators)       │   (configurable)   (state + events)    │        (jobs,   · models · alerts
 uploads (PDF, Word) ─┘                                       │         idle    │
                                                              │         time)   └─► backend (FastAPI) ─► web (Next.js)
                     evaluation · shadow builds · drift checks · feedback ◄──────────┘
```

| layer | prototype | production (configuration only) |
|---|---|---|
| tables and state | DuckDB files | Postgres (`PROCINTEL_DB_URL`; checked: same answers on Postgres 17) |
| vectors | DuckDB table, in-memory search | Qdrant (`PROCINTEL_VECTOR_URL`); a graph index such as LEANN is an option for much larger corpora (§9) |
| raw files | data folder | S3 or MinIO (`PROCINTEL_BLOB_URL`) |
| models | llama.cpp on the host: Saluki 27B (answers), EmbeddingGemma 2 (vectors), Laya (decisions) | any endpoint by URL (`PROCINTEL_LLM_API_BASE`, `_EMBED_`, `_DECIDE_`, `_JUDGE_`), through LiteLLM |
| background work | a worker thread that runs jobs only while the app is idle | separate worker containers claiming jobs from Postgres |
| deployment | `next dev` + `uvicorn` | Docker Compose: web, api, worker, postgres, qdrant (built and run, `compose.yaml`) |

The governing rule (`docs/architecture-principles.md`): every part is replaceable by configuration or registration,
nothing hard-coded. Models, thresholds, prompts (versioned, evaluated before activation), pipeline rules, connector
settings and package-status parameters are all settings, validated, with dry runs where a change has reach.

---

## 3. Module 1: ingestion pipeline and knowledge representation

### 3.1 Sources and coverage (as of 2026-10-26)

| source | form | becomes |
|---|---|---|
| Projects API | JSON | 151 projects in 80 countries: 121 with completion reports, 30 ongoing (Active, approved since 2021, closing 2028-2032) |
| Procurement notices API | JSON + notice HTML | 11,895 notices → 8,175 packages (keyed project + bid reference), 1,423 with a measured tender-to-award time |
| Finances One (DS00005) | signed contracts | 16,414 contract awards; their signing dates fill 114 missing award dates |
| Documents API | plain-text exports of 100+-page reports | 120 completion reports (ICRs), 114 supervision reports (ISRs), 92 restructuring papers → 22,060 citable passages |
| Indicators API | country series | CPIA (6,444 rows, 59 countries; IDA countries only) and WGI (11,104 rows, 69 countries) |
| uploads | PDF, Word, text, HTML | stored, extracted, classified, linked; completion reports about tracked projects join the evidence |

### 3.2 Entity-relationship schema and reconciliation across keys

The model is relational with an explicit link layer (`docs/data-model.md` has every table's grain and the measured
gaps). The brief's example, a supplier contract row linked to a section of an ICR lesson via project, sector and time,
is answered in three steps of increasing looseness:

1. **Exact keys first.** Contract, notice, package, project and report share `project_id`; a report covering several
   projects is split into `document_project`. Citations rest on these exact links.
2. **Entity resolution where keys disagree.** Notices of one tender are grouped into a package by bid reference; an
   award filed under a re-tender suffix ("-1") is relinked to its tender (10 cases) and the original of an X / X-N pair
   is marked as re-tendered (28); supplier ids of the same firm are merged (5,415 ids → 5,019 firms).
3. **Sector and temporal proximity.** A contract is linked to the completion reports of other projects in the same
   sector family that were running when it was tendered (`package_icr_link`, 70,618 links), so Assess can draw
   same-sector lessons from other countries when a country's own reports cover other sectors.

Passages carry `doc_id`, section and paragraph (the citation anchor), and get a vector, a procurement-topic tag and,
where the tagger flags a possible problem, a problem label.

### 3.3 Parsing, chunking and embedding long reports

- **Layout-aware chunking per document type.** Completion reports and restructuring papers number their paragraphs,
  so passages follow numbered paragraphs and keep section and ¶ as the anchor; running headers, footers, page numbers
  and footnote blocks are removed first (before that fix 7% of passages carried page furniture; after it none, 99.8% of
  real words kept). ISRs have their own chunker: numbered sections, unnumbered paragraphs joined up to a size, and the
  ratings and risk tables kept as table passages; results-indicator tables, which text extraction scrambles, are left
  out. Across the pipeline 86% of a report's words reach the index; the rest are removed on purpose (contents,
  headings kept as labels, staff lists, data sheets).
- **Embeddings:** EmbeddingGemma 2 with its retrieval prompts, truncated to 256 dimensions; stored with the model name
  and a text hash, so a rebuild embeds only new or changed passages and passages that only moved keep their vectors,
  tags and evaluation labels.
- **Tags from a decision model:** Laya returns calibrated probabilities for fixed choices (procurement topic per
  passage, 20,663 tagged); the answer model then labels whether a flagged passage describes a problem (3,776 labelled,
  1,582 problems; 29 of 30 right in a hand check, the problem *kind* only 8 of 13, so only problem/no-problem is shown).
- **Tables:** flattened tables are detected and marked as table passages; image-based table extraction is a gap (§9).

### 3.4 An event-driven pipeline instead of rebuilds

Six source types are tracked (`docs/event-pipeline-design.md`): notices, projects, contract awards, indicators,
completion reports, and ISRs / restructuring papers. Each read is compared with stored fingerprints; differences become
events (`Notice.added`, `Project.changed`, ...); 11 default rules turn events into 15 registered actions (write rows,
rebuild tables, cut and index passages, checks, alerts, drift check, reload), coalesced so an action asked for by many
events runs once per batch. Rules are editable by admins with validation, cycle detection and a dry run on the last
week's events. Connectors are configuration (poll interval, on/off, or push through a signed webhook), back off when a
source fails without stopping the others, and are shown with cursor, last success and last error. The weekly full
refresh remains as a reconciliation.

---

## 4. Module 2: predictive and prescriptive engines

### 4.1 Timeline and risk models

**Before tendering.** Gradient-boosted trees (scikit-learn) predict tender-to-award days (median, 90th percentile) and
the chance of exceeding 180 days, from what a planner knows: procurement group and method, region, sector, CPIA scores
of the tender year, contract value; and, when the package's project is known, years from project approval and project
size (a second variant). Training uses only packages with 18 months of follow-up (1,336), because recent tenders enter
the data only if awarded quickly, which made a first version learn that recent years are fast.

| metric (5-fold CV grouped by project, averaged over 5 random project splits) | model | model, project known | historical median |
|---|---|---|---|
| typical days, mean absolute error | 82.5 | 80.8 | 84.9 |
| > 180 days, Brier score | 0.168 | 0.165 | 0.174 |
| > 180 days, AUC | 0.77 | 0.78 | 0.72 |
| 90th percentile, pinball loss | 30.8 | 29.2 | 29.3 |

A model is used only where it beats the baseline by at least 2%, decided on the repeated runs: a single run was a coin
toss near that bar (gains from -1.1% to +5.8% over five splits). So the typical time and the over-180 risk come from
the model and the slow case from history; every model number is labelled with its test error.

**Under way: survival.** For a package already in bidding, the forecast is a Kaplan-Meier estimate over comparable
tenders, given that this one is still open at its age: awarded tenders are events, tenders still open are censored at
their age, and tenders open past any normal time (status *stale*) are left out, since many were awarded without a
published notice. Counting open tenders as waiting moved the median forecast for the 244 live tenders from 74 to 109
days and the chance of an award within 90 days from 53% to 43%: the earlier estimate, from awarded tenders only, had
leaned early.

**Risks beyond time.** Re-tendering and amendment risks come from evidence, not a classifier: re-bid evidence in
notices (re-tender references, awards under a suffix) and in completion-report passages (71 passages from 26 projects),
amendment evidence (15 from 11 projects), each stated as "at least N of M comparable projects" because the evidence
only shows positives. Governance (CPIA; for 18 of the 21 countries without CPIA, which covers IDA countries only, WGI) flags context risk.

### 4.2 Retrieval for precedents and lessons (RAG)

Hybrid retrieval: BM25 and vector search over the same filtered passages (country, procurement group, sector), merged
by reciprocal rank fusion; the question is also rephrased into the reports' vocabulary and searched again when that
adds evidence; an evidence gate (the answer model) keeps only passages that help answer; answers are written only from
those, at most four cited sentences. On the evaluation set (100 questions, 80 answerable; 1,437 judged question-passage
pairs, the judge agreeing with a hand check on 28 of 30): hybrid precision@5 0.70 against 0.54 for BM25 alone, recall@10
0.71 against 0.48 (with ISRs and restructuring papers in; 0.78 before they enlarged the pool of relevant passages), gate
precision 0.90.

Assess surfaces quoted lessons from comparable projects (same country and group first, widening to the region or
sector when too few), similar past contracts by description embedding (with award time, value and re-tendering), and
an answer map that shows which sources back each sentence.

### 4.3 Prescriptive: recommendations, goal seeking, monitoring

- **Recommendations** come only from statistics and cited passages: a method that was clearly faster for the same kind
  of purchase (median at least 20% shorter, 10+ packages each, with the value-threshold caveat), and, for the flagged
  risks, what past projects did, asked through the answer pipeline so every sentence is cited and checked. With no
  supporting evidence, none is made.
- **Goal seeking** works backwards from a target ("awarded within 90 days"): methods and lot splits ranked by the share
  of comparable packages that met it, with n and scope; lot values outside what a method was used for are flagged for
  the thresholds; worded as association ("packages set up this way were faster"), not cause.
- **Plan a project** takes several packages of a new project, forecasts each with the assessment, and lays them on one
  timeline with the likely bottleneck and a deadline check. It has two ways in: a **planning chat** (the default) and a
  manual form, both editing one plan. In the chat the language model only reads the message and proposes edits; every
  edit is checked against the data's own vocabulary (countries, purchase types, methods used for that type, values,
  links) before it reaches the plan, defaults are stated as assumptions, and what cannot be checked becomes a question.
  The forecast numbers come from the engine, never from the model. The same chat answers questions about the plan (only
  from the forecast it was given; an answer containing a number that is not in the forecast is replaced by the forecast
  itself), statistics about past projects (the Overview's measures, shown as a table), and questions about what went
  wrong in past projects (the cited-answer pipeline). The conversation lives in the browser, a context guard stops it
  before the model's window is full, and the interpreter is measured on 28 messages (`eval/plan_chat_cases.jsonl`,
  `python -m procintel.assistant.evaluate`): 28 of 28 with the local answer model on 2026-10-27.
- **Monitoring** stamps every package of every tracked project active (bidding or contract running), finished,
  replaced (re-tendered) or stale, by configurable rules with reasons and a dry run (now: 495 active, 6,438 finished,
  30 replaced, 1,212 stale); active packages get the survival forecast, the contract end, and warnings (slower than 9 in
  10, re-issued notice, contract ending after the project closes, a downgrade in the newest ISR).

---

## 5. Module 3: guardrails, faithfulness and source attribution

### 5.1 Validation layers

1. **Citation by construction.** Every answer sentence and recommendation carries the passages it rests on; every risk
   flag carries its evidence (notices, packages, passages, indicators) with links to the source documents.
2. **Evidence gate.** A passage counts as evidence only if judged to help answer the question; if none qualifies the
   question is refused with the reason, not answered.
3. **Sentence check.** Each generated sentence is checked against its cited passages and dropped if unsupported, and
   the drop is reported. In a live run it caught "firms stopped showing up to bid because the cancellation was
   substantial", which its source does not say.
4. **An independent judge in evaluation.** A second model checks the answer model's sentences; where the two disagree
   (7 of 285 sentences) the case goes to a person in the labelling queue.
5. **Honest outputs.** Every response names the methods and models actually used, labels model numbers with their test
   error and statistics with their sample, falls back to quoted sentences when a model fails, and says when evidence is
   too thin ("not enough comparable packages", "beyond the data").
6. **Predictions are never data.** Forecasts are drawn as forecasts, replaced by real dates when they arrive, never
   written into the records and never used to train.
7. **Inputs are checked too.** Uploaded files are classified by their own title before any model guess (the decision
   model alone called a supervision report a completion report at 84%; that file was taken back out of the evidence
   and the rule changed), and only a titled completion report about a tracked project joins the evidence.

Measured on the evaluation set: 77 of 80 answerable questions answered, 277 of 285 sentences supported by their
citations according to the answer model and 282 of 285 according to the independent judge, 20 of 20 trap questions
refused.

### 5.2 Conflicting institutional evidence

Each completion report's outcome rating is compared with the project's last ISR development-objective rating, both
parsed from the report (104 of 120 could be judged; 11 disagree). The method: the completion report is the later,
evidence-based verdict and is treated as final; the ISR is shown as context, with its date; the two are never averaged;
a disagreement appears as a caveat wherever that report is cited. Procurement ratings in completion reports are
checked against the overall verdict the same way (52 reports state one; 6 rate procurement below a satisfactory
overall verdict). Statistics that report "what the completion reports say" read completion reports only, so ISRs and
restructuring papers add evidence without changing those counts.

---

## 6. Module 4: continuous learning and implementation strategy

### 6.1 The closed loop

New milestones (notices, awards), supervision notes (ISRs), amendments and restructurings (restructuring papers,
re-issued notices) enter as events; the rules re-cut and re-index only what changed (vectors, tags, checks), rebuild
the tables, and queue a drift check when award times change. The loop ran for real on 2026-10-26: adding the ongoing
portfolio labelled 70 new packages, the drift check found the model's error on them at 130 days against 76 in
cross-validation and retrained it; the retrained model no longer cleared the 2% bar on a single run, the app fell back
to the historical medians (the guard working), and the investigation led to the repeated-run decision and the project
variant, which put the model back in use. Every retrain is kept in a model history with its metrics.

Index and prompt changes are tested before they go live: an alternative index is built as a *shadow* next to the live
one and promoted only if it measures better (semantic chunking was tried and not promoted: precision@5 0.67 against
0.70); a new prompt version answers the same sample questions as the active one before it can be activated.

Users feed the loop: every response is logged with a pseudonymous user id; ratings and flagged citations attach to it;
citations flagged on two separate responses are demoted in search; refused and not-useful questions become candidates
for the evaluation set, and relevance labels and judge disagreements go to people in a labelling queue. An Evaluation
page shows quality over time with the changes between runs (refreshes, retrains, promotions, question-set changes),
comparisons with promote / discard, and model history. Logs and history are kept 30 days.

### 6.2 Pilot rollout and KPIs

Full plan with entry and exit criteria in `docs/pilot-plan.md`:

| phase | who and what | move on when |
|---|---|---|
| 0. Pre-pilot | logging of user ids, package references, response times | the KPI script reports them on test data (done) |
| 1. Shadow (4-6 weeks) | 5-10 procurement specialists on packages they already plan | 150+ rated responses, 60%+ useful, flagged citations under 5 per 100, no acted-on unsupported claim |
| 2. Assisted planning (one region, one quarter) | planners use Assess for procurement plans | predicted vs actual award time on 30+ packages; half the group active weekly |
| 3. Wider rollout | more regions, scheduled pipeline, feedback-driven evaluation | — |

KPIs, each with how it is computed and today's baseline: retrieval precision (0.70) and recall (0.71) from the
evaluation set; faithfulness (282/285 by the independent judge); refusals of unanswerable questions (20/20); award-time
error on pilot packages against the median baseline; useful share and flagged citations from ratings; weekly active
users from the pseudonymous log; response time (34 s per question, median); planning cycle time from the planners' own
plan records, before and after.

---

## 7. What a user sees

| page | for | shows |
|---|---|---|
| Overview | planners | what went wrong in past procurement, ranked and by year, every number clickable to its records |
| Assess a package | planners | stage timeline with the package's own estimate and risks placed by stage; forecast, flags with evidence, governance, similar contracts as a chart, quoted lessons; "already started?" forecast from today; set a goal; recommendations |
| Plan a project | planners | a planning chat (default) or a form: several packages, a forecast for each, dates and bottleneck on one timeline, a deadline check, a goal search per package; questions about the plan, past statistics and past projects in the same chat |
| Ask the evidence | planners | cited answers, an answer map, country and type filters |
| Insights | planners | alerts on a personal watch-list, trends, ongoing work (projects and packages with status, forecasts and warnings), package pages with a live timeline |
| Pipeline | admins | connectors, event log, rules, upload, status rules |
| Evaluation | admins | quality over time, comparisons, prediction-model history, labelling queue |
| Settings | admins | models, thresholds, profiles, prompts, users, jobs |

---

## 8. How this meets the rubric

| dimension | where |
|---|---|
| System and knowledge architecture (30) | §2 configuration-replaceable layers, Postgres / Qdrant / object storage by setting; §3.2 relational schema with exact keys, entity resolution and sector-time links; §3.3 per-type chunking of long reports with tables marked; §3.4 event pipeline |
| Analytical and AI methodology (30) | §4.1 models with grouped, repeated CV against a stated baseline, survival with censoring for live tenders; §4.2 hybrid retrieval with gate and measured precision / recall; §5 validation layers, independent judge, citation by construction |
| Domain alignment and data use (25) | §3.1 all five World Bank sources plus uploads; procurement stages (plan, bidding, award, signing, contract) in the timeline and monitoring; missing and incomplete reporting handled explicitly: follow-up window for training, censored open tenders, stale status for unpublished awards, positive-only evidence stated as "at least" |
| Operationalization and scalability (15) | §2 Compose deployment and production mapping; §6 closed loop shown working on real drift; §6.2 phased pilot with KPIs and baselines |

---

## 9. Limits and next steps

- **Coverage.** 151 projects and 30 ongoing ones is a sample; the pipeline scales by connector settings, but the
  statistics for rarer methods and regions stay thin (methods with fewer than 10 packages are not used for estimates).
- **Tables in reports** are extracted from text exports; image-based extraction for tables and annexes is not built.
- **Re-tendering and amendments** rest on positive-only evidence, so they are not rates; a calibrated probability needs
  labelled negatives.
- **The slow case** (90th percentile) still does not beat history; the model is used only for the typical time and
  the over-180 risk.
- **Retrieval** is a fixed pipeline with one rephrasing step rather than a multi-step agent; similar past technical
  specifications are matched by description, not by specification documents.
- **Index size at full scale (a production scalability option).** The vector index is small at this sample size and
  Qdrant takes over in production (§2). If the corpus grew to the full World Bank archive, or had to run on modest
  hardware, LEANN (open source, MIT) is a candidate to test behind the same vector setting: it stores a pruned graph
  and recomputes embeddings at query time, and its authors report 91-97% smaller indexes than FAISS. That would cut
  storage and memory as the corpus and the number of tenants grow, at the cost of an embedding call per query
  (latency, and load on the embedding server). Not tested here, and the figures are the authors' own; the test to run
  is recall@10 and query time on the evaluation set against Qdrant, at several corpus sizes.
- **Planning chat:** conversations are not saved; the model's window is 8,192 tokens, so long conversations stop with a prompt to start a new one; a forecast of a two-package plan takes about two minutes on the local models. The interpreter test set is small (28) and written by the builder.
- **Not built:** the subscribe connector mode and image page indexing. OCR of scanned uploads and the Reviewer role were added on 2026-10-26.
- **Planning cycle time** cannot be measured from public data; it needs the planners' own records in the pilot.

---

## Appendix: running it

`README.md` covers set-up; `docker compose up` runs the full stack; `python -m procintel.learning.evaluate run`
reproduces the evaluation; `python -m procintel.prediction.predict` retrains and prints the cross-validation table
above; `docs/TRACKER.md` lists every change with its commit and how it was checked.
