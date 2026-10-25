"""Re-bidding evidence per project (procintel.prediction.evidence, kind "rebid"), from two independent sources.

- ICR text: passages that report a re-tender in the project ("re-bid", "retendering", "re-advertised", "relaunched
  tender", "no responsive bids", "failed bidding" ...). Checked by hand on all 35 matching passages (2026-10-25): 33
  report a re-tender in that project, 2 recommend reducing re-tendering; every one of the 19 reports matched has at
  least one genuine report.
- Notice references: packages re-tendered or awarded under the original reference plus "-N" (package.rebid_evidence).

Both miss cases: ICRs summarise (only 4 of the 11 projects with suffix evidence mention re-bidding in their ICR), and
only some agencies number re-tenders. So the evidence is a lower bound ("at least N of M projects"), never a rate.

    python -m procintel.prediction.rebid        # builds the "rebid" rows of table project_evidence
"""
from __future__ import annotations

from pathlib import Path

import duckdb

from procintel.prediction import evidence

DB_PATH = evidence.DB_PATH
PATTERN = evidence.REBID.pattern


def reports(text: str) -> bool:
    """True when a passage reports a re-tender (not when it only advises against one)."""
    return evidence.reports(evidence.REBID, text)


def build(db_path: Path = DB_PATH) -> None:
    evidence.build([evidence.REBID], db_path)


def by_country(con: duckdb.DuckDBPyConnection) -> dict[str, dict]:
    """country -> {"projects": M, "with_rebid": N, "example": (project_id, quote) from an ICR if any}."""
    return {cc: {"projects": v["projects"], "with_rebid": v["with_event"], "example": v["example"]}
            for cc, v in evidence.by_country(con, "rebid").items()}


def cost(con: duckdb.DuckDBPyConnection) -> tuple[float, float] | None:
    """(median tender-to-award days of re-tendered packages, median of all packages), or None without evidence."""
    r = con.execute("""SELECT median(tender_to_award_days) FILTER (WHERE rebid_evidence IS NOT NULL), median(tender_to_award_days)
                       FROM package WHERE tender_to_award_days IS NOT NULL""").fetchone()
    return (r[0], r[1]) if r[0] is not None else None


if __name__ == "__main__":
    build()
