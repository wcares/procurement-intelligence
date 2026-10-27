# Web app (UI): design and request log

Status: built; updated 2026-10-27. This file collects what the web app shows and how; each request is logged in
section 6 and was queued in docs/TRACKER.md (section "UI (web app)"). Follows docs/architecture-principles.md: every
part replaceable by configuration or registration, nothing hardcoded. Backend pieces it depends on are designed in
docs/event-pipeline-design.md.

The app now has these pages (role needed): **Overview** (home dashboard), **Assess a package**, **Ask the evidence**,
**Plan a project**, **Insights** and **Documents** (planner); **Evaluation** (reviewer); **Pipeline** (connectors, event log, rules, upload)
and **Settings** (admin). The first version had only Assess, Ask and Settings, with text, cards and one timeline bar.

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

**Built (2026-10-25)** as the home page: headline numbers, a worst-first ranking (TanStack Table) by country, sector
family or method for six measures (median award time, awards over 6 months, re-tendering, amendments, procurement rated
below satisfactory, problem passages per report), award time by tender year with the years after the 18-month
follow-up shaded incomplete (Recharts), country x method heat map (ECharts), problem mix with its reliability note,
and the records behind any row or cell. Data from `procintel.insights.dashboard`, `/dashboard` endpoints (planner role).
Not yet: governance as a ranking measure, problems by closing year as a chart, the "what changed recently" block
(event log), mock data for the in-app mock.

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

## 2.4 Alerts, recommendations and trends next to the query (user, 2026-10-25)

On the page where the planner asks or assesses, a compact side panel with three parts, each linking to a full
**Insights** page with the details:

| part | shows (compact) | full Insights page |
|---|---|---|
| **Alerts** | new risks on what the planner watches: e.g. "2 new re-tenders in Kenyan civil works this month", "award times for RFB in your region rose 20%" | all alerts with their evidence, filters, watch-list management |
| **Recommendations** | 2-3 actions for the package being planned, each with its source: method or packaging options, mitigations taken in past projects for the flagged risks | every recommendation with the precedents and passages behind it; accept / dismiss (feeds back like a rating) |
| **Trends** | one small chart relevant to the query (e.g. award time for this method and region over years) | the dashboard's trend views, pre-filtered |

- Alerts come from the event pipeline: a rule on new events (re-tender evidence, award times, ratings) matched against
  a planner's **watch-list** (countries, sectors, methods, projects). Shown in the app only for now (user,
  2026-10-25); email or other notifications can be added later as a setting.
- Recommendations are generated only from retrieved precedents and statistics, with citations, the same way answers
  are; with no supporting evidence, none is shown.

**Built (2026-10-26):** watch-lists and alerts (`procintel.insights.alerts`, pipeline rule `watch-alerts`),
recommendations (`procintel.insights.recommendations`: faster methods from the statistics, mitigations from cited
answers), the award-time trend for a package's scope, the Insights page and the compact panel on Assess and Ask.

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

**Built (2026-10-25):** Connectors, Event log and Rules as an admin Pipeline area (`/pipeline`, three tabs); Settings links
to it. Upload (2026-10-25): add files, follow each through extraction, classification, linking and, for a completion
report about a tracked project, into the evidence.

## 3b. Evaluation page (admins)

No page yet: results go to eval/report.md, eval/history.jsonl and logs; only the Settings "Check search quality"
compares before and after a change. The page:

| block | shows | from |
|---|---|---|
| Quality over time | search precision and recall, evidence-check precision, answers given, traps refused, sentences supported (answer model and independent judge), median time; each run marked with the refresh, retrain or promotion before it | eval/history.jsonl |
| Comparisons | live vs shadow, model A vs B: each measure side by side, Promote / Discard | shadow evaluations, comparison runs (e.g. eval/report-qwen3-8b-q4.md) |
| Prediction models | cross-validated error vs baseline per retrain, drift-check results, error on newly awarded packages | model bundle, jobs |
| Labelling queue | random judge labels to confirm (agreement shown, 54/60 today); refused and not-useful real questions to turn into evaluation questions; judge disagreements | judgments, feedback review |
| Run | queue a full evaluation or a quick search-quality check (background priority) | job queue |

