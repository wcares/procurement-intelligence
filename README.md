# Procurement Intelligence (prototype)

Evidence-backed decision support for procurement planners, built on World Bank open data. It links three kinds of
records on `project_id`:

- **structured:** projects and procurement notices (tenders, awards, prices, suppliers), CPIA governance scores;
- **semi-structured:** notice texts parsed into dates, methods, prices and suppliers;
- **unstructured:** Implementation Completion and Results Reports (ICRs), cleaned and split into citable passages.

Two pages use them:

- **Assess a package:** a typical tender-to-award time and range for comparable packages, risk flags from statistics
  and from a trained model, the country's CPIA scores, and quoted lessons from past ICRs.
- **Ask the evidence:** free-text questions answered only from ICR passages. Every sentence cites its source, a
  decision model checks each sentence against the passage it cites, and questions the reports do not cover are
  refused instead of guessed.

Feedback buttons on both pages, a refresh command, an evaluation report and a settings page close the loop. Work
status per module of the brief: [docs/TRACKER.md](docs/TRACKER.md). Data model: [docs/data-model.md](docs/data-model.md).
Latest evaluation: [eval/report.md](eval/report.md).

## Quick look without models (web app on mock data)

```bash
cd web && npm install && npm run dev        # http://localhost:3100
```

The web app ships with an in-app mock API built from real exported data (`web/src/mocks/data.json`), so both pages work
without Python or models. Responses are labelled MOCK.

## Full setup

Developed on macOS (Apple M5, 32 GB), Python 3.13.17, Node 24.

### 1. Python environment

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt          # or requirements.lock for the exact versions used
PYTHONPATH=src .venv/bin/python -m pytest -q tests  # 66 tests
```

### 2. Models (optional, all local, swappable)

Every model is reached through configuration (`.env.example`), so any OpenAI-compatible server or hosted API works.
The reference setup is [llama.cpp](https://github.com/ggml-org/llama.cpp) (`brew install llama.cpp`) with three
servers on localhost:

| port | model | used for |
|---|---|---|
| 8080 | Underdog-Saluki-27B-1.0 IQ2 ([ConwayResearch/Underdog-Saluki-27B-1.0](https://huggingface.co/ConwayResearch/Underdog-Saluki-27B-1.0), 7.9 GB) | writing cited answers |
| 8081 | EmbeddingGemma 2 Q8_0 ([ggml-org/embeddinggemma-2-GGUF](https://huggingface.co/ggml-org/embeddinggemma-2-GGUF), 0.3 GB) | semantic search |
| 8082 | Laya Q8_0 ([ggml-org/Laya-GGUF](https://huggingface.co/ggml-org/Laya-GGUF), 0.45 GB) | evidence gate, sentence fact-check, quote choice, passage tags |

The exact `llama-server` command for each is in `.env.example`. Each runs with `--sleep-idle-seconds 300`, which
releases the model's memory after 5 idle minutes (measured on Saluki: wired memory 12.6 → 3.6 GB; 1.4 s to wake).

```bash
cp .env.example .env            # edit model paths/endpoints if yours differ
set -a; . ./.env; set +a        # load into the shell before the commands below
```

Without any model configured, search is keyword-only (BM25) and answers are quoted sentences checked by word overlap.

### 3. Build the data

Run from the repository root with `PYTHONPATH=src`. Times are from runs on the machine above.

| step | command | what it does | time |
|---|---|---|---|
| ingest | `.venv/bin/python -m procintel.ingest --icrs 120` | 120 newest ICRs, their projects, up to 300 notices per project (World Bank APIs, cached in `data/cache/http`) | network-bound |
| model | `.venv/bin/python -m procintel.model` | clean tables: project, package (tender-to-award days), notice, supplier, CPIA | < 1 s after ingest |
| chunk | `.venv/bin/python -m procintel.chunk` | ICR text → 18,992 passages with section and paragraph anchors; page furniture and footnotes removed | 2 s |
| embed | `.venv/bin/python -m procintel.embed` | passage vectors (needs the embedding server); only new or changed passages | 326 s full |
| tag | `.venv/bin/python -m procintel.tag` | passage tags from the decision model; only new or changed passages | 653 s full |
| ratings | `.venv/bin/python -m procintel.ratings` | ICR outcome vs last ISR rating, conflicts for caveats | < 1 s |
| predict | `.venv/bin/python -m procintel.predict` | trains and cross-validates the award-time models (`data/models/timeline.joblib`) | seconds |
| evaluate | `.venv/bin/python -m procintel.evaluate run` | evaluation report (answers every test question; ~10 min with the 27B model) | see report |

After the first build, one command keeps everything current:

```bash
.venv/bin/python -m procintel.refresh           # fresh listings, then rebuild what changed, then evaluation
.venv/bin/python -m procintel.refresh --skip-fetch
```

It logs every run (documents and notices added, passages embedded and tagged, model metrics before and after) to the
`refresh_log` table. Measured: 2.9 min with fetching, 6 s without. Add
`--reload-url http://127.0.0.1:8000/admin/reload` to have a running backend load the new data when it finishes.

