"""Show what the World Bank APIs return, untouched, and where the pipeline keeps it.

    python scripts/show_raw_api.py [PROJECT_ID]        (default P118518)

Makes the same three requests the pipeline makes (procintel.ingestion.wb_client) and prints each answer as it comes:
no renaming, no typing, no cleaning. The pipeline stores each answer as a file in data/cache/http/ (named by a hash of
the request) and builds its tables from those files; the tables are what pgAdmin shows.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import requests

SEARCH = "https://search.worldbank.org/api"
CACHE = Path(__file__).resolve().parents[1] / "data" / "cache" / "http"
UA = "procintel-prototype/0.1 (research)"   # the same header the pipeline sends


def cache_file(url: str, params: dict | None, text: bool = False) -> Path:
    """The file the pipeline keeps this answer in (same key as procintel.ingestion.wb_client)."""
    key = hashlib.sha256((url + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()[:32]
    return CACHE / f"{key}{'.txt' if text else '.json'}"


def show(title: str, url: str, params: dict, text: bool = False, limit: int = 1800) -> None:
    r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    body = r.text if text else json.dumps(r.json(), indent=2, ensure_ascii=False)
    saved = cache_file(url, params, text)
    print(f"\n{'=' * 78}\n{title}\nGET {r.url}\nthe pipeline's copy: {saved.relative_to(CACHE.parents[1])} "
          f"({'exists' if saved.exists() else 'not fetched yet'})\n{'-' * 78}")
    print(body[:limit] + (f"\n... ({len(body):,} characters in all)" if len(body) > limit else ""))


def main() -> None:
    project = sys.argv[1] if len(sys.argv) > 1 else "P118518"
    show(f"1. The project record for {project}", f"{SEARCH}/v2/projects",
         {"format": "json", "rows": 1, "os": 0, "id": project})
    show(f"2. Procurement notices of {project}", f"{SEARCH}/v2/procnotices",
         {"format": "json", "rows": 2, "os": 0, "project_id": project}, limit=3000)
    listing = requests.get(f"{SEARCH}/v3/wds", headers={"User-Agent": UA}, timeout=60, params={
        "format": "json", "rows": 1, "os": 0, "projectid": project,
        "docty_exact": "Implementation Completion and Results Report",
        "fl": "id,docty,docdt,projectid,display_title,pdfurl,txturl,count"}).json()
    docs = [v for k, v in listing.get("documents", {}).items() if k != "facets"]
    if docs:
        show("3. The report listing, then the report's full text", f"{SEARCH}/v3/wds", {
            "format": "json", "rows": 1, "os": 0, "projectid": project,
            "docty_exact": "Implementation Completion and Results Report",
            "fl": "id,docty,docdt,projectid,display_title,pdfurl,txturl,count"})
        show(f"   its text ({docs[0]['txturl']})", docs[0]["txturl"], {}, text=True, limit=1200)
    else:
        print(f"\n3. {project} has no completion report yet.")


if __name__ == "__main__":
    main()
