# Work tracker: the four modules of the assessment brief

**Plan (agreed 2026-10-24):** first build every module as a minimal working version (the MVP list below), so the
whole loop works end to end: data → answers and predictions → user feedback and evaluation → refresh and retrain.
Then improve, driven by what the feedback and evaluation numbers show.

How the parts work:

- **MVP**: one ordered list across all modules, worked top to bottom first.
- **Queue** (per module): tasks you give me. They are taken before anything else, in file order. A task added to a
  queue that already has tasks waits its turn.
- **In progress**: what I am working on now (at most one item in the whole file).
- **Improvements** (per module): everything beyond the MVP, done after the MVP list is empty.
- **Done** (per module): finished work with the commit that holds it and how it was verified.

Line format: `- [ ] task (added 2026-10-24, by you|me)`. Finished: `- [x] task — <commit> — <how verified>`.

Order of work: In progress → Queues (file order) → MVP list → Improvements (Module 2, 3, 4, 1, Proposal).

---

## In progress

_(none)_

## MVP (in order)

- [ ] **M4** Evaluation report combining the test set and user feedback, re-run after each refresh (added 2026-10-24, by me)
- [ ] **M4** Basic configuration page: view and change the main settings (models and endpoints, retrieval k, thresholds, LLM settings) through a backend /config endpoint, validated and applied live (added 2026-10-24, by you)
- [ ] **Proposal** README: setup, models, how to run each step (added 2026-10-24, by me)
- [ ] **Proposal** Short write-up per module, using the prototype's measurements as evidence (added 2026-10-24, by me)

Status at a glance (2026-10-24): Module 1 MVP done · Module 2 retrieval done, prediction pending · Module 3 guardrails
done, conflict check and evaluation pending · Module 4 most of the MVP pending · Proposal not started.

---

## Module 1: Ingestion pipeline and knowledge representation

> Brief: ETL and entity resolution over tabular feeds and long documents; an ER schema or knowledge graph linking
> records across keys (supplier contract row ↔ ICR lesson via project ID, sector codes, temporal proximity);
> parsing, chunking and embedding strategy for 100+ page reports with tables and annexes.

### Queue

_(empty)_

### Improvements

- [ ] Supplier entity resolution: 225 duplicate normalised names are not merged into firms (added 2026-10-24, by me)
- [ ] Link contract rows to ICR passages by sector and time, not only project ID (added 2026-10-24, by me)
- [ ] Tables: report text comes from the World Bank text files, so tables arrive flattened; parse them or index page images (added 2026-10-24, by me)
- [ ] Data quality debts: 4 reports keep ~51% of their text; 137 packages have award before tender; data-sheet tables mixed with lessons (added 2026-10-24, by me)
- [ ] Sources unavailable: Major Contract Awards (endpoint now returns HTML), WGI (indicator not found) (added 2026-10-24, by me)
- [ ] Optional: wrap cleaner, embedder and tagger as a LlamaIndex IngestionPipeline (added 2026-10-24, by me)

### Done

- [x] World Bank API client with caching and retries (projects, notices, WDS documents, CPIA) — 98ac4a5 — live calls 2026-10-23
- [x] Raw load into DuckDB and normalised model: project, package (tender-to-award days), notice, supplier, award_supplier, document, cpia — 98ac4a5 — row counts in docs/data-model.md
- [x] Notice parser: award dates, prices (USD preferred), suppliers incl. names with brackets — 98ac4a5 — tests/test_parse_notice.py
- [x] ER diagram, grains and measured limitations — 98ac4a5 — docs/data-model.md
- [x] Section-aware report chunker: numbered-paragraph anchors, footnote removal, table detection — 7eba647 — tests/test_chunk.py
- [x] Header/footer removal: 1,360 of 19,169 chunks leaked page furniture, now none; 99.8% of real words kept — f5d1a8b — audit of every removed line, before/after word count
- [x] Length cap: 107 chunks over 1,400 characters split at word boundaries — 55911af — max 1,400 after rebuild
- [x] Shared statistics module (options, benchmarks, CPIA) with deterministic output — 7026465, 5084daf — fixtures equal as data, repeat export same hash
- [x] Embeddings: EmbeddingGemma 2 (256 dims) for 18,992 passages, incremental by text hash — a36f209 — 326 s full run, re-run embeds 0
- [x] Passage tags by the decision model (Laya), incremental — d19a6e8 — 18,140 tagged in 653 s; problem-type labels hand-checked at ~7/18, so only "not a lesson" (≥0.9) is used