## 3c. Sign-in and roles

One app, one sign-in; the role decides what a person sees and can do (user, 2026-10-25: "one for end clients and one for
admin users who run the pipeline ... exactly the role based").

| role | who | can |
|---|---|---|
| **Planner** | World Bank project teams and procurement specialists, borrower implementing agencies | home dashboard, Assess, Ask, interactive visuals; rate answers, flag citations; upload documents to analyse (their own, on the Documents page; a completion report joins the shared evidence once an admin adds it; built 2026-10-26) |
| **Admin** | the team running the platform | the admin pages only: Pipeline (connectors, rules, event log, upload), Evaluation, Settings (background jobs, users, feedback review, promotions). The planner pages are not shown to an admin account and send it to Pipeline (user, 2026-10-27: "admin shouldn't show what client side sees"); the backend still lets an admin call the planner endpoints |
| **Reviewer** | domain experts | everything a planner can, plus the Evaluation page to read (quality over time, comparisons, models), the labelling queue and feedback review; no runs, promotions, prompts, pipeline or settings (built 2026-10-26) |

- **Login for now: username and password** (user, 2026-10-25). Passwords stored only as salted hashes; an admin creates
  accounts and assigns roles; the first admin comes from an environment setting; sessions in a secure, HTTP-only
  cookie; repeated failed logins are slowed down. Single sign-on (OpenID Connect, e.g. Microsoft Entra ID or Okta) can be
  added later as a setting (docs/architecture-principles.md).
- **Roles enforced in the backend**, not only hidden in the UI: every admin endpoint checks the caller's role. Today the
  settings, jobs and reload endpoints are open to anyone who can reach the server (only reload and queueing jobs are
  limited to this machine).
- **Identity on every logged response** (a pseudonymous id), which the pilot's adoption KPIs need
  (docs/pilot-plan.md, phase 0).
- **Navigation by role**: planners see the planner app; admins also see an Admin area.

**Built (2026-10-25):** `procintel.auth` (scrypt hashes, sessions stored as token hashes in an HTTP-only cookie, five
failed attempts per name or address in 15 minutes lock further tries, first admin from the environment, accounts on
the Settings page or `python -m procintel.auth`), `PROCINTEL_AUTH` = local | off, roles per endpoint group in the
backend (`procintel.api.routes.ROUTERS`), a pseudonymous user id on every logged response and feedback, a sign-in
page, navigation by role and a Users panel.

## 4. Visual language

- One colour scale for risk everywhere: red high, amber medium, grey low; green only for "better than typical". The
  scale is a set of theme tokens so it reads in light and dark.
- Model estimates are always marked as such (shape or label), separate from historical statistics.
- Every chart element links to its records; no number without a source.
- Charts are drawn from the same API the pages use, with established component libraries, not hand-drawn.

### Components (decided 2026-10-25, user: "use better react components which are built for this, no need to
reinvent")

The app is Next.js 16, React 19 and Tailwind CSS 4, with no component library yet.

| need | library |
|---|---|
| UI building blocks (cards, tabs, selects, dialogs, tooltips, sheets) | shadcn/ui (Tailwind-based, components copied into the project) |
| Standard dashboard charts (bar, line, area, small multiples) | shadcn/ui charts, built on Recharts |
| Stage timeline / Gantt with risk markers, heat map, zoom and brush over years | Apache ECharts via echarts-for-react |
| Answer map (clickable graph of causes and sources) | React Flow (@xyflow/react) |
| Ranking tables (sort, filter, drill down) | TanStack Table (shadcn data table pattern) |

Checked 2026-10-25 (npm registry metadata and a web search):

| package | version | React peer range | note |
|---|---|---|---|
| recharts | 3.10.1 | 16.8 – 19 | default open-source choice for React dashboards in current comparisons; SVG |
| echarts | 6.1.0 | — (framework-free) | recommended for large and interactive data (heat maps, timelines, zoom) |
| echarts-for-react | 3.0.6 | >= 16 | React 19 not stated explicitly; Next.js needs `transpilePackages` for echarts and zrender |
| @xyflow/react | 12.12.0 | >= 17 | |
| @tanstack/react-table | 9.3.1 | >= 18 | |

shadcn/ui states support for Tailwind v4 and React 19. Not confirmed by any source: Recharts 3 inside shadcn's chart
component; tested by rendering one chart before the dashboard relies on it. If echarts-for-react misbehaves on React 19,
ECharts is used directly through a small hook (ECharts has no React dependency). Dedicated Gantt components were
considered: SVAR React Gantt supports React 19 but is GPLv3 and aimed at editable project plans, so it is only a
fallback; the read-only stage timeline is built with ECharts.

Before installing: list exact names and versions for the user's approval (installing downloads packages from npm).

**Installed (2026-10-25):** recharts 3.10.1, @tanstack/react-table 9.3.1 (v9 API: `useTable`, `tableFeatures`),
echarts 6.1.0 used directly through a small hook (`web/src/lib/use-echarts.ts`), not echarts-for-react.
**shadcn/ui (2026-10-26):** the app's own `--muted` / `--accent(-soft)` tokens were renamed `--ink-muted` /
`--brand(-soft)` (838c42d, a pure rename), and shadcn's theme names (`--primary`, `--muted-foreground`, `--accent`,
`--border`, `--ring`, ...) are mapped onto this palette in `globals.css`, so a shadcn component takes the app's colours
in light and dark mode. `components.json` (new-york style, `@/components/ui`), `cn` in `src/lib/utils.ts`, Button added
with the shadcn CLI 4.21.4 (radix-ui 1.7.0, class-variance-authority 0.7.1, clsx 2.1.1, tailwind-merge 3.7.0); further
components come with `npx shadcn@4.21.4 add <name>` (check the import of `cn` afterwards: the CLI wrote `from "cn"` and
installed an unrelated npm package of that name, removed). The CLI did not touch `globals.css`.

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
| U2 | 2026-10-25 | Home dashboard with graphs: most risky things that happened in the past, worst to best, trends over time | done (25111f2); follow-ups in the tracker |
| U3 | 2026-10-25 | Interactive visual for query results besides the text report: risks at each tender stage, with colours, clickable | done (c0c02bf stage timeline, 840bec5 answer map, 08f5182 similar contracts and lessons) |
| U4 | 2026-10-25 | Pipeline pages: connectors, event log, rules (with the state and event system) | done (ba23530 connectors, event log, rules; d058319 upload) |
| U5 | 2026-10-25 | Predictions shown on the timeline and in interactive charts; use existing React component libraries (shadcn/ui or better), no reinventing | libraries in use (ECharts, Recharts, React Flow, TanStack Table; shadcn/ui waits for a token rename); the planned package's own estimate on the stage timeline: done (0864ff7) |
| U6 | 2026-10-25 | Evaluation page for admins: quality over time, comparisons with promote/discard, labelling queue | done (3f7bccf, 468a741) |
| U7 | 2026-10-25 | Two kinds of users, role based: planners (end clients) and admins who run the pipeline | done (84a1041) |
| U8 | 2026-10-25 | On the query page, a small section with alerts, recommendations and trends, linking to a full detail page | done (95091b0); follow-ups in the tracker |
| U10 | 2026-10-26 | Goal seeking: set a desired outcome for a package and see the set-ups that met it most often | done (affc866): "Set a goal" panel on Assess, shown after a package is assessed; target award time and maximum lots; ranked by the share of comparable packages that met it |
| U11 | 2026-10-27 | Plan a project: enter the packages of a new project, see a forecast for each, the project dates, bottleneck and a deadline check | done: page /plan; each package forecast with the existing assess endpoint and its own goal panel; project dates combine the forecasts in the order set by the user (dependencies are not learned from data); plan kept in the browser only |

## 7. Open questions

- One chart library instead of two: ECharts alone can do everything, at the cost of styling it to match shadcn/ui.
  (2026-10-26: still two; Recharts in two dashboard charts, ECharts for the rest.)
- Which measure ranks the dashboard by default (delay is the most complete today). (Delay is the default.)
- Whether the problem-mix chart waits for better problem kinds. (It shows, with the reliability caution: the kinds
  were right on 8 of 13 in a hand check.)
