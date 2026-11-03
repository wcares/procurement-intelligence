"""Word (.docx) versions of a plan and of a package assessment, built from the same data the page shows.

The page sends what it has (the plan with its forecasts, or the assessment response with its request), so the file
matches the screen and nothing is recomputed here. Not the chat: only the result. Every file says when it was made,
that forecasts are estimates from past World Bank packages, and where each quoted lesson comes from.

    plan_docx(body) -> bytes          assessment_docx(body) -> bytes
"""
from __future__ import annotations

import io
from datetime import date, datetime, timezone

from docx import Document
from docx.shared import Pt, RGBColor

NOTE = ("Forecasts are estimates from the tender-to-award times of comparable past World Bank packages "
        "(and a trained model where it applies), not commitments. The evidence behind each number is in the app.")


def _d(iso: str | None) -> str:
    if not iso:
        return "–"
    try:
        return date.fromisoformat(iso[:10]).strftime("%d %b %Y")
    except ValueError:
        return iso


def _new(title: str, who: str | None) -> Document:
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(10.5)
    doc.add_heading(title, level=0)
    made = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    p = doc.add_paragraph(f"Made {made}" + (f" by {who}" if who else "") + " with the procurement intelligence prototype.")
    p.runs[0].font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    return doc


def _table(doc, header: list[str], rows: list[list[str]]) -> None:
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Light Grid Accent 1"
    for c, h in zip(t.rows[0].cells, header):
        c.text = h
    for r in rows:
        for c, v in zip(t.add_row().cells, r):
            c.text = "" if v is None else str(v)


def _bytes(doc) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _note(doc, text: str = NOTE) -> None:
    p = doc.add_paragraph(text)
    p.runs[0].italic = True


def deadline_check(rows: list[dict], deadline: str) -> tuple[list[str], list[str]]:
    """(ids whose typical award is after the deadline, ids that miss it only in the slow case), as on the page."""
    late = [r["id"] for r in rows if r["award50"] > deadline]
    at_risk = [r["id"] for r in rows if r["award50"] <= deadline < r["award90"]]
    return late, at_risk


PLAN_NOTE = ("Each forecast comes from comparable past packages; the project dates combine them in the order set. Treat the "
             "project dates as a planning aid: the system has not learned how packages depend on each other.")


def _days(n: int) -> str:
    return f"{abs(n)} day{'' if abs(n) == 1 else 's'}"


def _between(a: str, b: str) -> int:
    return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days


def slack(row: dict, deadline: str) -> str:
    """Days to spare or late against the deadline, typical and slow case, worded as on the plan page."""
    t = _between(row["award50"], deadline)
    out = f"{_days(t)} late" if t < 0 else f"{_days(t)} to spare"
    if not row.get("p90Missing"):
        s = _between(row["award90"], deadline)
        out += f", slow case {_days(s)} late" if s < 0 else f", slow case {_days(s)} to spare"
    return out


def why(f: dict) -> str:
    """Where a forecast comes from, worded as the plan page's "why this number?"."""
    src = "A model trained on past World Bank packages" if f.get("basis") == "model" else "The median of comparable past packages"
    n = f" ({f['n']} packages{', ' + f['scope'] if f.get('scope') else ''})" if f.get("n") else ""
    text = f"{src}{n}: {f.get('p50')} days typical" + (f", {f['p90']} in the slow case (1 in 10)" if f.get("p90") else "")
    if f.get("pLong") is not None:
        text += f"; {round(f['pLong'] * 100)}% chance of more than 180 days"
    text += "."
    if f.get("risks"):
        text += f" Risks: {'; '.join(f['risks'])}."
    return text


def _freshness_line(only: tuple[str, ...]) -> str | None:
    """"Data read: ..." as under the plan on the page; None when the pipeline store cannot be read."""
    try:
        from procintel.pipeline import freshness
        rows = [s for s in freshness.sources() if s["entity"] in only]
    except Exception:  # noqa: BLE001
        return None
    ago = lambda h: "never" if h is None else f"{max(1, round(h * 60))} min ago" if h < 1 else f"{round(h)} h ago" if h < 48 else f"{round(h / 24)} days ago"  # noqa: E731
    return "Data read: " + " · ".join(f"{s['label']} {ago(s['hoursAgo'])}{' (late)' if s['late'] else ''}" for s in rows)


