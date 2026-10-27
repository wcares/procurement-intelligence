# Pipeline overview: from any source to the planner's screen

Status as of 2026-10-27. This is the plain-text version of the pipeline diagram that used to live only as a Claude
page ("Procurement Intelligence Pipeline", 2026-10-25); the statuses are updated to what is built. The detailed
design is `docs/event-pipeline-design.md`, the deployment mapping is in `docs/proposal.md` §2.

Legend: **built** runs today; **partly** works for the World Bank sources and uploads only; **design** is described
but not built.

## The whole loop

```
 1 INGESTION            sources → connectors → intake → extract by format → classify → extract fields + link
 2 EVENT SYSTEM         state store → events → rules → job queue (idle time) → actions     (timers feed the queue)
 3 SERVING              data stores → backend API → web app → planners
 feedback               a planner's rating or flag re-enters the event system as Feedback.added
```

Row 1 turns whatever arrives into records and passages. Row 2 compares them with what is stored and runs only the jobs
the change needs; actions may emit further events (for example `Model.updated`). Row 3 serves the updated state; the
backend swaps in new data after a job, with no restart (about 3 seconds).

## Ingestion

| stage | status | what it does |
|---|---|---|
| Sources | partly | World Bank APIs: projects, procurement notices, completion reports (text exports), supervision reports (ISRs) and restructuring papers, CPIA, WGI, exchange rates, Finances One contract awards. Uploads (PDF, Word, text, HTML, Markdown). Not yet: watched folders, client systems, MCP servers, email |
| Connectors | built (poll, push) | Defined by configuration: mode, interval, on/off, saved from the Pipeline page. Poll asks each interval for what is new. Push is a webhook checked by an HMAC signature, with a daily poll as a safety net. Not built: subscribe mode (no source offers subscriptions yet) |
| Intake | built | Stores each item as received with its source and a fingerprint, so a duplicate is not processed twice. Emits `RawItem.added {format}` |
| Extract by format | built | JSON and notice text parsed into records; PDFs read per page; scanned pages read with OCR (Apple Vision, RapidOCR); report text cleaned and flattened tables detected. Emits `Document.extracted` |
| Classify content | built | Decides contract, completion report, supervision report, notice or amendment: the title phrase first, else the decision model at 60% or more, else a review list. Emits `Document.classified {type}` |
| Extract fields + link | built | Pulls the fields for the type and links them to the project, package or firm. Contracts match packages by reference (4,341 of 6,990); firm ids are merged into firms; sector and time links join packages to reports. Every value keeps a pointer to its page |

## Event system

| part | status | what it does |
|---|---|---|
| State store | built | Per tracked item (project, notice, document, passage, contract, indicator, feedback), its key and a fingerprint of the fields we care about. Comparing fingerprints is how changes are found |
| Events | built | Typed changes (`Notice.added`, `Document.changed`, `Project.changed[status]`, `Feedback.added`), logged, so "why did this prediction change?" has an answer |
| Rules | built | "When this event happens, run these actions." Defaults in code; the Settings page adds, edits, disables, dry-runs and resets them. Rules can only pick registered actions |
| Job queue | built | Runs jobs only after a few minutes without requests, pauses between steps when someone uses the app, survives restarts, retries on failure |
| Actions | built | Chunk, embed, tag, update packages, fill award dates, rebuild evidence and benchmarks, check drift, retrain, review feedback, reload. Scoped to the items that changed where possible |
| Timers | built | A drift check daily, a refresh weekly (now a reconciliation that catches anything a detector missed) |

## Serving

| part | status | what it does |
|---|---|---|
| Data stores | built | DuckDB (projects, packages, passages, vectors, tags, evidence, firms), the trained prediction models, separate files for pipeline state, jobs, users and feedback. Production mapping: Postgres, Qdrant, S3 or MinIO |
| Backend API | built | FastAPI; holds the search index and models in memory; serves assessments, goal seeking, answers, insights, settings, jobs and feedback review |
| Web app | built | Overview, Assess (with Set a goal), Plan a project, Ask, Insights, Documents, Pipeline, Evaluation, Settings |
| Planners | built | Read answers with citations, rate them, flag a wrong citation. A passage flagged on two separate answers drops to the end of search results |

## One upload, end to end

A signed contract arrives as a 40-page PDF.

1. An officer uploads it. The upload connector stores it with its source and fingerprint (`RawItem.added`).
2. Extraction reads the pages, using OCR for scanned ones, and keeps each page's text and tables (`Document.extracted`).
3. Classification recognises a contract (`Document.classified`).
4. Field extraction finds the contract reference, supplier, amount and signing date, each with its page.
5. Linking matches the reference to a package; the rule for that event queues `fill_award_dates` for that one package.
6. Rules queue a benchmark rebuild and a drift check, merged with other awards from the same batch.
7. The backend reloads; the next planner assessing similar works sees the updated benchmark, and the contract text is
   searchable with page citations.

## Inside a request

**Ask the evidence** (median 34 s): question with country and type filters → rephrase into report vocabulary (answer
model) → hybrid search (BM25 plus vectors) → evidence check, refusing if nothing supports an answer → write cited
sentences → fact-check each sentence (decision model) → answer with caveats.

**Assess a package**: package details → timeline (history plus gradient-boosted trees) → risk flags with their
evidence (notices, CPIA/WGI, reports) → precedents (lessons from past reports, same sector first) → similar contracts
by description → answer with caveats. **Plan a project** runs the same assessment for each package of a new project and lays the forecasts on one timeline with the likely bottleneck and a deadline check. **Set a goal** then works backwards from a target award time to the methods and
lot counts that met it most often, with the number of comparable packages behind each.

Both requests read only from stores the event system keeps current; neither waits for a background job.

## Deployment

The web app talks only to the API. The API answers requests, receives webhooks and queues work; the worker runs every
pipeline step, including the connector code that polls external sources. Local today: DuckDB files, the `data/`
folder and llama.cpp servers. Production, by configuration only: Postgres, Qdrant, object storage and model endpoints
by URL, in Docker containers (`compose.yaml`). Login is username and password with planner, reviewer and admin roles;
alerts are shown in the app.
