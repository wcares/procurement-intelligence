"""Event-driven updates (docs/event-pipeline-design.md): detectors compare each source with the stored state of its
entities and record typed events; rules map events to actions; actions run as one job per detection batch.

    entities.py   entity types: key, fingerprint fields, how to read the source and the current database
    store.py      entity state, event log and rule firings (data/pipeline.duckdb, schema "pipeline" in Postgres)
    rules.py      default rules and the coalesced plan of actions for a batch of events
    actions.py    the action registry: units of pipeline work, each today's build step for the affected data
    detect.py     the detection job and the batch job that runs a plan
"""