def plan_docx(body: dict, who: str | None = None) -> bytes:
    packages = {p["id"]: p for p in body.get("packages", [])}
    plan, forecasts = body.get("plan") or {}, body.get("forecasts") or {}
    rows = plan.get("rows") or []
    name = lambda i: packages.get(i, {}).get("name") or "Unnamed package"  # noqa: E731
    doc = _new(body.get("title") or "Procurement plan", who)
    doc.add_heading("Summary", level=1)
    _table(doc, ["", ""], [
        ["Project start", _d(body.get("projectStart"))],
        ["Typical: all packages awarded by", _d(plan.get("end50"))],
        ["Slow case: all packages awarded by", _d(plan.get("end90"))],
        ["Likely bottleneck (awarded last)", name(plan["bottleneck"]) if plan.get("bottleneck") else "–"],
    ] + ([["Deadline", _d(body["deadline"])]] if body.get("deadline") else []))
    if body.get("deadline") and rows:
        late, at_risk = deadline_check(rows, body["deadline"])
        doc.add_heading("Deadline check", level=1)
        if not late and not at_risk:
            doc.add_paragraph(f"Every package is awarded by {_d(body['deadline'])} even in the slow case.")
        if late:
            doc.add_paragraph(f"Typical award date after the deadline: {', '.join(map(name, late))}.")
        if at_risk:
            doc.add_paragraph(f"Only the slow case misses the deadline: {', '.join(map(name, at_risk))}.")
    if plan.get("loops"):
        doc.add_paragraph(f"Not scheduled (packages that wait for each other in a loop): {', '.join(map(name, plan['loops']))}.")
    doc.add_heading("Packages", level=1)
    out = []
    for r in rows:
        p, f = packages.get(r["id"], {}), forecasts.get(r["id"]) or {}
        days = f"{f.get('p50')}" + (f" (slow {f['p90']})" if f.get("p90") else "") if f else "–"
        out.append([name(r["id"]), f"{p.get('procGroup', '')} {p.get('methodCode', '')}".strip(), _d(r.get("start50")),
                    _d(r.get("award50")), _d(r.get("award90")) + (" *" if r.get("p90Missing") else ""), days,
                    f"{f.get('basis', '–')}" + (f", {f['n']} packages" if f.get("n") else ""),
                    "; ".join(f.get("risks") or []) or "–", name(r["waitsFor"]) if r.get("waitsFor") else ""])
    _table(doc, ["Package", "Method", "Tender", "Typical award", "Slow-case award", "Days", "Basis", "Risks", "Waits for"], out)
    if any(r.get("p90Missing") for r in rows):
        doc.add_paragraph("* no slow-case estimate: the typical date stands in for it.")
    doc.add_heading("Each package", level=1)
    for r in rows:
        f = forecasts.get(r["id"]) or {}
        doc.add_paragraph(name(r["id"]) + (f" · after {name(r['waitsFor'])}" if r.get("waitsFor") else ""), style="List Bullet")
        lines = [f"Award {_d(r.get('award50'))}" + (f" ({f.get('p50')} days)" if f else "") + ("" if r.get("p90Missing") else f" · slow {_d(r.get('award90'))}")]
        if body.get("deadline"):
            lines.append(slack(r, body["deadline"]))
        if f:
            lines.append("Why this number: " + why(f))
        for line in lines:
            doc.add_paragraph(line).paragraph_format.left_indent = Pt(18)
    if (fresh := _freshness_line(("Notice", "ContractAward", "Project"))):
        doc.add_paragraph(fresh)
    _note(doc, PLAN_NOTE)
    _note(doc)
    return _bytes(doc)


