# Notes

Running notes on how the system works, written as questions came up. Each note says what it rests on: **verified** (read in
the code or run on 2026-10-29 unless dated otherwise) or **reading** (my interpretation of names and docs, not checked line
by line). New notes go at the end; correct a note in place and say so.

## 1. Entities and tables (2026-10-29)

**Two different things are called "entity" here.**

**a) Entity types the pipeline watches: 6** (verified, `src/procintel/pipeline/entities.py`). Each is one kind of record read
from a World Bank source. It has a key (what makes one item unique), the fields whose change counts, how often to look, and a
reader for the source and one for the database.

| Entity type | Source | Table | Key |
|---|---|---|---|
| Notice | procurement notices API | `notices` | `notice_id` |
| Project | projects API | `projects` | `project_id` |
| ContractAward | Finances One contract awards dataset | `contract_award` | built by `contract_key` |
| Indicator | indicators API (CPIA and WGI) | `cpia` and `wgi` | built by `indicator_key` |
| Document | documents API, completion reports | `documents` (not supervision types) | `doc_id` |
| SupervisionDoc | documents API, ISRs and restructuring papers | `documents` (supervision types) | `doc_id` |

The names are ours and describe the thing. They are not the APIs' names. `docs/event-pipeline-design.md` also lists Passage and
Feedback as entity types, but the code registers six.

**New kinds of data.** More items of an existing kind (more ICRs or notices) need no new entity. A new kind (for example
contracts from a client's system) needs one more entity type: a table, a key, the fingerprint fields and a reader. The design
doc says so. The pipeline does not invent entity types from incoming files: an uploaded document that is not one of our kinds
is kept and linked, not added to any table.

**b) Tables: 49 in the five DuckDB databases** (verified, listed from `data/*.duckdb`).

| Group | Tables | Count |
|---|---|---|
| Loaded straight from the World Bank | `notices`, `projects`, `documents`, `contract_award`, `cpia`, `wgi`, `fx` | 7 |
| Derived by our pipeline from those | `country`, `project`, `notice_m`, `package`, `supplier`, `award_supplier`, `document_m`, `document_project`, `firm`, `supplier_entity`, `chunk`, `chunk_tag`, `chunk_problem`, `chunk_vec`, `package_vec`, `package_icr_link`, `project_evidence`, `rating_check`, `procurement_check` | 19 |
| Left over from the semantic-chunking experiment | `chunk__semantic`, `chunk_parent__semantic`, `chunk_vec__semantic`, `text_vec` | 4 |
| App bookkeeping | `refresh_log`, `shadow` (main database); pipeline: `action_run`, `alert`, `detection`, `entity_state`, `event_log`, `firing`, `upload`, `watch`; auth: `failed_logins`, `sessions`, `users`; feedback: `demoted_citations`, `feedback`, `response_log`, `review_items`; jobs: `jobs`, `meta` | 19 |

- Six of the seven raw tables are watched as entity types. `fx` is loaded from the indicators API but not watched.
- The derived tables are rebuilt from the raw ones with `CREATE OR REPLACE TABLE ... AS SELECT` (`ingestion/tables.py`,
  `entities.py`, `chunk.py`). `package` groups notices into procurement packages and is the central one.
- Reading (not checked builder by builder): the grouping of `rating_check`, `procurement_check`, `project_evidence` and
  `package_icr_link` as derived comes from their names and the modules that write them.

