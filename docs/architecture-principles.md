# Architecture principles: configurable, replaceable, scalable

Standing rule from the user (2026-10-25): the whole project, backend and UI, is designed so that models, databases,
connectors and pipeline steps can be replaced or added through configuration or registration, not by editing code,
and so that it scales beyond the prototype's data. docs/event-pipeline-design.md and docs/ui-design.md follow it.

## Principles

1. **Configuration, not code.** Anything an operator may want to change (a model, an endpoint, a threshold, a
   source, a schedule, a prompt) lives in settings, environment or a registry entry, editable on the Settings page
   where safe. Secrets stay in the environment and are never shown.
2. **Registries with interfaces.** Each replaceable part has one small interface and a registry of implementations:
   model providers, vector indexes, storage, connectors, extractors (by format), classifiers (by content), pipeline
   actions, chart and visual components. Adding one is a new entry, not a change to the code that uses it.
3. **One source per setting.** A value (the data location, a model name) is defined once and read everywhere from
   there, never repeated as a constant in many modules.
4. **Scale by design, measure before switching.** Interfaces allow a bigger implementation (Postgres instead of
   DuckDB, a vector database instead of in-memory search, more workers) without touching callers; the switch itself
   happens when measurements show the need.
5. **Every change is observable.** Configuration changes, events and jobs are logged, and evaluation runs before and
   after a change of model or setting (as the Settings page's search-quality check does).

## Where the code stands (audit, 2026-10-25)

| area | today | target |
|---|---|---|
| Models: answer, embedding, decision, judge | environment settings, editable on the Settings page (LiteLLM model strings, endpoints, options) | already meets the rule; add a provider registry only if a non-OpenAI-compatible model needs it |
| Thresholds, retrieval sizes | DONE (2026-10-25): drift-check limits, passage size limit and the flattened-table rule joined the Settings page (30 settings); the size limit is read when used, not bound at import | — |
| Data location | DONE (2026-10-25): `procintel.core.paths` reads `PROCINTEL_DATA_DIR` (default `<repo>/data`); the 25 modules that built `data/...` paths from their own location take them from there, and a test fails if one does again | a database URL replaces the file path when Postgres comes in |
| Storage engine | DONE for tables (2026-10-25; checked on Postgres 17 in a container: the same Assess and Ask answers as DuckDB, feedback and jobs written to Postgres, model tables rebuilt there; struct columns are stored as JSON because Postgres has no unnamed composite types): every connection goes through `procintel.core.db.connect`; `PROCINTEL_DB_URL` selects DuckDB files (default) or Postgres, where DuckDB's postgres extension runs the same SQL against Postgres tables (schemas public, feedback, jobs) | per-entity repositories later, where the SQL differs between engines |
| Vector search | DONE (2026-10-25): `procintel.core.vector_index` behind one interface; `PROCINTEL_VECTOR_URL` unset = in memory (default), a Qdrant URL = collections per kind and dimension, filled by `python -m procintel.core.vector_index sync` and by refresh; checked on Qdrant 1.19.2: identical rankings to memory on 25 evaluation questions (top 10 and whole pool) and identical similar packages, 2.5 ms vs 0.4 ms per query | pgvector as another implementation if wanted |
| Data sources | World Bank URLs and calls in code (`wb_client`, `contract_awards`, `wgi`) | connectors with configuration (mode, interval, cursor), per the event design |
| Prompts | DONE (2026-10-25): `procintel.core.prompts`; defaults in `src/procintel/prompts/*.txt` (identical to the former constants, checked), versions in the data folder, edited on the Settings page; a new version is a candidate until activated, and answering prompts are first compared with the active one on 20 sample questions (`procintel.learning.prompt_eval`, background job) | — |
| Pipeline order | fixed sequence in `refresh.py` | actions and rules registries (event design) |
| UI components | page code; no component library yet | shadcn/ui, Recharts, ECharts, React Flow, TanStack Table (UI design); visuals driven by API data and registered chart types |

## Code layout (user, 2026-10-25: "code is organized in better related modules ... in their own dirs")

`src/procintel/` has one package per area, matching the four modules of the assessment: `core` (data location,
database and vector-store access, model clients), `ingestion` (Module 1), `prediction` (Module 2), `answering`
(Module 3), `learning` (Module 4), plus `jobs`, `api` and `tools`. New code goes into the package of its area; a file
that grows past a few hundred lines or mixes concerns is split in the same change (behaviour-identical moves in their
own commit). Packages depend downwards: `api` and `jobs` on the module packages, those on `core`. The API is an app factory
(`api/app.py`) assembled from `state.py` (data loaded from the database), `background.py` (job mode), `access.py`
(administrative clients, a setting), `schemas.py` and `routes/` (one module per endpoint group, listed in
`routes/ROUTERS`): a new endpoint group is a new route module and one line there.

## Scale and deployment (user, 2026-10-25)

- **Local default, production by configuration.** Locally: DuckDB for tables and in-memory search over vectors stored in
  DuckDB. Production: Postgres for tables and a vector database (Qdrant, or Postgres with pgvector) for vectors, each
  plugged in behind the storage and vector-index interfaces by configuration.
- **Containers.** The backend (API and job worker), the web app and, in production, the databases each run as a Docker
  container; Docker Compose starts the whole system with one command, and every endpoint (models, databases,
  connectors) is an environment setting, so the same images connect to local or remote services.
- **Models.** On a Mac, containers cannot use the Apple GPU, so locally the model servers keep running on the host and
  containers reach them by URL; in production they run as GPU containers or a hosted endpoint, again by URL.

### Deployment topology

```
  browser (planners, admins)
        │
        ▼
  web (Next.js UI) ──HTTP──► api (FastAPI) ◄── webhooks from push sources
                                  │ queues work
                                  ▼
                            worker (job queue): connectors' polling and subscribing, extract, classify, chunk,
                                  │             embed, tag, retrain, feedback review, retention
        ┌──────────────┬──────────┴───────┬──────────────────┐
        ▼              ▼                  ▼                  ▼
    Postgres        Qdrant          object storage       model servers
  (tables, state,  (vectors)        (raw files,          (answer LLM, embeddings,
   events, jobs,                     uploads)             decision model)
   feedback, users)

  outside: World Bank APIs, client databases, MCP servers, document systems (reached by connectors in the worker)
```

| part | role | local now | production |
|---|---|---|---|
| web | the UI; talks only to the api | `next dev` | container |
| api | requests from the UI, webhooks, queueing | one process with the worker | container |
| worker | every pipeline step as jobs, including connector code | a thread in the api process | its own container (same image), scaled separately |
| tables and state | Postgres | DuckDB files | Postgres |
| vectors | Qdrant or pgvector | DuckDB table, in-memory search | Qdrant |
| raw files | object storage | `data/` folder | S3 or MinIO |
| models | answer, embedding, decision | llama.cpp on the host | GPU containers or hosted endpoints |
| sign-in | username and password, roles | — | same; single sign-on optional later |

### Demo target: the production stack on this Mac (user, 2026-10-25)

**Status: running (2026-10-25).** `compose.yaml` starts web, api, worker (scalable), Postgres and Qdrant, plus a
one-shot `seed` that on first start copies `./data` into Postgres (`--if-empty`, so later starts keep what was
written there), syncs the vectors into Qdrant and copies the trained model into the data volume. Checked: the stack's
Assess (Peru, Kenya) and Ask answers equal the local backend's, Settings queues jobs through the web container, and
`--scale worker=3` starts three workers; memory about 1.5 GB of the 6 GB VM. Object storage (MinIO / S3) is left out
until uploads exist: nothing reads or writes objects yet, so a container would only be decoration.

The whole system runs as one Docker Compose stack here, so the presentation shows the production pipeline itself;
scaling is more replicas of the same images plus managed services, with nothing rebuilt.

| service | image | scales by |
|---|---|---|
| web | Next.js production build (standalone output), multi-stage Dockerfile | replicas (no state) |
| api | backend image, `uvicorn` command | replicas (sessions in Postgres) |
| worker | same backend image, worker command | `docker compose up --scale worker=N`; jobs claimed from Postgres so no two workers take the same job |
| postgres · qdrant · minio | official images | managed services in production |
| models | llama-server on the host, reached at `host.docker.internal` | GPU containers or hosted endpoints in production, by URL |

Preconditions, in order:
1. **UI address at run time.** `NEXT_PUBLIC_API_BASE` is written into the build (web/src/lib/api/client.ts:19), tying an
   image to one backend. The browser instead calls the UI's own `/api/...`, and a Next.js server handler forwards to
   `API_URL` read per request; this also keeps the login cookie on one address.
2. **One data-location setting** (see the audit above).
3. **Postgres and Qdrant behind the storage and vector interfaces.** DuckDB allows one writing process, so separate api
   and worker containers, or several workers, cannot share it.
4. **Worker as its own process.** DONE (2026-10-25): `PROCINTEL_JOBS=external` in the api and
   `python -m procintel.jobs.worker` per worker (needs Postgres). Jobs are claimed in one Postgres statement
   (`FOR UPDATE SKIP LOCKED`, retried on a serialization conflict), each step writes a heartbeat so a starting worker
   only takes back jobs of stopped workers, the api records the last request time for the workers' idle wait, and a
   worker raises a data version that every api replica polls and reloads on. Checked: 4 processes claimed 40 jobs
   three times, each job exactly once; a separate worker ran a queued retrain and the api reloaded within 25 s.

Models in containers on a Mac run on the CPU only (Docker has no Apple GPU access), too slow for the 27B answer model;
Docker runs through Colima (installed 2026-10-25, the user's choice;
Docker 29.9.2, Compose 5.6.1; VM with 4 CPUs, 6 GB memory, 60 GB disk). Docker Model Runner belongs to Docker Desktop and is not used, so the models stay
on the host.

## Order of the clean-up

Done as part of the queued work, not as a separate rewrite: the data-location setting first (small, touches every
module), then prompts as files, then the storage and vector interfaces when the event pipeline's state store is built,
and connectors with the event pipeline's step 1.
