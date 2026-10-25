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

_(empty: MVP complete 2026-10-25)_

Status at a glance (2026-10-25): **MVP complete for all four modules** (see docs/proposal.md). Work continues on the
Improvements lists, Module 2 first.

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

- [ ] Survival model for award time — DEFERRED 2026-10-25: of 859 tenders without an award, 805 are over 2 years old and ~723 have no award notice in the data at all (no-award shares 32-46% for every method, including open-bid works and goods that must publish awards), so they are mostly unpublished or unlinked awards, not open tenders; treating them as censored would inflate predicted times. Revisit after the two items above, if a reliable "still open" signal exists (added 2026-10-24, by me)

### Done

- [x] Retrieval for everyday wording: before the first search the answer LLM rephrases the question in the reports' vocabulary and the question and its rephrasings are searched and merged (VOCAB_STEP=1, on the Settings page; the old thin-evidence second search runs only when it is 0). If none of the kept evidence comes from the question's own search, that search is judged too: no evidence there means out of scope (refused), otherwise both are used — 1895e7d — relevant passages among the 12 the gate sees, judged labels plus new judgments: 10 everyday-wording questions 45 -> 59 (top 5: 20 -> 29), 10 standard 66 -> 73 (top 5: 40 -> 35; extra weight on the original query did not recover it). Traps with the step on all 20: high-speed rail kept the "HSIP" passage again (2 of 2), so the own-search check was added; refusing outright instead lost misprocurement and PPP. Full 100-question run (with the outright-refusal version): 77/80 answered, 277/285 and 282/285 sentences supported (answer model, independent judge), 20/20 unanswerable refused (was 19/20), median 34.0 s, everyday-wording 9/10 answered (q76 still refused); after the fix misprocurement and PPP are answered again (4 sentences each) and high-speed rail, casino and stadium are refused (checked directly, not a full re-run); 93 tests pass (1 new)
- [x] Similar past specifications: a package description is matched to 6,070 awarded package descriptions of the same procurement group (table package_vec, EmbeddingGemma, embedded in 30 s; also a refresh step) by vector similarity plus shared rare words, merged by rank fusion; /assess returns up to 5 (similarPackages) with country, method, USD value, tender-to-award days and a re-bid mark, shown in Assess; among the closest 15, contracts with a known award time come first (only ~1 in 5 has one) — a82deaf — hand-checked top 5: roads 5/5, medical equipment 5/5, supervision consultant for early warning ~3/5 (DRM specialists mixed in); live after the ordering change: roads and consultant queries each show 5 contracts with known days (69–493, 4–543); no description returns none; zero prices shown as unknown; 84 tests pass (3 new)
- [x] Multi-step retrieval (no measured gain yet): with fewer than MIN_EVIDENCE (3, on the Settings page; 0 = off) evidence passages, the answer LLM rewrites the question into up to 3 queries in the reports' vocabulary, results are merged by rank fusion and checked again, the larger evidence set is kept, and a caveat names the queries — d9502ef — full evaluation unchanged (15/15 answered, 53/55 supported, 5/5 unanswerable refused, median 23.4 s): it fires on thin-evidence questions (paraphrased question, blockchain and tungsten traps) and keeps traps refused, but rescued nothing; for "Why did firms stop showing up to bid?" the rewrites were good ("no responsive bids", "low bidder participation") and the limit was the decision-model evidence gate, which scored the found passages 0.04–0.41 and kept 1; 81 tests pass (2 new)
- [x] Amendment evidence from ICRs and an /assess flag: ICR passages reporting contract amendments, variations or extensions (advice and amended laws excluded), 11 of 121 projects; flag "Contract amendments in past projects: at least N of M" with the overall figure and a quoted example, "not evidence of absence" otherwise. Re-bid and amendment evidence now share one module (evidence.py, table project_evidence); rebid.py keeps its interface; a level of "high" needs at least 2 projects — 1711dff — all 20 amendment matches read by hand (15 reports, 4 advice, 1 the 2024 amendment of a Contracts and Tenders Act); the filters exclude exactly those 5; re-bid evidence unchanged after the refactor (35/33/19 reports, 26 projects); live: Lebanon both flags with example, Kenya "no evidence"; old project_rebid table dropped after checking nothing used it; 79 tests pass (3 new)
- [x] Amendment probability from notice versions — investigated, NOT buildable from this data: "Notice Version No" exists only on Contract Award notices (8,090; 1,377 at version >= 1, none on tender notices); the API returns only the latest version, so earlier versions are missing (only 133 packages have a version 0 and a later one); within one reference, different-version notices are mostly separate contracts (464 pairs: price differs in 91%, published the same day at the median); no award notice text says why it was revised ("amendment", "variation", "corrigendum": 0 of 1,377 revised, 2 of 6,713 originals). A version-based label would measure re-publication, not amendment — no code; replaced by the ICR-based item in Improvements
- [x] Re-bidding evidence per project and an /assess flag: ICR passages reporting a re-tender (keyword pattern, advice-to-avoid excluded) plus "-N" notice references → table project_rebid, 26 of 121 projects (ICR 19, references 11, overlap 4); flag "Re-tendering in past projects: at least N of M" per country with the overall figure, the measured cost (re-tendered packages: median 384 days to award vs 108, from the data at startup) and a quoted example; countries without evidence get "not evidence of absence" — bd31e7d — all 35 keyword passages read by hand: 33 report a re-tender, the 2 excluded recommend reducing it (the filter excludes exactly those); every flagged report has a genuine passage; an LLM step was not needed; recall is low (ICRs mention re-bidding for 4 of 11 suffix-evidenced projects), hence lower-bound wording; live: Bangladesh "at least 3 of 5" (high), Kenya "no evidence"; 76 tests pass (3 new)
- [x] Precedents picked by the answer LLM: one call per shortlist returns the useful passages; the decision model is no longer used for precedents; without an LLM, or on an unusable reply, retrieval order is kept — 9f10832 — 34 candidates for 3 packages labelled by hand before scoring (eval/precedent_labels.json, 13 useful): Saluki precision 0.77, recall 0.77, accuracy 0.82; Laya precision 0.29, worse than keeping everything (0.38); live: 9 of 12 precedents shown are useful (was ~6 of 15 before any check), 14–16 s per assessment; 73 tests pass (3 new, incl. that the decision model is not consulted)
- [x] Precedent relevance check (partial gain): CORRECTION 2026-10-25: the "net gain" below was judged from three output lists; against hand labels the decision model's precision was 0.29, below keeping everything (0.38), so this check made precedents worse and was replaced by the entry above. the decision model is asked whether each candidate is a lesson that would help plan the package (type, method, country, sector, description); rejected passages are not retried in the wider search, and the caveat says how many were set aside — 8c83439 — hand-judged on 3 packages: useful precedents ~6/15 before, ~7–9/15 after; Kenya's disbursement and indicator tables removed; but inconsistent: Pakistan kept two irrelevant passages, Indonesia dropped its best one (probe: relevant 0.37 vs irrelevant 0.66/0.77, and an alternative question scored all three 0.82–0.95, so no threshold or wording separates them); a test caught a double count (rejected passage judged again in the wider search); 72 tests pass (2 new)
- [x] Contract value as a feature: award prices converted to USD with World Bank yearly rates (PA.NUS.FCRF; table fx, 59 of 60 currencies; old SLL/STD units scaled after their 1,000:1 redenominations), log10 value added to the models (80% of training packages have one); at prediction the planner's estimate, or the typical value for the group and method when none is given (left missing it read as "small contract": 78 days and 5% for Kenya CW/RFB, now 99 days and 12% with a note) — 312aff6 — CV with vs without value: typical-days MAE 79.4 vs 82.0, >180 Brier 0.152 vs 0.156; converted values compared with USD-priced awards per currency, outliers traced in notice text (SLL redenomination fixed; KZT/GEL large and MZN small contracts genuine); live: Kenya CW/RFB $150k 79 days 4%, $25M 115 days 27%; found and fixed a crash when no estimate is given; 70 tests pass (4 new)
- [x] Re-bid evidence from reference suffixes: "-N" means a re-tender, not a lot (X and X-N near-identical descriptions; X-N later in 28 of 30 pairs, median 104 days); package.rebid_evidence marks 38 originals (successor_reference 28, award_under_suffix 10); re-bid packages took a median 341–384 days to award vs 108 overall. Not used as a re-bid rate or risk model: positive-only, ~12 of 98 projects use the convention, 13 pairs from one project — 045bfb2 — pairs, timing and project spread measured on the full notice table; 10 X/X-N description pairs read by hand; labelled packages unchanged (1,178); 66 tests pass
- [x] Recover missing awards (partly): awards filed under a tender's reference plus "-N" (the bidding round; one award reads "Vandhoo-3rd Tender") are linked to their tender when safe, marked `award_relinked`; 10 packages, +9 labelled (1,169 → 1,178). The 107 award notices without a date cannot be recovered: their text has no date ("Contract Signature Date | null"), and the notice publication date is not a usable stand-in (it trails the award by a median 92 days, p90 843) — 52dc022 — 8 of 8 sampled links read by hand are the same contract; relinked packages take a median 384 days (up to 1,512) vs 108 overall, so the previous metrics were flattering: retrained, typical-days MAE 82.0 vs baseline 84.5, >180 Brier 0.156 vs 0.168 (both still used), p90 model no longer beats its baseline and is switched off by the 2% rule; Kenya CW/RFB benchmark 195/113 → 198/116, test and mock data updated
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