---

## Module 2: Predictive and prescriptive engines

> Brief: a model (e.g. gradient-boosted trees) predicting tender completion time, amendment probability and
> re-bidding risk from project variables and governance indicators; agentic retrieval that surfaces precedents,
> similar past specifications and lessons when a user starts a package.

### Queue

_(empty)_

### Improvements

- [ ] Survival model for award time that uses never-awarded tenders as censored rows (recent tenders look fast because slow ones are unawarded; the current model still gives Kenya CW/RFB 17% >180 days where 37% of comparable past packages took that long) (added 2026-10-24, by me)
- [ ] Contract value as a feature: convert local-currency prices to USD and use the planner's estimate (added 2026-10-24, by me)
- [ ] Precedents: decision model checks each candidate is a lesson relevant to the package (Kenya/CW/RFB still shows a disbursement table and an indicator list) (added 2026-10-24, by me)
- [ ] Re-bidding label per project from ICRs via the decision model, then re-bidding risk (added 2026-10-24, by me)
- [ ] Amendment probability from notice versions, after confirming what a version number means (added 2026-10-24, by me)
- [ ] Agentic retrieval: multi-step (reformulate, retrieve, check, retrieve again) instead of single pass (added 2026-10-24, by me)
- [ ] Similar past specifications: match a new package's description to past notices by embedding (added 2026-10-24, by me)

### Done

- [x] Prediction model: gradient-boosted trees (from scratch) for tender-to-award days p50/p90 and >180-day risk; /assess adds flags with basis "model" — db56ce2 — 5-fold CV grouped by project on 1,145 packages vs the app's median baseline: typical-days MAE 74.4 vs 81.2, p90 pinball 25.2 vs 26.0, >180 Brier 0.147 vs 0.167 (AUC 0.81 vs 0.74); a model is used only with ≥2% lower error. Live check: Kenya CW/RFB 102 days (history 113)
- [x] Timeline benchmarks and risk flags from historical statistics, falling back to wider slices when thin — bf7f501 — Kenya/CW/RFB n=195 median 113, same as the mock
- [x] BM25 retrieval via LlamaIndex with country / procurement-type / kind filters — ea742cf — tests/test_retrieve.py
- [x] Hybrid retrieval: BM25 + EmbeddingGemma vectors, reciprocal rank fusion, BM25 fallback — a36f209 — 3 tests with a fake embedder; 4-question comparison in the commit
- [x] Cited answers written by a local model (Saluki 27B via llama.cpp), thinking disabled — d1e1020 — 4 cited sentences per question in 13–30 s
- [x] FastAPI backend /options /assess /ask matching the web contract — bf7f501 — tests/test_api.py, both flows checked in Chrome

---

## Module 3: Guardrails, faithfulness and source attribution

> Brief: validation layers so every recommendation or risk flag is anchored in documents and records; a method for
> conflicting evidence (e.g. an ICR contradicting supervision ISR ratings).

### Queue

_(empty)_

### Improvements

- [ ] Procurement-specific conflicts: ISR tables carry only DO and IP ratings, not a procurement rating; compare the ICR's procurement text (e.g. "procurement rated Satisfactory") with the IP rating trend (added 2026-10-24, by me)
- [ ] Independent faithfulness judge: the answer model currently grades its own sentences (53/55 supported may be optimistic) (added 2026-10-24, by me)
- [ ] Evidence gate barely filters: it kept 5 of 5 passages on most questions (gate precision 0.77 = hybrid P@5); tune the threshold or ask a stricter question (added 2026-10-24, by me)
- [ ] Larger evaluation set (~100 questions) once the MVP set shows where answers fail (added 2026-10-24, by me)
- [ ] Risk flags carry their evidence: link each flag to the packages or passages it rests on (added 2026-10-24, by me)
- [ ] Two-step passage tagging (is a problem described? then which type) to make problem types usable (added 2026-10-24, by me)

### Done

