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
| Thresholds, retrieval sizes | module constants, most editable on the Settings page | expose the rest (drift-check limits, flattened-table rule, demotion threshold is done) |
| Data location | DONE (2026-10-25): `procintel.paths` reads `PROCINTEL_DATA_DIR` (default `<repo>/data`); the 25 modules that built `data/...` paths from their own location take them from there, and a test fails if one does again | a database URL replaces the file path when Postgres comes in |
| Storage engine | IN PROGRESS (2026-10-25): every connection goes through `procintel.db.connect`; `PROCINTEL_DB_URL` selects DuckDB files (default) or Postgres, where DuckDB's postgres extension runs the same SQL against Postgres tables (schemas public, feedback, jobs) | per-entity repositories later, where the SQL differs between engines |
| Vector search | vectors in a DuckDB table, searched in memory (fine for 18,000 passages) | a vector index interface: in-memory (today), DuckDB vss, pgvector or a vector database by configuration |
| Data sources | World Bank URLs and calls in code (`wb_client`, `contract_awards`, `wgi`) | connectors with configuration (mode, interval, cursor), per the event design |
| Prompts | strings in code (evidence check, answer writer, rephrasing, tagging, precedent picking) | prompt files with versions, editable on the Settings page, evaluated before use |
| Pipeline order | fixed sequence in `refresh.py` | actions and rules registries (event design) |
| UI components | page code; no component library yet | shadcn/ui, Recharts, ECharts, React Flow, TanStack Table (UI design); visuals driven by API data and registered chart types |

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
4. **Worker as its own process.** Today it is a thread in the api process.

Models in containers on a Mac run on the CPU only (Docker has no Apple GPU access), too slow for the 27B answer model;
Docker runs through Colima (installed 2026-10-25, the user's choice;
Docker 29.9.2, Compose 5.6.1; VM with 4 CPUs, 6 GB memory, 60 GB disk). Docker Model Runner belongs to Docker Desktop and is not used, so the models stay
on the host.

## Order of the clean-up

Done as part of the queued work, not as a separate rewrite: the data-location setting first (small, touches every
module), then prompts as files, then the storage and vector interfaces when the event pipeline's state store is built,
and connectors with the event pipeline's step 1.
