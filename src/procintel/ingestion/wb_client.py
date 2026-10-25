"""World Bank API client.

Endpoints and field names here were checked against live responses on 2026-10-23:
  projects      https://search.worldbank.org/api/v2/projects      (rows, os, fl, id, countrycode_exact ...)
  procnotices   https://search.worldbank.org/api/v2/procnotices   (rows, os, notice_type, project_id ...)
  documents     https://search.worldbank.org/api/v3/wds           (rows, os, docty_exact, projectid, fl ...)
  indicators    https://api.worldbank.org/v2/country/<iso3>/indicator/<code>  (CPIA: IQ.CPA.*)

Replacements found 2026-10-25: the Major Contract Awards Socrata endpoint
(finances.worldbank.org/resource/kdui-wcs3.json) now returns an HTML page; contract awards come from the Finances One
data catalog instead (procintel.ingestion.contract_awards). The old WGI codes (GE.EST, CC.EST) return "indicator not found"; the
current codes are GOV_WGI_<x>.EST (procintel.ingestion.wgi).
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Iterator

import requests

from procintel.core import paths

SEARCH = "https://search.worldbank.org/api"
INDICATORS = "https://api.worldbank.org/v2"
CACHE_DIR = paths.HTTP_CACHE
UA = "procintel-prototype/0.1 (research)"

ICR_TYPE = "Implementation Completion and Results Report"


class WBClient:
    def __init__(self, cache: bool = True, pause: float = 0.2, timeout: int = 60, fresh_listings: bool = False):
        """fresh_listings: re-fetch project / notice / document listings (they change as projects progress) while
        still caching document texts, which do not change once published. Used by procintel.ingestion.refresh."""
        self.cache = cache
        self.fresh_listings = fresh_listings
        self.pause = pause
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # -- low level -----------------------------------------------------
    def _get(self, url: str, params: dict[str, Any] | None = None, text: bool = False, fresh: bool = False) -> Any:
        key = hashlib.sha256((url + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()[:32]
        path = CACHE_DIR / (key + (".txt" if text else ".json"))
        if self.cache and path.exists() and not fresh:
            raw = path.read_text()
            return raw if text else json.loads(raw)
        last: Exception | None = None
        for attempt in range(4):
            try:
                r = self.s.get(url, params=params, timeout=self.timeout)
                r.raise_for_status()
                body = r.text if text else r.json()
                if self.cache:
                    path.write_text(body if text else json.dumps(body))
                time.sleep(self.pause)
                return body
            except (requests.RequestException, ValueError) as e:  # ValueError: bad JSON
                last = e
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"GET failed after retries: {url} {params}") from last

    # -- projects ------------------------------------------------------
    def projects(self, rows: int = 100, offset: int = 0, **filters: Any) -> tuple[int, list[dict]]:
        d = self._get(f"{SEARCH}/v2/projects", {"format": "json", "rows": rows, "os": offset, **filters}, fresh=self.fresh_listings)
        return int(d["total"]), list(d.get("projects", {}).values())

    def iter_projects(self, limit: int, page: int = 100, **filters: Any) -> Iterator[dict]:
        got = 0
        while got < limit:
            total, batch = self.projects(rows=min(page, limit - got), offset=got, **filters)
            if not batch:
                return
            yield from batch
            got += len(batch)
            if got >= total:
                return

    # -- procurement notices ------------------------------------------
    def notices(self, rows: int = 100, offset: int = 0, **filters: Any) -> tuple[int, list[dict]]:
        d = self._get(f"{SEARCH}/v2/procnotices", {"format": "json", "rows": rows, "os": offset, **filters}, fresh=self.fresh_listings)
        return int(d["total"]), list(d.get("procnotices", []))

    def iter_notices(self, limit: int, page: int = 100, **filters: Any) -> Iterator[dict]:
        got = 0
        while got < limit:
            total, batch = self.notices(rows=min(page, limit - got), offset=got, **filters)
            if not batch:
                return
            yield from batch
            got += len(batch)
            if got >= total:
                return

    # -- documents (WDS) ----------------------------------------------
    def documents(self, rows: int = 50, offset: int = 0, **filters: Any) -> tuple[int, list[dict]]:
        params = {
            "format": "json", "rows": rows, "os": offset,
            "fl": "id,docty,docdt,projectid,display_title,pdfurl,txturl,count",
            **filters,
        }
        d = self._get(f"{SEARCH}/v3/wds", params, fresh=self.fresh_listings)
        docs = [v for k, v in d.get("documents", {}).items() if k != "facets"]
        return int(d["total"]), docs

    def iter_documents(self, limit: int, page: int = 50, **filters: Any) -> Iterator[dict]:
        got = 0
        while got < limit:
            total, batch = self.documents(rows=min(page, limit - got), offset=got, **filters)
            if not batch:
                return
            yield from batch
            got += len(batch)
            if got >= total:
                return

    def document_text(self, txturl: str) -> str:
        return self._get(txturl, text=True)

    # -- indicators ----------------------------------------------------
    def indicator(self, iso3: str, code: str, per_page: int = 60) -> list[dict]:
        d = self._get(f"{INDICATORS}/country/{iso3}/indicator/{code}", {"format": "json", "per_page": per_page})
        if not isinstance(d, list) or len(d) < 2 or d[1] is None:
            return []  # API returns a [ {message: ...} ] list on a bad code/country
        return d[1]
