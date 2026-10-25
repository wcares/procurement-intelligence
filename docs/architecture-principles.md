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
| Data location | `data/procintel.duckdb` repeated in about 22 modules; feedback and jobs files likewise | one `PROCINTEL_DATA_DIR` (or database URL) setting read by a single module |
| Storage engine | DuckDB SQL in each module | a storage layer per entity (repositories) so Postgres can replace DuckDB for a multi-user pilot |
| Vector search | vectors in a DuckDB table, searched in memory (fine for 18,000 passages) | a vector index interface: in-memory (today), DuckDB vss, pgvector or a vector database by configuration |
| Data sources | World Bank URLs and calls in code (`wb_client`, `contract_awards`, `wgi`) | connectors with configuration (mode, interval, cursor), per the event design |
| Prompts | strings in code (evidence check, answer writer, rephrasing, tagging, precedent picking) | prompt files with versions, editable on the Settings page, evaluated before use |
| Pipeline order | fixed sequence in `refresh.py` | actions and rules registries (event design) |
| UI components | page code; no component library yet | shadcn/ui, Recharts, ECharts, React Flow, TanStack Table (UI design); visuals driven by API data and registered chart types |

## Order of the clean-up

Done as part of the queued work, not as a separate rewrite: the data-location setting first (small, touches every
module), then prompts as files, then the storage and vector interfaces when the event pipeline's state store is built,
and connectors with the event pipeline's step 1.
