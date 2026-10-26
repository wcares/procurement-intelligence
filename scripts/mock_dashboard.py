"""Write the web app's in-app mock of the home dashboard (web/src/mocks/dashboard.json) from the real data.

Run after a data refresh when the mock should follow: PYTHONPATH=src python scripts/mock_dashboard.py
Every ranking and heat map is captured; records only for the first rows of each ranking (the mock says so for others).
"""
from __future__ import annotations

import json
from pathlib import Path

from procintel.insights import dashboard, recent

OUT = Path(__file__).resolve().parent.parent / "web" / "src" / "mocks" / "dashboard.json"
RECORD_ROWS = 3      # drill-downs captured per ranking
RECORD_LIMIT = 25    # records kept per drill-down


def main() -> None:
    d = dashboard.Dashboard()
    out = {"dashboard": {"summary": d.summary(), "measures": dashboard.measures(), "groups": dashboard.GROUPS,
                         "trends": d.trends(), "problemMix": d.problem_mix(), "fewProjects": dashboard.FEW_PROJECTS},
           "rankings": {}, "heatmaps": {}, "records": {}, "recent": recent.recent()}
    for m in dashboard.MEASURES:
        if dashboard.MEASURES[m].level == "package":
            out["heatmaps"][m] = d.heatmap(m, 5)
        for g in dashboard.GROUPS:
            if not d.supports(m, g):
                continue
            r = d.ranking(m, g)
            out["rankings"][f"{m}|{g}"] = r
            for row in r["rows"][:RECORD_ROWS]:
                rec = d.records(g, row["key"], m, limit=RECORD_LIMIT)
                out["records"][f"{g}|{row['key']}|{m}"] = rec
    OUT.write_text(json.dumps(out, default=str))
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
