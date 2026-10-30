# Notes

Running notes on how the system works, written as questions came up. Each note says what it rests on: **verified** (read in
the code or run on 2026-10-29 unless dated otherwise) or **reading** (my interpretation of names and docs, not checked line
by line). New notes go at the end; correct a note in place and say so.

This file is the primary source. A copy for reading on a phone is the Claude Doc "Procurement Intelligence Notes"
(https://claude.ai/artifact/S4yGRS7s3ajLetZAAJrRQM); update this file first, then the doc.

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

## 5. From the World Bank sources to events: one worked path per kind (2026-10-30)

Five sources (checked in `ingestion/wb_client.py`, `ingestion/contract_awards.py`). Raw examples below were fetched live on
2026-10-30 (long fields cut); table rows and counts are read from `data/procintel.duckdb` the same day. Which fields are
watched and how often is from `pipeline/entities.py`. The mapping of source field names to our column names is read from
the examples side by side, not from every reader line.

**The chain, for every kind:** source API → raw item → entity type (key + watched fields) → raw table → derived tables →
detection compares fingerprints → event → rule → action.

### 1. Procurement notices → Notice → `notices`
`GET search.worldbank.org/api/v2/procnotices?format=json&rows=1`
```
{"id": "OP00477669", "notice_type": "Invitation for Prequalification", "noticedate": "29-Oct-2026",
 "project_id": "P509161", "project_name": "Fourth Energy Sector Project", "bid_reference_no": "MN-MOE-ESP4-1-CW-RFP",
 "bid_description": "Construction of Mandalgobi-Arvaikheer 220kV ... Transmission Line (287 km)",
 "procurement_group": "CW", "procurement_method_code": "RFP", "submission_deadline_date": "2026-12-11T00:00:00Z", ...}
```
Row in `notices` (12,152 rows): `notice_id OP00472266 | project_id P105680 | notice_type Contract Award | bid_ref
AR-UCOFI-280748-GO-RFB | proc_group GO | method_code RFB | award_date 2023-11-01 | price_currency USD | price_amount
953944.91 | suppliers [{"name": ..., "firm_id": 1131595}]`.
- **Key** `notice_id`. **Watched:** `notice_type`, `notice_version`, `notice_date`, `award_date`, `price_currency`,
  `price_amount`, `suppliers`. **Looked at:** every hour.
- **Derived:** `notice_m` (cleaned notices) → `package` (8,347 rows; one tender, its notices grouped by project and bid
  reference, with `tender_start`, `award_date`, `price_amount`, …) → `supplier`, `award_supplier`, `firm`.

### 2. Projects → Project → `projects`
`GET search.worldbank.org/api/v2/projects?format=json&rows=1&countrycode_exact=KE`
```
{"id": "P501648", "countryname": ["Republic of Kenya"], "lendinginstr": "Program-for-Results Financing",
 "project_name": "Kenya Secondary Education Equity and Quality Improvement Program", "totalcommamt": "540,000,000",
 "boardapprovaldate": "2024-10-17T00:00:00Z", "closingdate": "12/31/2029 12:00:00 AM", "status": "Active", ...}
```
Row in `projects` (153 rows): `project_id P105680 | name Matanza-Riachuelo Basin ... | country Argentine Republic |
country_code AR | region Latin America and Caribbean | status Active | commitment_usd 840000000.0 | board_approval
2009-06-08 | closing_date 2025-09-29 | sector Sanitation`.
- The source writes the amount as text with commas and the date in two formats; the reader turns them into numbers and
  dates. **Key** `project_id`. **Watched:** `status`, `closing_date`, `sector`, `commitment_usd`, `board_approval`.
  **Looked at:** hourly.
- **Derived:** `project`, `country`.

### 3. Documents → Document and SupervisionDoc → `documents`
`GET search.worldbank.org/api/v3/wds?format=json&rows=1&docty_exact=Implementation Completion and Results Report`
```
{"id": "40136409", "count": "Tonga", "docty": "Implementation Completion and Results Report",
 "docdt": "2026-10-30T04:00:00Z", "abstracts": {"cdata!": "Ratings of the Pacific Resilience Program for Tonga were ..."},
 "txturl": ".../text/...", "pdfurl": ".../pdf/..."}
```
Row in `documents` (364 rows: 122 ICRs, 145 ISRs, 97 restructuring papers): `doc_id 40130914 | project_id P169610 |
doc_type Implementation Completion and Results Report | doc_date 2026-10-01 | title ... | pdf_url | txt_url | text`.
- **One API, two entity types** (same fields, different reading): `Document` = completion reports (ICRs), the newest 120,
  newest first, **hourly**; `SupervisionDoc` = the newest ISRs and restructuring papers of each tracked project, **daily**.
  **Key** `doc_id`. **Watched:** `doc_type`, `doc_date`, `title`, `txt_url`.
- The report text is fetched from `txturl` and stored in `text`. **Derived:** `document_m`, `document_project`, then
  `chunk` (passages), `chunk_tag`, `chunk_vec`, `chunk_problem`, `rating_check`, `procurement_check`, `project_evidence`.

### 4. Finances One contract awards → ContractAward → `contract_award`
`GET datacatalogapi.worldbank.org/dexapps/fone/api/apiservice?datasetId=DS00005&resourceId=RS00005&type=json&top=1`
(296,096 rows in the whole dataset; we filter by our projects)
```
{"project_id": "P151416", "wb_contract_number": "1543858", "borrower_contract_reference_number": "UDP PPG-QCBS-2016-4-12",
 "contract_description": "Technical Supervision of construction in pilot Schools and Kindergartens",
 "contract_signing_date": "19-May-2022", "procurement_category": "Consultant Services",
 "procurement_method": "Quality And Cost-Based Selection", "supplier": "M/S. AIRES INGEGNERIA", "supplier_id": "316882",
 "supplier_country_code": "IT", "supplier_contract_amount_usd": 161538.89, "as_of_date": "30-Oct-2026", ...}
```
Row in `contract_award` (17,569 rows): `project_id P105680 | contract_ref AR-UCOFI-68647-CW-RFB | signing_date 2020-04-17 |
category Works | method Request for Bids | supplier ESUCO S.A. | supplier_id 23681 | amount_usd 11959434.07 |
wb_contract_number 1612096 | firm_id 23681`.
- **Key** `wb_contract_number|supplier_id`. **Watched:** `signing_date`, `amount_usd`, `supplier`, `contract_ref`.
  **Looked at:** daily.
- **Why it exists:** it carries the contract signing date, which notices often lack; `fill_award_dates` copies it into
  `package.award_date`.

### 5. Indicators → Indicator → `cpia` and `wgi` (and `fx`)
`GET api.worldbank.org/v2/country/KEN/indicator/IQ.CPA.TRAN.XQ?format=json`
```
{"indicator": {"id": "IQ.CPA.TRAN.XQ", "value": "CPIA transparency, accountability, and corruption in the public sector
 rating (1=low to 6=high)"}, "countryiso3code": "KEN", "date": "2025", "value": 3.5}
```
and for governance `.../indicator/GOV_WGI_GE.EST` → `{"date": "2025", "value": -0.0893561}` (government effectiveness,
about -2.5 to +2.5).
Rows: `cpia` (6,444): `country_code SN | year 2025 | indicator public_sector_mgmt_cluster | value 3.5`; `wgi` (11,104):
`country_code MA | year 2025 | indicator control_of_corruption | value -0.5027918`. Our names replace the codes
(`CPIA_CODES` in `ingestion/tables.py`, `WGI_CODES` in `ingestion/wgi.py`).
- **Key** source + country + year + indicator. **Watched:** `value`. **Looked at:** weekly (these move once a year).
- The same API also gives `fx` (3,468 rows, local currency per US dollar), loaded but **not watched**.
- **Used by:** the six CPIA scores are timeline-model inputs (note 4).

### Summary

| Source | Entity type | Key | Watched fields | Looked at | Raw table(s) |
|---|---|---|---|---|---|
| procnotices API | Notice | `notice_id` | type, version, dates, price, suppliers | hourly | `notices` |
| projects API | Project | `project_id` | status, closing date, sector, commitment, approval | hourly | `projects` |
| documents API (ICRs) | Document | `doc_id` | type, date, title, text URL | hourly | `documents` |
| documents API (ISRs, restructuring) | SupervisionDoc | `doc_id` | same | daily | `documents` |
| Finances One | ContractAward | contract no.+supplier | signing date, amount, supplier, ref | daily | `contract_award` |
| indicators API | Indicator | country+year+indicator | value | weekly | `cpia`, `wgi` |

### What happens on a change (example)
A planner's project P105680 gets a new notice: the hourly Notice check finds a `notice_id` not seen before → event
`Notice.added` in `pipeline.event_log` → default rules run `apply_notices` (write it to `notices`), `rebuild_tables`
(regroup into `package`), `rebuild_firms` and `watch_alerts` (alert anyone following that project or country). If the
package gets its award, `rebuild_tables` reports `Package.award_changed`, which queues `drift_check` and alerts again.
A new ICR does the same through `Document.added` → `ingest_documents` → `chunk_documents` → `Passages.changed` →
`index_passages` and `document_checks`. Events and actions are listed in note 3.

## 6. How a package is built (2026-10-30)

Verified from `ingestion/tables.py` (`notice_m`, `package`) and from `data/procintel.duckdb` on 2026-10-30.

**No API returns a package.** The notices API returns single notices (an invitation for bids, a contract award, ...). We group
them into one tender, a **package**, and `rebuild_tables` recreates the `package` table from `notices` each time. Nothing writes
to it directly.

**Grouping rule.** `package_id = project_id / bid_reference` (the bid reference is the notice's `bid_ref`). A notice with no
bid reference becomes a package of its own (its `notice_id` stands in). General Procurement Notices are left out of the package
(they announce a plan, not a tender).

**Re-linked awards.** Some awards are filed under the tender's reference plus "-N" (for example `...-CW-RFB-3`, likely a
bidding round). Such an award is linked to the base tender when the suffixed reference has no tender of its own, the base
reference is a tender, and that tender has no dated award yet. `notice_m.relinked` and `package.award_relinked` mark these
so the link can be audited.

**Columns (18).**

| Group | Columns |
|---|---|
| Identity | `package_id`, `project_id`, `proc_group`, `method_code`, `description` (longest seen), `n_notices` |
| Tender | `tender_start` (earliest pre-award notice), `first_stage` |
| Award | `award_date`, `max_notice_version`, `n_award_notices`, `contract_duration_days`, `price_currency`, `price_amount`, `award_relinked`, `award_from_contract` |
| Outcome | `tender_to_award_days` = days from `tender_start` to `award_date`, only when both exist and the award is not earlier |
| Re-bid | `rebid_evidence` (`award_under_suffix` or `successor_reference`) |

`award_from_contract` marks an award date copied from the Finances One signing date (`fill_award_dates`, note 3).

**Re-bid evidence is positive-only.** It marks the original package when its reference also exists as `X-N` in the same
project, or when an award was filed under `-N`. About 12 of 98 projects have it (13 pairs from one project), so a package without it
may still have been re-bid; it is not a re-bid rate.

**Example (one row).**
```
package_id  P126498/RW-RTDA-58025-CW-RFB      proc_group CW   method RFB   first_stage Invitation for Bids
n_notices 3   n_award_notices 2   tender_start 2018-09-25   award_date 2019-06-20   tender_to_award_days 268
price_amount 5,440,991,134 RWF   contract_duration_days 1260   rebid_evidence (none)
```

**Counts today.** 8,347 packages; 6,904 have an award date and 6,160 a price. A package with no award yet has no
`tender_to_award_days`, so it cannot train the timeline models.

**What uses it.**
- The timeline models (note 4) train on packages with at least 540 days of follow-up, with `tender_to_award_days` as the thing
  to predict; inputs come from the package (group, method, value) and its project (region, sector, CPIA scores).
- `/assess` and the benchmark statistics read it; `supplier` and `award_supplier` are built from the notices' suppliers by package.
- It is rebuilt by `rebuild_tables` on any Notice, Document, SupervisionDoc or Project event, or upload (note 3), and
  `Package.award_changed` (a package's award changed) queues the drift check.

## 7. Labels on a passage (2026-10-30)

Verified from `data/procintel.duckdb` and `ingestion/chunk.py`, `tag.py`, `problem_tag.py` on 2026-10-30. A passage (a row of `chunk`,
up to 1,400 characters) carries three separate labels.

| Label | Table | Values | Set by | Used for |
|---|---|---|---|---|
| Kind | `chunk.kind` | `text` (20,901), `table` (1,960) | the chunker's rules, no model | whether the passage is searched and answered from |
| Problem tag | `chunk_tag` | 7 options, each with a probability | Laya (decision model) | the "none of these" filter; the other six are not reliable enough to show as facts |
| Problem described? | `chunk_problem` | yes / no, plus a kind | Saluki, only on passages Laya did not mark "none of these" | a more precise tag for passages describing a problem |

**Laya's 7 options (passages):** none of these 17,484; funding or payment delays 1,139; weak specifications or design 912;
contractor performance or capacity 842; external shock (pandemic, disaster, conflict) 466; re-tendering or contract
termination 412; land acquisition or resettlement 73.

**Saluki's check:** 3,572 passages asked; 2,270 no problem, 1,301 problem (funding delays 420, weak specifications 384,
contractor performance 345, external shock 309, land acquisition 60, another kind 45, re-tendering 38; one with no kind).

**Tables in a passage.** The text export flattens a table's columns, so we do not rebuild tables. The chunker labels a block
`table` if most of its lines have wide column gaps, or if `is_flat_table` finds it mostly numbers (>= 30% of tokens; >= 20%
with no sentence boundary; or a "Table 4." caption with >= 10%). Tables of words stay `text` unless the column-gap layout
test catches them (not counted). Retrieval returns only `kind = text` by default (`retrieve.py`), and tagging, problem
tagging, evidence extraction and procurement ratings read only `text`. So a number-heavy table is stored but not used as
evidence, and a question answered only in a table gets the "no direct answer" fallback. Structured figures come from the
notices, Finances One and indicators instead. Known misses: data-sheet sector tables and short lists with under 20% numbers.

**Possible later improvement (not tested):** a layout parser such as Docling on the PDF (`pdfurl`) could recover table
rows and headers, so tables could be searched. It would need a new table-aware chunker, new citation anchors and a background
job, and should first be compared on a sample with our labelled questions.