### Done

- [x] Two-step passage tagging: the answer LLM is asked (1) does the passage describe a problem that happened in the project, (2) if so which kind, for the 3,154 passages the decision-model tagger marks as a possible problem (table chunk_problem, also a refresh step); precedents in Assess that describe one are marked "describes a past problem" — cd64254 — 60 passages labelled by hand first (19 problems): problem precision/recall decision model one step 0.44/0.79, decision model two steps 0.52/0.74, answer LLM two steps 0.94/0.79 (prefiltered 0.93/0.68), one combined question 0.91/0.53; kind right on 10/10 named problems (decision model 8, 6). Full run: 3,153 passages in 2.6 h, 1,378 problems, 1 failed reply retried next run. Hand check of 30 results: problem/no-problem right on 29, but the kind right on only 8 of 13 judgeable ("funding or payment delays" overused), so only the problem/no-problem call is shown; live Bangladesh CW/RFB: all 5 precedents marked; 98 tests pass (3 new)
- [x] Risk flags carry their evidence: each /assess flag has an evidence list (up to 5) shown under it in Assess: the timeline flags list the comparable packages over the threshold from the same set the statistic used (asked country first, slowest first) linked to their award notices; the governance flag links the CPIA indicator page; re-bid and amendment flags list one completion-report passage (linked PDF) or re-tender reference per project, matching "at least N of M"; model flags have none (they rest on the model; the detail gives its test) — 404ad37 — notice link format checked in Chrome (OP00203369 page shows the same project and bid reference; a made-up ID also returns HTTP 200, so the status code alone proves nothing); CPIA link shows Bangladesh 2.5 for 2025 as in the item; live Bangladesh CW/RFB: rebid "at least 3 of 5" with 3 projects, amendment "1 of 5" with 1, timeline flags 5 packages each; Kenya shows other countries' packages because none of Kenya's exceeds 180 days; evidence list rendered and links checked in the web app; tsc and eslint clean; 95 tests pass (2 new)
- [x] Answer writer refuses despite evidence — investigated, the refusals are correct; no code change: for "Why did firms stop showing up to bid?" the 3 kept passages are about bids priced above benchmarks (not about firms not bidding), and for "How did supervision consultants perform?" 4 of 5 are about World Bank supervision; the answer model replied {"sentences": []} for both, which is the rule it is given. A retry with the rephrased second search when the writer finds nothing was measured and rejected: still no answer for the first, and for the second 2 of 4 sentences were about Bank supervision, not consultants. A corpus search shows relevant passages exist (a tender that "received no bids", "limited bidder participation and repeated rounds of rebidding"), so the gap is retrieval for everyday wording (new Module 2 item)
- [x] Answer relevance check (q86 trap fixed by a narrower rule): no second search when the answer LLM gate kept no passage on the first pass — 523375c — the trap passed only through the second search (first-pass gate kept 0, 3 of 3 runs; the rephrased search found an "HSIP" metering passage, kept 2 of 2 runs). Two broader checks were measured and rejected: a stricter gate prompt ("a passage about a different kind of project does not count") still kept the passage 2 of 2 runs; a check after writing ("which sentences answer the question?") over all 289 sentences of the 100-question run rejected 29, about 18 of them good answers (e.g. a contract "terminated due to the contractor's non-performance" for q64), and kept one of the two q86 sentences. First-pass gate on 100 questions + a paraphrase: every answerable question kept at least 1 passage (min 1, 7 kept fewer than 3), 18 of 20 unanswerable kept none (stadium and casino kept 2, both refused later). Live: high-speed rail refused with no second search; weak engineering designs (thin first pass) still searched again and answered; 92 tests pass (1 new)
- [x] Larger evaluation set: 100 questions (80 answerable, 20 unanswerable), 80 added and written by hand, not generated: 55 on procurement topics each found in at least 5 reports by a corpus count (price escalation, exchange rates, insecurity, CERC, UN agencies, HEIS, e-procurement, misprocurement, PPP, STEP, prior review, audits, disputes ...), 10 in everyday wording unlike the reports' ("Why was the money not spent on time?"), 10 in-domain traps on topics with 0 matching passages (high-speed rail, stadiums, Mars rover ...) and 5 off-topic controls; 1,016 new pairs judged — 9c4e0d7 — second hand check of 30 new relevance judgments: 26/30 agree (3 lenient, 1 strict; eval/judge_check.md). Full run on 100: hybrid P@5 0.70 (0.77 on the first 20), recall@10 0.78, gate precision 0.90, 78/80 answered, sentences supported 275/287 (answer model) and 283/287 (independent judge), 19/20 unanswerable refused, median 33.8 s. Failures found and added to Improvements: q86 trap answered with a faithful but irrelevant sentence; q59 and q76 refused despite gate evidence
- [x] Evidence gate quality: the answer LLM now picks the evidence passages in one call (LLM_GATE=1, on the Settings page; the decision model judges per passage when it is 0 or the call fails); the decision model still checks each answer sentence — 99d34a0 — measured before switching: Laya per-passage scores on all 232 judged pairs AUC 0.77 (at 0.5: precision 0.78, recall 0.82; vs the 30 hand labels 0.70/0.82); Qwen3-VL-8B as gate too lenient (recall 1.00, precision 0.80, hand 0.71); one-call LLM gate on the 12 retrieved passages of all 20 questions + a paraphrase: precision 0.95 vs 0.82 (recall 0.91 vs 0.86) against the judged labels (same model, so possibly favourable), 0.89 vs 0.62 against hand labels, passages kept for traps 0 of 5 vs 2 of 5 (Laya kept 6 for the Paris Olympics trap), the paraphrase kept 3 vs 1. Full evaluation after the switch: gate precision 0.77 -> 0.92, 15/15 answered, sentences supported 53/56 (answer model) and 54/56 (independent judge), 5/5 traps refused; cost: median 18 -> 33 s per question. Live: Kenya "What caused procurement delays" now answered (was refused); "Why did firms stop showing up to bid?" now has evidence but the answer model writes no sentence from it, so that limit is now in answer writing; 91 tests pass (1 new; two tests no longer depend on which models are configured)
- [x] Independent faithfulness judge: the evaluation checks every answer sentence against its cited passages with the answer model and with a second model (PROCINTEL_JUDGE_*; Qwen3-VL-8B-Instruct, text-only, port 8083, already on disk), reports both, and writes both verdicts with the cited passages to eval/faithfulness.jsonl — 17f81f5 — two full runs: 53/55 supported by both judges, agreement 55/55 in each (15/15 answered, 5/5 refused); probe: both reject an invented "three times due to corruption" and accept a paraphrase; hand check of both rejections and 8 random acceptances against the full passages: 10/10 verdicts correct (the 2 rejections misdate a slowdown and attribute construction delays to consultant selection; one acceptance has a loose causal link). So self-grading was not inflating the figure; the remaining limit is the question set size; 90 tests pass (1 new)
- [x] Procurement-specific conflicts: the procurement rating each ICR states in its fiduciary compliance section is parsed (closing rating from closing/completion sentences, else the only rating stated; lowest rating; MS/MU/HS/HU abbreviations read; capacity or arrangement assessments and counts over a programme's sub-projects excluded) into table procurement_check (also a refresh step); when procurement fell to Moderately Unsatisfactory or worse while the outcome (or, without one, the last ISR implementation rating) is satisfactory, a cited report gets the caveat "Procurement weaker than the overall rating" with the quoted sentence — 8f9e607 — 52 of 120 reports state a procurement rating, 6 flagged; every parsed sentence of the first draft read by hand (fixes: abbreviations, "improved from MU to MS", "through closing", a sub-project count, a capacity assessment), all 6 flagged sentences read in full and correct; live /ask on Rwanda feeder roads (P126498) shows the caveat with its quote, Kenya /assess shows none; 89 tests pass (5 new)
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

- [x] Smaller answer model (user request, 2026-10-25) — measured, Saluki stays the default; Qwen3-8B Q4_K_M is documented in .env.example as the faster option — f2de720 — downloaded with the user's approval (Qwen/Qwen3-8B-GGUF, 5.03 GB, sha256 and size match the Hugging Face listing). 12 questions on a quiet machine, median per answered question: Saluki 27B IQ2 ~38 s, Qwen3-VL-8B Q8 ~20 s, Qwen3-8B Q4 ~15 s, all 8/9 answered and 3/3 traps refused (CORRECTION: an earlier spot check said the Q8 was no faster; it ran while the tagging job used the machine, and the "same file size, same speed" explanation was wrong). Full 100-question run with Qwen3-8B Q4 answering and Saluki as independent judge (eval/report-qwen3-8b-q4.md): 79/80 answered, 275/290 sentences supported by the independent judge (Saluki answering: 282/285 by its independent judge), 19/20 traps refused (fighter-jet trap answered from Haiti passages), evidence gate precision 0.81 vs 0.90, median 14.8 s vs 34 s. The rejected sentences read by hand are mostly real errors (a road answer citing healthcare plans, a recommendation stated as fact, a wrong re-tender cause), and the decision-model sentence check passed them; Q4 also rated 289/290 of its own sentences supported. The two independent judges differ (Qwen3-VL for Saluki, Saluki for Q4), so the faithfulness gap is indicative
- [x] Configuration page (Settings): 15 backend settings grouped by area (answer/decision model and endpoints, LLM temperature and max tokens, retrieval k, fusion pool and constant, evidence passages and thresholds, precedent filter), applied to the next request through GET/PUT /config, validated all-or-nothing, optional save to data/config.json loaded at startup; embedding model and dimensions read-only (stored vectors belong to one model); API keys never listed — 1a3834f — 3 API tests (live apply + save, 7 invalid bodies applying nothing, no keys exposed); in Chrome: search k = 0 refused in place, 8 applied and confirmed on the backend without a saved file, reverted to 12
- [x] Evaluation report with user feedback and history: eval/report.md shows retrieval metrics now vs the previous run, answer metrics (re-run, or the last measured ones dated), and feedback counts per page with the most flagged citations; every run appends headline metrics to eval/history.jsonl; refresh ends with the quick evaluation (retrieval + feedback), `evaluate run` does the full one — a51f373 — refresh --skip-fetch: evaluation step 10.5 s, retrieval metrics identical to the committed full run (P@5 0.64/0.77, R@10 0.62/0.76); 2 report tests (with history and feedback, and with neither)
- [x] `python -m procintel.refresh`: re-fetches listings (projects, notices, ICR list) while keeping cached ICR texts and existing ICRs, then model tables → chunks → embeddings and tags (incremental) → rating check → prediction models; table refresh_log records added/changed/removed documents, new notices, project status changes, passages embedded/tagged, model metrics before and after, and per-step times — d33fe0d — --skip-fetch run: 0 changes, 0 re-embedded, 0 re-tagged, 5.8 s; live run: 304 listings re-fetched from the network (cache files rewritten), 0 texts re-downloaded, no changes since the 2026-10-23 ingest, 2.9 min; change detection covered by 2 unit tests
- [x] Feedback capture: every /ask and /assess response logged with a responseId; POST /feedback (useful / not_useful / bad_citation naming a shown citation, optional comment); "Was this useful?" bar and "flag citation" on answers and assessments; separate data/feedback.duckdb so the server never blocks the build commands — 9d6aa0d — 4 API tests (unknown response, citation not shown, missing citation, bad rating all 400); in Chrome: flagged a citation and sent "not useful" with a comment, both rows stored against the logged response, no console errors
- [x] Embeddings and tags re-run only for new or changed passages (text hash per model) — a36f209, d19a6e8 — re-run embeds 0
- [x] All models swappable by configuration; documented in .env.example — b8d7c0e — backend starts from it
- [x] Idle model servers release memory: --sleep-idle-seconds 300 on all three llama-servers — 911f037 — Saluki wired memory 12.6 → 3.6 GB after idle, 1.4 s to wake

---

## Proposal (the written deliverable)

### Queue

_(empty)_

### Done

- [x] MVP write-up per module (docs/proposal.md): what is built, design choices, measured evidence and gaps for each of the four modules, the conflicting-evidence method, and a proposed three-phase pilot with KPIs and how each is computed — 7f1ee44 — every figure cross-checked against TRACKER Done entries, commit messages and eval/report.md; pilot sizes and durations marked as proposals
- [x] README: what it is, quick look on mock data, Python and model setup (llama.cpp commands, idle sleep), data build steps with measured times, refresh, run, architecture, evaluation summary, limitations, layout; requirements.txt corrected (dropped unused networkx and rank-bm25, marked anthropic optional, added bm25s, PyStemmer, joblib and httpx that are imported) plus requirements.lock — 8722ed8 — every command checked to have an entry point; a fresh venv from requirements.txt alone passes all 66 tests

### Improvements

- [ ] Full technical proposal document per the brief's four modules, after the MVP write-up (added 2026-10-24, by me)