- [x] Evaluation set and runner: 20 questions (15 answerable, 2 off-topic controls, 3 in-domain traps), pooled relevance judged by the answer LLM, `python -m procintel.evaluate judge|sample|run` → eval/report.md — b6ba812 — 232 judged pairs; judge agreed with my hand labels on 28/30 (eval/judge_check.md). Hybrid P@5 0.77 vs BM25 0.64, recall@10 0.76 vs 0.62; 15/15 answered, 53/55 sentences supported, 5/5 unanswerable refused, median 23 s
- [x] Conflicting evidence: each ICR's outcome rating vs the last ISR development-objective rating (both parsed from the report's data sheet); a disagreement (opposite sides of satisfactory, or 2+ points apart) becomes a caveat on /ask and /assess naming both ratings and the ISR date, the ICR treated as the later verdict, never averaged — 594011d — 104 of 120 reports judged, 11 conflicts; ISR rows parsed 97.3% (wrapped cells handled; an ambiguous last row must conflict under every reading; an unreadable later rated row gives no verdict); two flagged reports checked against raw text found and fixed a stale-last-row bug; live /ask on Morocco P165411 shows the caveat
- [x] Every answer sentence cites passages; citation cards show quote, section ¶, project, PDF link — bf7f501 — tests/test_api.py
- [x] Unsupported questions refused, not guessed — bf7f501, a0a125d — "boiling point of tungsten" refused
- [x] Decision model (Laya) as evidence gate, sentence fact-check and quote picker; word-overlap fallback — a0a125d — pre-registered 26-question check; caught a real fabrication in a live run
- [x] Cut-off model output treated as an error; caveats name the retrieval and checking method actually used — d1e1020 — tests/test_answer.py
- [x] Model choice by a pre-registered test across Decider-2B/4B, Kev-4B and Laya — a0a125d — results in the commit message

---

## Module 4: Continuous learning and implementation strategy

> Brief: a closed loop where new milestones, supervision notes and amendments update the models and vector indices;
> a phased pilot rollout with KPIs (planning cycle time, retrieval precision/recall, adoption).

### Queue

_(empty)_

### Improvements

- [ ] Full configuration dashboard: every tunable (retrieval pool/RRF, embedding dim, precedent filter, per-model options), saved profiles, before/after evaluation on change (added 2026-10-24, by you)
- [ ] Scheduled refresh (e.g. nightly) and a backend reload so a refresh reaches the running server without a restart (added 2026-10-24, by me)
- [ ] Retraining triggered by feedback volume or evaluation drift, not only by refresh (added 2026-10-24, by me)
- [ ] Pilot rollout plan and KPI definitions with how each is measured (added 2026-10-24, by me)

### Done

- [x] `python -m procintel.refresh`: re-fetches listings (projects, notices, ICR list) while keeping cached ICR texts and existing ICRs, then model tables → chunks → embeddings and tags (incremental) → rating check → prediction models; table refresh_log records added/changed/removed documents, new notices, project status changes, passages embedded/tagged, model metrics before and after, and per-step times — COMMIT — --skip-fetch run: 0 changes, 0 re-embedded, 0 re-tagged, 5.8 s; live run: 304 listings re-fetched from the network (cache files rewritten), 0 texts re-downloaded, no changes since the 2026-10-23 ingest, 2.9 min; change detection covered by 2 unit tests
- [x] Feedback capture: every /ask and /assess response logged with a responseId; POST /feedback (useful / not_useful / bad_citation naming a shown citation, optional comment); "Was this useful?" bar and "flag citation" on answers and assessments; separate data/feedback.duckdb so the server never blocks the build commands — 9d6aa0d — 4 API tests (unknown response, citation not shown, missing citation, bad rating all 400); in Chrome: flagged a citation and sent "not useful" with a comment, both rows stored against the logged response, no console errors
- [x] Embeddings and tags re-run only for new or changed passages (text hash per model) — a36f209, d19a6e8 — re-run embeds 0
- [x] All models swappable by configuration; documented in .env.example — b8d7c0e — backend starts from it
- [x] Idle model servers release memory: --sleep-idle-seconds 300 on all three llama-servers — 911f037 — Saluki wired memory 12.6 → 3.6 GB after idle, 1.4 s to wake

---

## Proposal (the written deliverable)

### Queue

_(empty)_

### Improvements

- [ ] Full technical proposal document per the brief's four modules, after the MVP write-up (added 2026-10-24, by me)
