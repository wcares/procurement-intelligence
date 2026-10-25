# Work tracker: the four modules of the assessment brief

One section per module of `assessment.md` §4. Each section has four parts:

- **Queue**: tasks you give me for this module. Add a line at the bottom of the module's queue; I take queued tasks
  first, top to bottom, before anything in "Remaining". A task you add to a queue that already has tasks waits its turn.
- **In progress**: what I am working on now (at most one item across the whole file).
- **Remaining**: gaps I identified against the brief, in the order I plan to do them.
- **Done**: finished work with the commit that holds it and how it was verified.

Line format: `- [ ] task (added 2026-10-24, by you|me)`. When a task is done it moves to Done as
`- [x] task — <commit> — <how it was verified>`.

The written proposal the brief asks for is tracked under "Proposal" at the end; the prototype is its evidence.

Status at a glance (2026-10-24): Module 1 most of it · Module 2 about half (retrieval yes, prediction no) ·
Module 3 about half · Module 4 barely started · Proposal not started.

---

## Module 1: Ingestion pipeline and knowledge representation

> Brief: ETL and entity resolution over tabular feeds and long documents; an ER schema or knowledge graph linking
> records across keys (supplier contract row ↔ ICR lesson via project ID, sector codes, temporal proximity);
> parsing, chunking and embedding strategy for 100+ page reports with tables and annexes.

### Queue

_(empty)_

### In progress

_(none)_

### Remaining

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

### In progress

_(none)_

### Remaining

- [ ] Prediction model: gradient-boosted trees trained from scratch on packages for tender-to-award days (median, p90) and >180-day risk; project-grouped CV vs the median baseline; shown in /assess as basis "model" only if it beats it (added 2026-10-24, by me)
- [ ] Precedents: decision model checks each candidate is a lesson relevant to the package (Kenya/CW/RFB still shows a disbursement table and an indicator list) (added 2026-10-24, by me)
- [ ] Re-bidding label per project from ICRs via the decision model, then re-bidding risk (added 2026-10-24, by me)
- [ ] Amendment probability from notice versions, after confirming what a version number means (added 2026-10-24, by me)
- [ ] Agentic retrieval: multi-step (reformulate, retrieve, check, retrieve again) instead of single pass (added 2026-10-24, by me)
- [ ] Similar past specifications: match a new package's description to past notices by embedding (added 2026-10-24, by me)

### Done

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

### In progress

_(none)_

### Remaining

- [ ] Conflicting evidence: compare each ICR's procurement verdict with its ISR ratings and show disagreements with both sources (added 2026-10-24, by me)
- [ ] Labelled evaluation set (~100 questions) with retrieval precision/recall and answer faithfulness numbers (added 2026-10-24, by me)
- [ ] Risk flags carry their evidence: link each flag to the packages or passages it rests on (added 2026-10-24, by me)

### Done

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

### In progress

_(none)_

### Remaining

- [ ] Incremental refresh: fetch new notices and reports, re-chunk, re-embed, re-tag and retrain only what changed (added 2026-10-24, by me)
- [ ] Feedback capture in the UI (useful / wrong citation) stored for evaluation and retraining (added 2026-10-24, by me)
- [ ] Configuration dashboard: web page + backend /config to view and tune models, endpoints, retrieval k/pool/RRF, thresholds, embedding dim, LLM settings; validated, applied live, optional save (added 2026-10-24, by you)
- [ ] Pilot rollout plan and KPI definitions with how each is measured (added 2026-10-24, by me)

### Done

- [x] Embeddings and tags re-run only for new or changed passages (text hash per model) — a36f209, d19a6e8 — re-run embeds 0
- [x] All models swappable by configuration; documented in .env.example — b8d7c0e — backend starts from it

---

## Proposal (the written deliverable)

### Queue

_(empty)_

### Remaining

- [ ] README: setup, models, how to run each step (added 2026-10-24, by me)
- [ ] Technical proposal covering the four modules, using the prototype's measurements as evidence (added 2026-10-24, by me)
