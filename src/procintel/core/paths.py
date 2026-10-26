"""Where the data lives: one setting, read by every module.

PROCINTEL_DATA_DIR (default: <repo>/data) holds the main database, the feedback and job databases, saved settings,
trained models and the HTTP cache. In a container it points at a mounted volume. A module that needs a file takes
its path from here, never builds one from its own location.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # src/procintel/core/paths.py -> repo
DATA_DIR = Path(os.environ.get("PROCINTEL_DATA_DIR") or ROOT / "data").expanduser()

DB_PATH = DATA_DIR / "procintel.duckdb"          # projects, notices, documents, passages, vectors, tags, models' tables
FEEDBACK_DB = DATA_DIR / "feedback.duckdb"       # response log and feedback (its own file: one writer per DuckDB file)
JOBS_DB = DATA_DIR / "jobs.duckdb"               # job queue
PIPELINE_DB = DATA_DIR / "pipeline.duckdb"       # change detection: entity state, event log, rule firings
PIPELINE_RULES = DATA_DIR / "pipeline_rules.json"  # rules edited on the Settings page (absent: the defaults)
CONNECTORS_FILE = DATA_DIR / "connectors.json"   # connector settings edited on the Connectors page (absent: defaults)
AUTH_DB = DATA_DIR / "auth.duckdb"               # user accounts, sessions, failed logins
CONFIG_FILE = DATA_DIR / "config.json"           # settings saved from the Settings page
PROFILES_FILE = DATA_DIR / "config_profiles.json"
MODEL_DIR = DATA_DIR / "models"                  # trained prediction models
HTTP_CACHE = DATA_DIR / "cache" / "http"         # World Bank API responses
LOG_DIR = DATA_DIR / "logs"                      # logs of the refresh script
EVAL_DIR = ROOT / "eval"                         # evaluation questions, labels and reports (kept with the code)
