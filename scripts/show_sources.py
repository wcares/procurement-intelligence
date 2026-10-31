"""One small answer from each World Bank source, and what the pipeline makes of it.

    python scripts/show_sources.py [PROJECT_ID] [COUNTRY_ISO3]        (default P118518 KEN)

For each of the five sources: the request, one record trimmed to its first fields (long values cut), then the entity
type built from it (key, watched fields, how often it is looked at) and the raw table it lands in, with today's row
count from data/procintel.duckdb. The entity details are read from procintel.pipeline.entities, so they cannot drift
from the code. Needs network; changes nothing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from procintel.pipeline.entities import ENTITY_TYPES  # noqa: E402

SEARCH = "https://search.worldbank.org/api"
FONE = "https://datacatalogapi.worldbank.org/dexapps/fone/api/apiservice"
INDICATORS = "https://api.worldbank.org/v2"
DB = Path(__file__).resolve().parents[1] / "data" / "procintel.duckdb"
UA = {"User-Agent": "procintel-prototype/0.1 (research)"}


def trim(v, width: int = 70, fields: int = 9):
    """A record cut down to read at a glance: first `fields` keys, long strings shortened."""
    if isinstance(v, dict):
        items = list(v.items())
        out = {k: trim(x, width) for k, x in items[:fields]}
        if len(items) > fields:
            out["..."] = f"{len(items) - fields} more fields"
        return out
    if isinstance(v, str) and len(v) > width:
        return v[:width] + "..."
    return v


def rows_in(table: str) -> str:
    try:
        con = duckdb.connect(str(DB), read_only=True)
        n = con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
        con.close()
        return f"{n:,} rows"
    except Exception as e:  # no database here, or table missing: the API part still works
        return f"(cannot count: {type(e).__name__})"


def show(n: int, title: str, url: str, params: dict, record, entity: str | None, tables: list[str], note: str = "") -> None:
    r = requests.get(url, params=params, headers=UA, timeout=60)
    r.raise_for_status()
    print(f"\n{'=' * 78}\n{n}. {title}\nGET {r.url}\n{'-' * 78}")
    print(json.dumps(trim(record(r.json())), indent=2, ensure_ascii=False))
    if entity:
        e = ENTITY_TYPES[entity]
        print(f"\n  -> entity type {e.name}: looked at every {e.every}; watched fields {e.watched}")
    else:
        print("\n  -> no entity type: loaded, not watched")
    print("  -> raw table(s): " + ", ".join(f"{t} ({rows_in(t)})" for t in tables) + (f"\n  -> {note}" if note else ""))


def first(d: dict, key: str):
    part = d.get(key, {})
    items = part if isinstance(part, list) else [v for k, v in part.items() if k != "facets"]
    return items[0] if items else {}


def main() -> None:
    project = sys.argv[1] if len(sys.argv) > 1 else "P118518"
    iso3 = sys.argv[2] if len(sys.argv) > 2 else "KEN"
    show(1, "Procurement notices", f"{SEARCH}/v2/procnotices",
         {"format": "json", "rows": 1, "os": 0, "project_id": project},
         lambda d: first(d, "procnotices"), "Notice", ["notices"])
    show(2, "Projects", f"{SEARCH}/v2/projects", {"format": "json", "rows": 1, "os": 0, "id": project},
         lambda d: first(d, "projects"), "Project", ["projects"])
    show(3, "Documents (completion reports; ISRs and restructuring papers come from the same API)", f"{SEARCH}/v3/wds",
         {"format": "json", "rows": 1, "os": 0, "projectid": project,
          "docty_exact": "Implementation Completion and Results Report",
          "fl": "id,docty,docdt,projectid,display_title,pdfurl,txturl,count"},
         lambda d: first(d, "documents"), "Document", ["documents"],
         "ISRs and restructuring papers become SupervisionDoc and land in the same table")
    show(4, "Finances One contract awards", FONE,
         {"datasetId": "DS00005", "resourceId": "RS00005", "type": "json", "top": 1, "filter": f"project_id='{project}'"},
         lambda d: (d.get("data") or [{}])[0], "ContractAward", ["contract_award"])
    show(5, "Indicators (CPIA score for one country; governance and exchange rates come the same way)",
         f"{INDICATORS}/country/{iso3}/indicator/IQ.CPA.TRAN.XQ", {"format": "json", "per_page": 1},
         lambda d: d[1][0] if isinstance(d, list) and len(d) > 1 and d[1] else {}, "Indicator", ["cpia", "wgi", "fx"],
         "cpia and wgi are watched (Indicator); fx comes from the same API but is not watched")
    print(f"\n{'=' * 78}\n5 sources -> {len(ENTITY_TYPES)} entity types: {', '.join(ENTITY_TYPES)}")
    print("raw tables: notices, projects, documents, contract_award, cpia, wgi, fx  (7; six watched, fx not)")


if __name__ == "__main__":
    main()