def assessment_docx(body: dict, who: str | None = None) -> bytes:
    req, res = body.get("request") or {}, body.get("response") or {}
    doc = _new("Package assessment", who)
    doc.add_heading("The package", level=1)
    _table(doc, ["", ""], [[k, str(v)] for k, v in [
        ("Country", req.get("countryCode")), ("Procurement group", req.get("procGroup")), ("Method", req.get("methodCode")),
        ("Sector", req.get("sector")), ("Estimated value (US$)", f"{req['estimatedValueUsd']:,.0f}" if req.get("estimatedValueUsd") else None),
        ("Project", req.get("projectId")), ("Description", req.get("description")), ("Tender reference", req.get("tenderReference"))] if v])
    t, pred = res.get("timeline"), res.get("prediction")
    doc.add_heading("Tender notice to award", level=1)
    if t:
        doc.add_paragraph(f"Comparable packages ({t['scope']}, n = {t['n']}): median {t['median']:.0f} days, "
                          f"middle half {t['p25']:.0f}–{t['p75']:.0f} days, 90th percentile {t['p90']:.0f} days.")
    if pred:
        line = f"Forecast for this package ({pred['basis']}): {pred['days_p50']:.0f} days typical"
        line += f", {pred['days_p90']:.0f} days in the slow case" if pred.get("days_p90") else ""
        line += f"; chance of more than 180 days {pred['p_long']:.0%}." if pred.get("p_long") is not None else "."
        doc.add_paragraph(line)
    if not t and not pred:
        doc.add_paragraph("No comparable packages with known award times.")
    if res.get("stages"):
        doc.add_heading("Stages", level=1)
        _table(doc, ["Stage", "Median days", "90th percentile", "Packages"],
               [[s["label"], s.get("median") if s.get("median") is not None else "–", s.get("p90") if s.get("p90") is not None else "–", s["n"]]
                for s in res["stages"]])
    doc.add_heading("Risks", level=1)
    if res.get("risks"):
        _table(doc, ["Risk", "Level", "From", "Why"], [[r["label"], r["level"], r["basis"], r["detail"]] for r in res["risks"]])
    else:
        doc.add_paragraph("No risk flags.")
    scores = (res.get("governance") or []) + (res.get("wgi") or [])
    if scores:
        doc.add_heading("Governance scores", level=1)
        _table(doc, ["Indicator", "Year", "Value"], [[g["indicator"], g["year"], f"{g['value']:.2f}"] for g in scores])
    if res.get("precedents"):
        doc.add_heading("Lessons from past reports", level=1)
        for i, p in enumerate(res["precedents"], 1):
            c = p["citation"]
            doc.add_paragraph(c["quote"], style="Intense Quote")
            src = doc.add_paragraph(f"[{i}] {c.get('projectName', '')} ({c.get('projectId', '')}, {c.get('countryCode', '')}) · "
                                    f"{c.get('docType', '')} · {c.get('section', '')}" + (f" · {c['url']}" if c.get("url") else ""))
            src.runs[0].font.size = Pt(9)
    if body.get("accepted"):   # mitigations the planner accepted from the recommendations, with their sources
        doc.add_heading("Accepted mitigations", level=1)
        for m in body["accepted"]:
            doc.add_paragraph(m.get("title", ""), style="List Bullet")
            if m.get("text"):
                doc.add_paragraph(m["text"])
            for s in m.get("sentences") or []:
                doc.add_paragraph(s.get("text", ""))
            for c in m.get("citations") or []:
                src = doc.add_paragraph(f"{c.get('projectName', '')} ({c.get('projectId', '')}) · {c.get('section', '')}" + (f" · {c['url']}" if c.get("url") else ""))
                src.runs[0].font.size = Pt(9)
    if res.get("similarPackages"):
        doc.add_heading("Similar past packages", level=1)
        _table(doc, ["Package", "Project", "Method", "Days to award", "Value (US$)", "Re-bid"],
               [[s["description"][:80], f"{s['projectId']} {s['countryCode']}", s["method"],
                 s["tenderToAwardDays"] if s.get("tenderToAwardDays") is not None else "–",
                 f"{s['valueUsd']:,.0f}" if s.get("valueUsd") else "–", "yes" if s.get("rebid") else ""]
                for s in res["similarPackages"][:15]])
    caveats = (res.get("meta") or {}).get("caveats") or []
    if caveats:
        doc.add_heading("Caveats", level=1)
        for c in caveats:
            doc.add_paragraph(c, style="List Bullet")
    _note(doc)
    return _bytes(doc)