**Background jobs.** The backend keeps a job queue (`procintel.jobs`, file `data/jobs.duckdb`) and runs it only
after 5 minutes without requests (tunable on the Settings page), pausing between steps when someone uses the app. It
queues a prediction drift check daily (retrains when enough packages were labelled since training, or the model does
worse on them than in cross-validation) and a World Bank refresh weekly; both reload the backend when they change
data. The Settings page lists the jobs and can queue one. `PROCINTEL_JOBS=0` turns the worker off;
`scripts/refresh.sh` runs a refresh by hand.

### 4. Run

```bash
PYTHONPATH=src .venv/bin/uvicorn procintel.server:app --host 127.0.0.1 --port 8000
cd web && NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev    # http://localhost:3100
```

The backend serves `/options`, `/assess`, `/ask`, `/feedback` and `/config` (`/health` for checks). It listens on
127.0.0.1 only, and its CORS rules let browsers call it only from the web app's origin; `/config` can change model
endpoints, so do not expose it beyond localhost. After a refresh, `POST /admin/reload` (accepted only from this
machine) loads the new data without a restart; requests keep using the old data until the new one is ready.

## How it works

```
World Bank APIs ──► ingest ──► DuckDB raw tables ──► model ──► project · package · notice · supplier · cpia
                                     │
                                     └─► ICR text ──► chunk ──► passages ──► embed (EmbeddingGemma 2) ─┐
                                                                    └──────► tag (Laya)               │
question ──► BM25 + vector search, merged by rank ◄──────────────────────────────────────────────────────┘
         ──► evidence gate (Laya) ──► answer written by Saluki, or quoted sentences
         ──► each sentence fact-checked against its citation (Laya) ──► answer with citations and caveats
package  ──► statistics of comparable packages + gradient-boosted trees ──► timeline and risk flags
```

- **Retrieval:** BM25 (LlamaIndex) and vector search over the same filtered passages, merged by reciprocal rank fusion.
- **Grounding:** a passage counts as evidence only if the decision model judges it relevant; a generated sentence is
  kept only if its cited passage supports it; without models, word-overlap rules do the same jobs.
- **Prediction:** scikit-learn HistGradientBoosting trained from scratch on 1,145 packages; each model is shown only
  where project-grouped cross-validation beats the historical median by at least 2%. Only tenders with 18 months of
  follow-up are used, because recent tenders are awarded only if fast (see `src/procintel/predict.py`).
- **Conflicting evidence:** an ICR outcome rating that disagrees with the project's last supervision (ISR) rating is
  stated as a caveat with both ratings and dates; the ICR is treated as the later verdict, never averaged.

## Evaluation (summary of [eval/report.md](eval/report.md))

20 questions: 15 answerable, 2 off-topic controls, 3 procurement-sounding questions the reports do not cover.

| | |
|---|---|
| precision@5, BM25 → hybrid | 0.64 → 0.77 |
| recall@10 (pooled, upper bound), BM25 → hybrid | 0.62 → 0.76 |
| answerable questions answered | 15/15 |
| answer sentences supported by their citations | 53/55 |
| unanswerable questions refused | 5/5 |
| relevance judge vs hand labels | 28/30 agree |

Limits: the faithfulness judge is the same model that writes the answers, recall is measured against a pooled set,
and 20 questions is a small set.

## Known limitations

- 120 ICRs and their projects, not the whole World Bank portfolio.
- Report text comes from the World Bank's text exports, so tables arrive flattened.
- Award-time predictions still miss slow tenders that were never awarded (a survival model is the planned fix).
- Passage problem-type tags were too unreliable to show (about 7 of 18 right on a hand check); only the
  "not a lesson" filter is used.
- Contract awards cover contracts signed since FY2020 only (Finances One DS00005); WGI is shown, not used by the model.

Details and what comes next: [docs/TRACKER.md](docs/TRACKER.md).

## Layout

```
src/procintel/   ingest, model, chunk, embed, tag, ratings, predict, retrieve, answer, assess, decide, llm,
                 feedback, config, evaluate, refresh, server (FastAPI), wb_client, stats, export_mock
tests/           pytest suite
web/             Next.js app (Assess, Ask, Settings) with an in-app mock API
eval/            questions, relevance judgments, hand check, report, history
docs/            data model, work tracker
data/            DuckDB files, HTTP cache, trained model (not in git)
```
