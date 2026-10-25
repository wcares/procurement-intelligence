# Web app (UI): design and request log

Status: proposed (2026-10-25). This file collects what the web app should show and how; each request is logged in
section 6 and queued in docs/TRACKER.md (section "UI (web app)"). Backend pieces it depends on are designed in
docs/event-pipeline-design.md.

Today the app has three pages: **Assess a package** (timeline, risk flags with evidence, precedents, similar
contracts), **Ask the evidence** (cited answer and caveats) and **Settings** (models, thresholds, profiles, background
jobs, feedback to review). Results are text, cards and one timeline bar.

## 1. Home dashboard: what went wrong in the past, worst to best

The new first page. A planner sees, before typing anything, where and when procurement went badly in past World Bank
projects, with every number linked to the records behind it.

| block | shows | data (exists today) |
|---|---|---|
| Headline numbers | projects, packages, reports covered; median tender-to-award; share over 6 months | `package`, `project`, `document_m` |
| **Riskiest first** ranking | countries, sectors or procurement methods ranked worst to best on a chosen measure; click a row to drill in | award times, share > 180 days (`package`); re-tendering and amendments (`project_evidence`); procurement rated below satisfactory (`procurement_check`); problem passages per project (`chunk_problem`) |
| Measure switcher | which measure ranks: delay, re-tendering, amendments, procurement rating, problems reported, governance (CPIA/WGI) | as above, `cpia`, `wgi` |
| **Trends over time** | median award time and share over 6 months by tender year; problems reported by project closing year | `package.tender_start`, `project.closing_date`, `chunk_problem` |
| Problem mix | how often each kind of problem is reported, by sector or region | `chunk_problem.kind` (see caution) |
| Heat map | country × procurement method, coloured by the chosen measure | `package` |
| What changed recently | new notices, reports and retrains (from the event log once built) | event log (event pipeline) |

Every chart element is clickable and opens the records it counts: packages with their notices, report passages with
citations.

**Cautions the dashboard must show, not hide:**

- *Recent years look fast*: only awarded tenders have an award time, and slow recent tenders are not awarded yet
  (median 258 days for 2019 tenders, 75 for 2025). Trend charts cut off at the 18-month follow-up line the model uses,
  or shade the years after it as incomplete.
- *Problem kinds are not reliable yet*: the problem/no-problem call is right 29 of 30 times by hand, the kind 8 of 13.
  The problem-mix chart carries that note, or waits until the kinds are improved.
- *Coverage*: 121 projects in 72 countries that have a completion report; rankings show the number of projects
  behind each row, and rows with very few are greyed.

## 2. Answers and assessments as interactive visuals

The current text answer and report stay. Next to them, a visual the user can work with.

### 2.1 Tender stage timeline (Assess, and Ask when the question is about a package)

A horizontal timeline of the stages of a tender, with risks placed on the stage where they bite:

```
 Plan ── Prepare documents ── Advertise ── (Prequalify) ── Bids & evaluation ── Award ── Contract ── Implementation
   ▲            ▲                                                  ▲                ▲                      ▲
 land,       weak specs /                                    re-tendering,     long award            payment delays,
 readiness   design (amber)                                  few bidders (red)  time (red)            contractor capacity
```

- **Durations**: each stage's typical length for comparable packages (from notice dates per stage), with the 90th
  percentile as a lighter band; the planned package's estimate overlaid.
- **Risks as markers**: colour = level (red high, amber medium, grey low), shape = basis (circle statistic, diamond
  model estimate). Hover shows the one-line flag; click opens its evidence (packages and notices, report passages with
  citations, the indicator).
- **Mapping problems to stages** (from the problem kinds and evidence): weak specifications or design → document
  preparation; re-tendering, few or no responsive bids → bidding; long award times → award; land and resettlement →
  planning and implementation; funding or payment delays, contractor performance → implementation; external shocks →
  across the timeline.

### 2.2 Answer map (Ask)

For a question such as "why were contracts re-tendered?": the answer's causes as nodes, sized by how many sources
support them, each linked to its passages; filter by country, sector or stage; click a node to read the quotes and open
the report page.

### 2.3 Precedents and similar contracts

Precedents placed on the same stage timeline and on a small map or list by country, with "same sector" and "describes
a past problem" markers; similar contracts as dots on a time axis (award time vs value), coloured by re-tendering.

## 3. Pipeline and settings pages

The Settings page grows into an operations area, using the event pipeline design:

| page | shows | depends on |
|---|---|---|
| Settings | models, thresholds, profiles, search-quality check (exists) | — |
| Background jobs | queue, running job, results (exists) | — |
| Feedback to review | flagged citations, refused and not-useful questions (exists) | — |
| **Connectors** | each source: mode (poll, push, subscribe, upload), interval or webhook, cursor, last success or error | event pipeline step 1 |
| **Event log** | events as they arrive, the rules they fired and the jobs they queued, filterable by type | event pipeline step 1 |
| **Rules** | rule list, editor (event, condition, actions), dry run, reset to defaults | event pipeline step 3 |
| **Upload** | add a file; follow it through extraction, classification and linking | event pipeline (intake) |

## 4. Visual language

- One colour scale for risk everywhere: red high, amber medium, grey low; green only for "better than typical". The
  scale is a set of theme tokens so it reads in light and dark.
- Model estimates are always marked as such (shape or label), separate from historical statistics.
- Every chart element links to its records; no number without a source.
- Charts are drawn from the same API the pages use; a chart library is chosen when building (to be decided, see
  open questions).

## 5. Backend work the UI needs

- Dashboard endpoints: rankings by measure and group, trends by year, heat map cells, each returning the record ids
  behind every number.
- Stage durations per comparable group (notice dates by stage, from `notice_m`).
- Stage mapping for risk flags and precedents (problem kind and evidence kind → stage).
- Answer map: the answer's sentences grouped by cause with their citations.
- Event log, connectors and rules endpoints (event pipeline).

## 6. Request log

Each UI request from the user, in the order asked. Status: queued, in progress, done (with the tracker entry).

| # | date | request | status |
|---|---|---|---|
| U1 | 2026-10-24 | Configuration dashboard for backend settings | done (Settings page, profiles, search-quality check) |
| U2 | 2026-10-25 | Home dashboard with graphs: most risky things that happened in the past, worst to best, trends over time | queued |
| U3 | 2026-10-25 | Interactive visual for query results besides the text report: risks at each tender stage, with colours, clickable | queued |
| U4 | 2026-10-25 | Pipeline pages: connectors, event log, rules (with the state and event system) | queued, after event pipeline step 1 |

## 7. Open questions

- Chart library (a light one such as a charting UMD build from the CDN allowlist, or hand-drawn SVG for the stage
  timeline) — decided when building U2.
- Which measure ranks the dashboard by default (delay is the most complete today).
- Whether the problem-mix chart waits for better problem kinds.
