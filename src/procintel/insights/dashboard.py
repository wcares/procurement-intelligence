"""What went badly in past procurement, worst to best (docs/ui-design.md section 1).

Loaded once per data reload (like the API's other state): one frame of packages (award time, method, country, sector
family, tender year) and one of projects (country, sector family, closing year, re-tendering, amendments, procurement
rated below satisfactory, problem passages). MEASURES says what each measure counts, whether higher is worse, and
which groupings it supports; every number comes with how many projects and packages are behind it, and records() lists
those records for a drill-down. The cautions in the design (recent years incomplete, problem kinds unreliable,
small groups) are returned with the data, so the page cannot leave them out.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from procintel.core import db
from procintel.ingestion import sectors
from procintel.prediction.predict import LONG_DAYS

PROJECT_URL = "https://projects.worldbank.org/en/projects-operations/project-detail/{}"  # its procurement tab lists the notices
FOLLOW_UP_MONTHS = 18   # tenders younger than this have not all been awarded: their years are marked incomplete
FEW_PROJECTS = 3        # rows behind fewer projects are flagged as too few to compare
BELOW_SATISFACTORY = ("Moderately Unsatisfactory", "Unsatisfactory", "Highly Unsatisfactory")
GROUPS = {"country": "Country", "sector": "Sector", "method": "Procurement method"}


@dataclass(frozen=True)
class Measure:
    key: str
    label: str
    unit: str            # "days", "share" or "per project"
    level: str           # "package" or "project": what the n behind a value counts
    higher_is_worse: bool = True
    note: str = ""


MEASURES = {m.key: m for m in [
    Measure("delay", "Median tender-to-award time", "days", "package",
            note="Awarded tenders only: slow tenders that were never awarded are missing, so this is optimistic."),
    Measure("long_share", f"Awards taking over {LONG_DAYS // 30} months", "share", "package"),
    Measure("rebid", "Projects with re-tendering", "share", "project",
            note="From completion reports and re-bid notice references (procintel.prediction.evidence)."),
    Measure("amendment", "Projects with contract amendments", "share", "project"),
    Measure("procurement_rating", "Reports rating procurement below satisfactory", "share", "project",
            note="Only 52 of 120 reports state a procurement rating; the share is of those."),
    Measure("problems", "Problem passages per report", "per project", "project",
            note="Problem tags cover part of the passages so far; kinds of problem are less reliable (8 of 13 right "
                 "by hand) than whether a passage describes one (29 of 30)."),
]}


class Dashboard:
    def __init__(self, db_path=None):
        con = db.connect(db_path, read_only=True)
        try:
            fam = sectors.project_families(con)
            countries = {c: (n, r) for c, n, r in con.execute("SELECT country_code, name, region FROM country").fetchall()}
            pk = con.execute("""
                SELECT k.package_id, k.project_id, k.proc_group, k.method_code, k.description, k.tender_to_award_days,
                       year(k.tender_start::DATE) AS tender_year, k.tender_start::DATE AS tender_start, p.country_code
                FROM package k JOIN project p USING (project_id)""").df()
            pr = con.execute("""
                SELECT p.project_id, p.name, p.country_code, year(p.closing_date::DATE) AS closing_year,
                       bool_or(e.kind = 'rebid') AS rebid, bool_or(e.kind = 'amendment') AS amendment
                FROM project p LEFT JOIN project_evidence e USING (project_id)
                GROUP BY ALL""").df()
            rated = con.execute(f"""
                SELECT dp.project_id, bool_or(c.lowest IN {BELOW_SATISFACTORY}) AS below
                FROM procurement_check c JOIN document_project dp USING (doc_id)
                WHERE c.lowest IS NOT NULL GROUP BY 1""").df()
            problems = con.execute("""
                SELECT dp.project_id, count(*) FILTER (WHERE cp.problem) AS problems, count(*) AS tagged
                FROM chunk_problem cp JOIN chunk c USING (chunk_id) JOIN document_project dp USING (doc_id)
                GROUP BY 1""").df()
            kinds = con.execute("""
                SELECT dp.project_id, cp.kind, count(*) AS n
                FROM chunk_problem cp JOIN chunk c USING (chunk_id) JOIN document_project dp USING (doc_id)
                WHERE cp.problem AND cp.kind IS NOT NULL GROUP BY 1, 2""").df()
        finally:
            con.close()
        self.countries = countries
        pk["sector"] = pk["project_id"].map(fam)
        pr["sector"] = pr["project_id"].map(fam)
        pr = pr.merge(rated.rename(columns={"below": "procurement_rating"}), on="project_id", how="left")
        pr = pr.merge(problems, on="project_id", how="left")
        for c in ("rebid", "amendment"):
            pr[c] = pr[c].fillna(False).astype(bool)
        self.packages, self.projects, self.kinds = pk, pr, kinds
        cutoff = pd.Timestamp(date.today()) - pd.DateOffset(months=FOLLOW_UP_MONTHS)
        self.complete_until = int((cutoff - pd.DateOffset(years=1)).year) if cutoff.month < 12 else int(cutoff.year)

    # --- labels -------------------------------------------------------------------------------------------------------
    def label(self, group: str, key: str) -> str:
        if group == "country":
            return self.countries.get(key, (key, None))[0] or key
        return key

    # --- summary ------------------------------------------------------------------------------------------------------
    def summary(self) -> dict:
        pk, pr = self.packages, self.projects
        awarded = pk["tender_to_award_days"].dropna()
        return {"projects": len(pr), "countries": int(pr["country_code"].nunique()), "packages": len(pk),
                "awarded": int(awarded.size),
                "median_days": round(float(awarded.median()), 1) if awarded.size else None,
                "long_share": round(float((awarded > LONG_DAYS).mean()), 3) if awarded.size else None,
                "rebid_projects": int(pr["rebid"].sum()), "amendment_projects": int(pr["amendment"].sum())}

    # --- ranking ------------------------------------------------------------------------------------------------------
    def supports(self, measure: str, group: str) -> bool:
        m = MEASURES[measure]
        return not (m.level == "project" and group == "method")  # a method is a package attribute

    def _package_values(self, frame: pd.DataFrame, measure: str):
        d = frame["tender_to_award_days"].dropna()
        if d.empty:
            return None, 0
        return (float(d.median()) if measure == "delay" else float((d > LONG_DAYS).mean())), int(d.size)

    def _project_values(self, frame: pd.DataFrame, measure: str):
        if measure == "procurement_rating":
            f = frame["procurement_rating"].dropna()
            return (float(f.astype(bool).mean()), int(f.size)) if f.size else (None, 0)
        if measure == "problems":
            f = frame.dropna(subset=["tagged"])
            return (float(f["problems"].sum() / len(f)), len(f)) if len(f) else (None, 0)
        return float(frame[measure].mean()), len(frame)

    def ranking(self, measure: str, group: str) -> dict:
        """Rows worst first: {key, label, value, n, projects, few}."""
        if measure not in MEASURES or group not in GROUPS:
            raise KeyError("unknown measure or group")
        if not self.supports(measure, group):
            raise ValueError(f"{MEASURES[measure].label} is counted per project, not per {GROUPS[group].lower()}")
        m = MEASURES[measure]
        col = {"country": "country_code", "sector": "sector", "method": "method_code"}[group]
        rows = []
        if m.level == "package":
            for key, f in self.packages.dropna(subset=[col]).groupby(col):
                value, n = self._package_values(f, measure)
                if value is not None:
                    rows.append({"key": key, "value": value, "n": n, "projects": int(f["project_id"].nunique())})
        else:
            for key, f in self.projects.dropna(subset=[col]).groupby(col):
                value, n = self._project_values(f, measure)
                if value is not None:
                    rows.append({"key": key, "value": value, "n": n, "projects": n})
        for r in rows:
            r["label"] = self.label(group, r["key"])
            r["value"] = round(r["value"], 3 if m.unit != "days" else 1)
            r["few"] = r["projects"] < FEW_PROJECTS
        rows.sort(key=lambda r: (r["few"], -r["value"] if m.higher_is_worse else r["value"]))
        return {"measure": _measure_json(m), "group": group, "groupLabel": GROUPS[group], "rows": rows}

    # --- trends -------------------------------------------------------------------------------------------------------
    def trends(self) -> dict:
        """Award time by tender year (incomplete years marked), problems by project closing year."""
        out = []
        for year, f in self.packages.dropna(subset=["tender_year"]).groupby("tender_year"):
            d = f["tender_to_award_days"].dropna()
            if d.size:
                out.append({"year": int(year), "median_days": round(float(d.median()), 1),
                            "long_share": round(float((d > LONG_DAYS).mean()), 3), "n": int(d.size),
                            "incomplete": int(year) > self.complete_until})
        probs = []
        tagged = self.projects.dropna(subset=["tagged", "closing_year"])
        for year, f in tagged.groupby("closing_year"):
            probs.append({"year": int(year), "per_project": round(float(f["problems"].sum() / len(f)), 2),
                          "projects": len(f)})
        return {"award": out, "problems": probs, "completeUntil": self.complete_until,
                "note": f"Tenders from after {self.complete_until} are not all awarded yet (follow-up "
                        f"{FOLLOW_UP_MONTHS} months), so their award times look shorter than they will be."}

    # --- heat map -----------------------------------------------------------------------------------------------------
    def heatmap(self, measure: str = "delay", min_n: int = 5) -> dict:
        """Country x procurement method for a package measure; cells behind fewer than min_n awards are left out."""
        if MEASURES[measure].level != "package":
            raise ValueError("the heat map shows package measures (award time, long awards)")
        cells = []
        for (cc, method), f in self.packages.groupby(["country_code", "method_code"]):
            value, n = self._package_values(f, measure)
            if value is not None and n >= min_n:
                cells.append({"country": cc, "countryLabel": self.label("country", cc), "method": method,
                              "value": round(value, 3 if measure == "long_share" else 1), "n": n})
        return {"measure": _measure_json(MEASURES[measure]), "minN": min_n, "cells": cells}

    # --- problem mix --------------------------------------------------------------------------------------------------
    def problem_mix(self) -> dict:
        k = self.kinds.merge(self.projects[["project_id", "sector"]], on="project_id", how="left")
        by_kind = k.groupby("kind")["n"].sum().sort_values(ascending=False)
        return {"kinds": [{"kind": kind, "passages": int(n)} for kind, n in by_kind.items()],
                "note": MEASURES["problems"].note}

    # --- drill-down ---------------------------------------------------------------------------------------------------
    def records(self, group: str, key: str, measure: str, method: str | None = None, limit: int = 200) -> dict:
        """The records behind one ranking row (or one heat-map cell, with method): packages or projects."""
        m = MEASURES[measure]
        col = {"country": "country_code", "sector": "sector", "method": "method_code"}[group]
        if m.level == "package":
            f = self.packages[(self.packages[col] == key) & self.packages["tender_to_award_days"].notna()]
            if method:
                f = f[f["method_code"] == method]
            f = f.sort_values("tender_to_award_days", ascending=False).head(limit)
            return {"kind": "packages", "records": [
                {"packageId": r.package_id, "projectId": r.project_id, "method": r.method_code,
                 "description": r.description or "", "days": int(r.tender_to_award_days),
                 "tenderStart": r.tender_start.isoformat() if pd.notna(r.tender_start) else None,
                 "url": PROJECT_URL.format(r.project_id)}
                for r in f.itertuples()]}
        f = self.projects[self.projects[col] == key]
        return {"kind": "projects", "records": [
            {"projectId": r.project_id, "name": r.name, "country": r.country_code, "rebid": bool(r.rebid),
             "amendment": bool(r.amendment),
             "procurementBelowSatisfactory": None if pd.isna(r.procurement_rating) else bool(r.procurement_rating),
             "problemPassages": None if pd.isna(r.tagged) else int(r.problems),
             "url": PROJECT_URL.format(r.project_id)}
            for r in f.head(limit).itertuples()]}


def _measure_json(m: Measure) -> dict:
    return {"key": m.key, "label": m.label, "unit": m.unit, "level": m.level, "higherIsWorse": m.higher_is_worse,
            "note": m.note}


def measures() -> list[dict]:
    return [_measure_json(m) | {"groups": [g for g in GROUPS if not (m.level == "project" and g == "method")]}
            for m in MEASURES.values()]
