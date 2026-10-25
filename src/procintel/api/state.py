"""Everything the API derives from the database, built once and swapped in whole on reload."""
from __future__ import annotations

import threading
import time
from pathlib import Path

from procintel.answering.answer import idf
from procintel.answering.retrieve import DB_PATH, Retriever
from procintel.core import db
from procintel.ingestion import wgi
from procintel.learning import feedback_review
from procintel.prediction import evidence, predict, rebid, stats
from procintel.prediction.flag_evidence import FlagEvidence
from procintel.prediction.similar import Similar


class State:
    """Everything derived from the database, loaded once at startup."""

    def __init__(self, db_path: Path):
        con = db.connect(db_path, read_only=True)
        self.options = stats.options(con)
        self.bench = stats.benchmarks(con)
        self.governance = stats.governance(con)
        self.wgi = wgi.latest(con)
        self.rebid = rebid.by_country(con)
        self.rebid_cost = rebid.cost(con)
        self.amendments = evidence.by_country(con, "amendment")
        self.similar = Similar(db_path)
        self.flag_evidence = FlagEvidence(db_path)
        con.close()
        self.retriever = Retriever(db_path)
        self.retriever.demoted = feedback_review.load_demoted()  # flagged citations moved to the end of search results
        idf(self.retriever)  # term weights for picking answer sentences
        self.timeline_model = predict.load()  # None until `python -m procintel.prediction.predict` has been run
        self.region = {c["code"]: c["region"] for c in self.options["countries"]}
        self.country_name = {c["code"]: c["name"] for c in self.options["countries"]}


_state: State | None = None
reload_lock = threading.Lock()


def state(db_path: Path = DB_PATH) -> State:
    global _state
    if _state is None:
        with reload_lock:
            if _state is None:
                _state = State(db_path)
    return _state


def reload_state(db_path: Path = DB_PATH) -> float:
    """Rebuild everything derived from the database and swap it in; seconds taken. Requests keep using the old state
    while the new one builds. Settings (procintel.api.config) live in the modules, so they are kept."""
    global _state
    t = time.time()
    with reload_lock:
        _state = State(db_path)
    return time.time() - t