**How the tables relate.** Through shared ID columns (`project_id`, `notice_id`, `doc_id`, `bid_ref`). The Postgres copy
has no primary keys, foreign keys, unique constraints or indexes in our schemas (verified 2026-10-28: 0 of each; the 62
primary keys a first count showed belong to Postgres's own `pg_catalog`). The pipeline keeps the tables consistent; the
database does not enforce it. No check for orphan rows has been run.

**Which database the app reads.** DuckDB files in `data/`. `PROCINTEL_DB_URL` is not set, so the Postgres containers hold a
copy for browsing in pgAdmin (http://127.0.0.1:5050) that goes stale as the pipeline writes to DuckDB. Setting the variable
makes the same code run on Postgres.

**How rules and events use the entities.** Detection compares each item's fingerprint with the last one and logs
`<Entity>.added`, `.changed` or `.removed` in `pipeline.event_log`. Rules turn those events into actions (`rules.py`,
`actions.py`). Derived events (`Passages.changed`, `Package.award_changed`, `Data.updated`, `Upload.ingested`) are reported
by actions and the upload step, not by detection.

## 2. The five databases (2026-10-29)

The app's data is in **five DuckDB files** in `data/` (verified: listed from `data/*.duckdb`; paths in `core/paths.py`). The
code keeps them apart because DuckDB lets only one process write to a file at a time.

| File | Tables | What it holds |
|---|---|---|
| `procintel.duckdb` | 32 | the main data: raw and derived tables, passages with vectors and tags, the experiment leftovers, `refresh_log` and `shadow` |
| `pipeline.duckdb` | 8 | change detection: entity state, event log, rule firings, actions run, alerts, watches, uploads |
| `auth.duckdb` | 3 | users, sessions, failed logins |
| `feedback.duckdb` | 4 | the response log, feedback, review items, demoted citations |
| `jobs.duckdb` | 2 | the job queue and its metadata |

32 + 8 + 3 + 4 + 2 = 49 tables. In Postgres (`core/db.py`) the same five become five schemas of one database: `public`,
`pipeline`, `auth`, `feedback`, `jobs`. Searched only `data/`; any `.duckdb` file elsewhere is not counted.

## 3. Events, rules and actions (2026-10-29)

Verified from `pipeline/entities.py`, `rules.py`, `actions.py`; the event list also matches the Rules page.

**Events: 24 types**
- **3 kinds applied to each of the 6 entities** (Notice, Project, ContractAward, Indicator, Document, SupervisionDoc), which makes 18:
  `added` (a new item), `changed` (a watched field of the item changed), `removed` (the item is gone from the source).
- **6 derived events**, reported by actions and the upload step, not by detection: `Package.award_changed`, `Data.updated`,
  `Documents.changed`, `Passages.changed`, `Upload.ingested`, `Upload.removed`.

**How an entity event is raised.** Detection reads a source and compares each item's fingerprint, built from the entity's
watched fields, with the last one. Other fields make no event.

**Rules: 11.** A rule lists events (`on`), the actions to run (`do`) and, for `.changed` events, an optional list of fields
(`fields`). One event can match several rules; an action asked for by several rules or events runs once per batch.

**Actions: 15**, run in this order:

| # | Action | What it does | Default trigger |
|---|---|---|---|
| 1 | `ingest_documents` | fetch and write new or changed reports (and new projects' records and notices) | Document, SupervisionDoc added or changed |
| 2 | `apply_notices` | write new and changed notices | Notice added or changed |
| 3 | `apply_projects` | write changed project records | Project added or changed, only if status, sector, closing date, board approval or commitment changed |
| 4 | `apply_contracts` | write new and changed contract awards | ContractAward added, changed, removed |
| 5 | `apply_indicators` | write CPIA and WGI values | Indicator added, changed, removed |
| 6 | `rebuild_tables` | rebuild packages, suppliers and links | Notice, Document, SupervisionDoc, Project events; upload events |
| 7 | `fill_award_dates` | fill award dates from contract signing dates | ContractAward events |
| 8 | `rebuild_firms` | merge supplier ids of the same firm | Notice, Document, SupervisionDoc events; upload events |
| 9 | `chunk_documents` | cut report texts into passages | Document, SupervisionDoc, upload events; `Documents.changed` |
| 10 | `index_passages` | embed and tag new or changed passages | `Passages.changed` |
| 11 | `document_checks` | rating checks, re-bid and amendment evidence from the passages | `Passages.changed` |
| 12 | `sector_links` | rebuild contract-to-report links by sector and time | Project events (as above) |
| 13 | `drift_check` | queue a prediction drift check (at most every 6 hours) | `Package.award_changed` |
| 14 | `watch_alerts` | alert planners whose watch-list covers the changes | Notice added or changed, Document added, `Upload.ingested`, `Package.award_changed` |
| 15 | `reload_backend` | reload the backend's data | `Data.updated` |

**Which entity triggers what (default rules).** Notice: 2, 6, 8, 14. Project: 3, 6, 12. ContractAward: 4, 7. Indicator: 5.
Document and SupervisionDoc: 1, 6, 8, 9 (Document added also 14).

## 4. The three timeline models (2026-10-29)

Verified from `src/procintel/prediction/predict.py` and `ingestion/refresh.py`; the latest numbers are from the 2026-10-26
retrain (`data/models/history.jsonl`). What each output means in plain words is my wording of standard quantile and
probability definitions, not text from the code.

**What they predict.** One thing: days from tender to contract award. Three models, all scikit-learn gradient-boosted trees
(`HistGradientBoosting`), differ in how they describe that time. Each also has a project variant (adds years since approval
and log commitment, used when the project is known), so six fitted models in all.

| Model | Output | Plain meaning | Example |
|---|---|---|---|
| `days_p50` | days | Of similar past tenders, half were awarded within this many days and half took longer. The date to plan around. | 112 days |
| `days_p90` | days | Of similar past tenders, 90% were awarded within this many days; the slowest tenth took longer. The cautious date. | 240 days |
| `over_180` | probability | The chance the tender takes more than 180 days. A low number is good. The 180 is fixed in the code (`LONG_DAYS`). | 20% means about 1 in 5 similar tenders took longer than 180 days |

"Similar" is not a lookup. The model learned from past tenders how the inputs relate to days and applies that to the new
package; the output is its estimate of where the line falls, not a count of matching tenders. A p50 is a plan, not a promise:
it is exceeded about half the time, which is why the p90 and the over-180 risk sit beside it.

**Inputs.** Procurement group, method, region, sector, six CPIA scores as of the tender year, and log contract value. The
tender year itself is not an input.

**Training.**
- Rows: tenders in the `package` table with at least 540 days of follow-up (`MIN_FOLLOWUP_DAYS`), so late awards are not
  missing. 1,336 packages from 94 projects in the latest run.
- Method: many small trees built one after another, each fitted to the errors the earlier ones still make (150 trees,
  learning rate 0.05, at most 7 leaves per tree, at least 50 tenders per leaf, L2 5.0). The p50 and p90 models use quantile
  loss at 0.5 and 0.9; `over_180` is a classifier.
- The trees come from the data, not from a person or a language model. People choose the inputs, the training rows, the
  settings and the acceptance rule.
- Each retrain starts from scratch on all data and overwrites `data/models/timeline.joblib`; the metrics are appended to
  `history.jsonl`. The tree settings are in code only.

**Does it keep learning?** No. It is retrained, not updated live. Triggers: the weekly refresh step "prediction models"
(`predict.main`), and the `drift_check` job, which retrains if new packages reach max(20, 5% of the training set) or the
error on new packages exceeds 1.2 times the cross-validated error (the three drift values are on the Settings page). The
first model needs one run of `python -m procintel.prediction.predict`; without a saved model, `/assess` uses the benchmark
statistics only.

**Automatic evaluation.** Every retrain scores itself with 5-fold cross-validation grouped by project (a project is never on
both sides of the split), repeated 5 times, against a baseline of the plain median. A model is used in `/assess` only if it
beats the baseline by at least 2% (`MIN_GAIN`). Latest: median error 82.5 days against a baseline of 84.9, project variant
80.8; `days_p90` did not qualify and is not used. The drift check tests on later-awarded packages and is shown under "Drift
checks" on the Evaluation page.
