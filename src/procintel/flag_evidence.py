"""The records each risk flag rests on, so a planner can open them instead of trusting the number.

- Timeline flags ("long-cycle", "spread"): packages from the same comparable set the statistic was computed over, those
  over the threshold, the asked country first, slowest first; each links to its award notice on the World Bank site.
- "governance": the CPIA rating and its World Bank data page.
- "rebid", "amendment": the evidence rows behind "at least N of M" (table project_evidence): the completion-report
  passage, linked to its PDF, or the re-tender reference in the notices.
- Model flags rest on a model, not on particular records; their detail already states how it was tested.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

from procintel import paths
from procintel.stats import MIN_BENCH_N

DB_PATH = paths.DB_PATH
MAX_ITEMS = 5
LONG_DAYS = 180
NOTICE_URL = "https://projects.worldbank.org/en/projects-operations/procurement-detail/{}"
CPIA_URL = "https://data.worldbank.org/indicator/{}?locations={}"
WGI_URL = "https://www.worldbank.org/en/publication/worldwide-governance-indicators"
CPIA_CODES = {"transparency_corruption": ("IQ.CPA.TRAN.XQ", "CPIA transparency, accountability and corruption in the public sector")}


class FlagEvidence:
    def __init__(self, db_path: Path = DB_PATH):
        con = duckdb.connect(str(db_path), read_only=True)
        q = con.execute("""
            SELECT k.package_id, k.project_id, p.country_code, k.proc_group, k.method_code, k.description,
                   k.tender_to_award_days, year(k.award_date::DATE) AS award_year,
                   (SELECT arg_max(n.notice_id, n.notice_date) FROM notice_m n
                    WHERE n.package_id = k.package_id AND n.notice_type = 'Contract Award') AS notice_id
            FROM package k LEFT JOIN project p USING (project_id)
            WHERE k.tender_to_award_days IS NOT NULL""")
        cols = [d[0] for d in q.description]
        self.packages = [dict(zip(cols, r)) for r in q.fetchall()]
        self.events: dict[str, dict[str, list[dict]]] = {}  # kind -> country -> rows
        if con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'project_evidence'").fetchone():
            for kind, pid, cc, source, ref, quote, pdf, notice in con.execute("""
                    SELECT e.kind, e.project_id, p.country_code, e.source, e.ref, e.quote, d.pdf_url,
                           (SELECT arg_max(n.notice_id, n.notice_date) FROM notice_m n WHERE n.package_id = e.ref)
                    FROM project_evidence e JOIN project p USING (project_id)
                    LEFT JOIN document_m d ON e.source = 'icr' AND d.doc_id = split_part(e.ref, ':', 1)
                    ORDER BY e.source, e.project_id, e.ref""").fetchall():
                self.events.setdefault(kind, {}).setdefault(cc, []).append(
                    {"project_id": pid, "source": source, "ref": ref, "quote": quote or "", "pdf": pdf, "notice": notice})
        con.close()

    def _comparable(self, group: str, method: str, bench: dict) -> list[dict]:
        """The set the timeline statistics used: group and method when it has enough packages, else the group."""
        if (bench.get(f"{group}/{method}") or {}).get("n", 0) >= MIN_BENCH_N:
            return [p for p in self.packages if p["proc_group"] == group and p["method_code"] == method]
        return [p for p in self.packages if p["proc_group"] == group]

    def _packages(self, pool: list[dict], min_days: float, country: str) -> list[dict]:
        over = [p for p in pool if p["tender_to_award_days"] > min_days]
        over.sort(key=lambda p: (p["country_code"] != country, -p["tender_to_award_days"]))
        return [{"kind": "package", "ref": p["package_id"],
                 "label": (p["description"] or p["package_id"])[:120],
                 "detail": f"{p['tender_to_award_days']} days from tender to award · {p['country_code'] or '?'} · "
                           f"{p['project_id']}" + (f" · awarded {p['award_year']}" if p["award_year"] else ""),
                 "url": NOTICE_URL.format(p["notice_id"]) if p["notice_id"] else None} for p in over[:MAX_ITEMS]]

    def _events(self, kind: str, country: str) -> list[dict]:
        """One item per project, matching the flag's "at least N of M projects"; a report passage before a reference."""
        out, seen = [], set()
        for e in self.events.get(kind, {}).get(country, []):  # ordered by source: "icr" before "notice_reference"
            if e["project_id"] in seen or len(out) == MAX_ITEMS:
                continue
            seen.add(e["project_id"])
            if e["source"] == "icr":
                out.append({"kind": "report", "ref": e["ref"], "label": f"Completion report of {e['project_id']}",
                            "detail": f"“…{e['quote'][:260]}…”", "url": e["pdf"]})
            else:
                out.append({"kind": "package", "ref": e["ref"], "label": f"Re-tender reference {e['ref']}",
                            "detail": e["quote"][:160],
                            "url": NOTICE_URL.format(e["notice"]) if e["notice"] else None})
        return out

    def attach(self, flags: list[dict], req: dict, bench: dict, timeline: dict | None, gov: list[dict],
               wgi: list[dict] | None = None) -> list[dict]:
        country, group, method = req["countryCode"], req["procGroup"], req["methodCode"]
        for f in flags:
            ev: list[dict] = []
            if f["id"] == "long-cycle":
                ev = self._packages(self._comparable(group, method, bench), LONG_DAYS, country)
            elif f["id"] == "spread" and timeline:
                ev = self._packages(self._comparable(group, method, bench), timeline["p90"], country)
            elif f["id"] == "governance":
                g = next((g for g in gov if g["indicator"] == "transparency_corruption"), None)
                code, name = CPIA_CODES["transparency_corruption"]
                if g:
                    ev = [{"kind": "indicator", "ref": code, "label": name,
                           "detail": f"{g['value']} on a 1–6 scale ({g['year']})", "url": CPIA_URL.format(code, country)}]
            elif f["id"] == "governance-wgi":
                w = next((w for w in wgi or [] if w["indicator"] == "control_of_corruption"), None)
                if w:
                    ev = [{"kind": "indicator", "ref": "GOV_WGI_CC.EST", "label": "WGI control of corruption (estimate)",
                           "detail": f"{w['value']:+.2f} ({w['year']}); 0 = world average", "url": WGI_URL}]
            elif f["id"] in ("rebid", "amendment"):
                ev = self._events(f["id"], country)
            f["evidence"] = ev
        return flags
