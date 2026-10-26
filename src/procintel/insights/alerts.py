"""Watch-lists and alerts (docs/ui-design.md 2.4).

A planner's watch-list names what they follow: regions, countries, sectors, procurement groups, methods, projects. It is a
scope: within one kind any value matches, across kinds all must (Kenya + civil works = Kenyan civil works); a watched
project matches on its own. The pipeline action watch_alerts (procintel.pipeline.actions) hands each batch's events to
`from_events`, which writes one alert per planner and kind of change in their scope:

    new_notices   procurement notices published, by notice type
    reissued      notices re-issued or amended (their version went up)
    awarded       awards recorded, the slow ones (over 180 days from tender) named
    report        a completion report added for a watched project (from the World Bank or an upload)
    award_shift   award times for a method in the planner's scope moved by SHIFT or more: the median days from tender
                  to award of the awards recorded in the last RECENT_DAYS against the BASELINE_DAYS before, each side
                  with enough awards (MIN_RECENT, MIN_BASELINE); at most one per method every REPEAT_DAYS. Checked when
                  award dates change (award_shifts)

Alerts are in-app only (user, 2026-10-25) and kept RETENTION_DAYS like other history (procintel.jobs.retention).
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from procintel.core import db
from procintel.pipeline import store as pipeline_store

KINDS = {"region": "region", "country": "country_code", "sector": "sector", "proc_group": "proc_group", "method": "method_code",
         "project": "project_id"}
SLOW_DAYS = 180
SHIFT = float(os.environ.get("PROCINTEL_AWARD_SHIFT", "0.2"))
RECENT_DAYS, BASELINE_DAYS = 365, 3 * 365
MIN_RECENT, MIN_BASELINE = int(os.environ.get("PROCINTEL_AWARD_SHIFT_MIN_N", "8")), 15
REPEAT_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def connect(db_path: Path | None = None):
    con = pipeline_store.connect(db_path)
    con.execute("CREATE TABLE IF NOT EXISTS watch (username VARCHAR, kind VARCHAR, value VARCHAR, added_at TIMESTAMP)")
    con.execute("""CREATE TABLE IF NOT EXISTS alert (alert_id VARCHAR, username VARCHAR, kind VARCHAR, title VARCHAR,
                   detail VARCHAR, refs VARCHAR, created_at TIMESTAMP, read_at TIMESTAMP)""")
    return con


def get_watch(username: str, db_path: Path | None = None) -> dict[str, list[str]]:
    con = connect(db_path)
    try:
        out: dict[str, list[str]] = {k: [] for k in KINDS}
        for k, v in con.execute("SELECT kind, value FROM watch WHERE username = ? ORDER BY value", [username]).fetchall():
            out.setdefault(k, []).append(v)
        return out
    finally:
        con.close()


def set_watch(username: str, watch: dict[str, list[str]], db_path: Path | None = None) -> dict[str, list[str]]:
    unknown = set(watch) - set(KINDS)
    if unknown:
        raise ValueError(f"unknown watch kinds {sorted(unknown)}; one of {', '.join(KINDS)}")
    con = connect(db_path)
    try:
        con.execute("DELETE FROM watch WHERE username = ?", [username])
        rows = [(username, k, v.strip(), _now()) for k, vs in watch.items() for v in dict.fromkeys(vs) if v.strip()]
        if rows:
            con.executemany("INSERT INTO watch VALUES (?, ?, ?, ?)", rows)
    finally:
        con.close()
    return get_watch(username, db_path)


def _all_watches(db_path: Path | None) -> dict[str, dict[str, set[str]]]:
    con = connect(db_path)
    try:
        out: dict[str, dict[str, set[str]]] = {}
        for u, k, v in con.execute("SELECT username, kind, value FROM watch").fetchall():
            out.setdefault(u, {}).setdefault(k, set()).add(v)
        return out
    finally:
        con.close()


def in_scope(watch: dict[str, set[str]], facts: dict) -> bool:
    if facts.get("project_id") in watch.get("project", set()):
        return True
    scope = {k: vs for k, vs in watch.items() if k != "project" and vs}
    return bool(scope) and all(facts.get(KINDS[k]) in vs for k, vs in scope.items())


def _projects(ids: set[str]) -> dict[str, dict]:
    if not ids:
        return {}
    con = db.connect(read_only=True)
    try:
        q = con.execute("SELECT project_id, name, country, country_code, region, sector FROM projects "
                        "WHERE project_id IN (SELECT unnest(?))", [sorted(ids)])
        cols = [d[0] for d in q.description]
        return {r[0]: dict(zip(cols, r)) for r in q.fetchall()}
    finally:
        con.close()


def _award_days(package_ids: list[str]) -> dict[str, int]:
    if not package_ids:
        return {}
    con = db.connect(read_only=True)
    try:
        return {p: int(d) for p, d in con.execute(
            "SELECT package_id, tender_to_award_days FROM package WHERE package_id IN (SELECT unnest(?)) "
            "AND tender_to_award_days IS NOT NULL", [package_ids]).fetchall()}
    finally:
        con.close()


def changes(events: dict[str, dict], document_rows: dict[str, dict]) -> list[dict]:
    """What a batch's events mean for a planner: one fact per change, with the attributes a watch-list matches on.
    events: {key: event} as the pipeline passes them (Notice events carry the source row in `new`);
    document_rows: {doc_id: documents row} for reports added in the batch."""
    out = []
    for key, e in events.items():
        new, typ = e.get("new"), e["type"]
        if not new or not typ.startswith("Notice."):
            continue
        base = {"project_id": new.get("project_id"), "proc_group": new.get("proc_group"),
                "method_code": new.get("method_code"), "ref": {"type": "notice", "key": key,
                                                               "label": (new.get("description") or key)[:120]},
                "package_id": f"{new.get('project_id')}/{new.get('bid_ref')}" if new.get("bid_ref") else None}
        changed = set(e.get("changed") or [])
        version = new.get("notice_version") or 0
        if typ == "Notice.added":
            out.append(base | {"kind": "new_notices", "what": new.get("notice_type") or "notice"})
        if (typ == "Notice.added" and version >= 1) or "notice_version" in changed:
            out.append(base | {"kind": "reissued", "what": new.get("notice_type") or "notice"})
        if "award_date" in changed or (typ == "Notice.added" and new.get("notice_type") == "Contract Award"):
            out.append(base | {"kind": "awarded", "what": "award"})
    for doc_id, d in document_rows.items():
        for pid in (d.get("project_id") or "").split(","):
            if pid:
                out.append({"kind": "report", "project_id": pid, "what": d.get("title") or doc_id,
                            "ref": {"type": "document", "key": doc_id, "label": (d.get("title") or doc_id)[:120]}})
    facts = _projects({c["project_id"] for c in out if c.get("project_id")})
    for c in out:
        p = facts.get(c.get("project_id"), {})
        c.update({"country_code": p.get("country_code"), "region": p.get("region"), "sector": p.get("sector"),
                  "country": p.get("country"),
                  "project_name": p.get("name")})
    return out


def _alert(kind: str, items: list[dict], days: dict[str, int]) -> tuple[str, str]:
    n = len(items)
    where = sorted({i["country"] for i in items if i.get("country")})
    place = f" in {', '.join(where[:3])}{' and others' if len(where) > 3 else ''}" if where else ""
    if kind == "new_notices":
        by = {}
        for i in items:
            by[i["what"]] = by.get(i["what"], 0) + 1
        return (f"{n} new procurement notice{'s' if n > 1 else ''}{place}",
                ", ".join(f"{v} {k}" for k, v in sorted(by.items(), key=lambda x: -x[1])))
    if kind == "reissued":
        return (f"{n} notice{'s' if n > 1 else ''} re-issued or amended{place}",
                "a new version of a notice can mean changed requirements, an extended deadline or a re-tender")
    if kind == "awarded":
        timed = [i for i in items if i.get("package_id") in days]
        slow = [i for i in timed if days[i["package_id"]] > SLOW_DAYS]
        if not timed:   # an award without a tender notice in the data has no measurable award time
            detail = "award times not known (no tender notice for these packages in the data)"
        elif slow:
            detail = (f"{len(slow)} of the {len(timed)} with a known award time took longer than {SLOW_DAYS} days from "
                      "tender to award: " + ", ".join(f"{days[i['package_id']]} days" for i in slow[:5]))
        else:
            detail = f"none of the {len(timed)} with a known award time took longer than {SLOW_DAYS} days"
        return f"{n} award{'s' if n > 1 else ''} recorded{place}", detail
    names = sorted({i.get("project_name") or i["project_id"] for i in items})
    return (f"{n} new completion report{'s' if n > 1 else ''}", "for " + "; ".join(names[:3]))


def from_events(events: dict[str, dict], document_rows: dict[str, dict], db_path: Path | None = None) -> int:
    """Write the alerts a batch gives each watching planner; returns how many."""
    watches = _all_watches(db_path)
    if not watches:
        return 0
    facts = changes(events, document_rows)
    days = _award_days(sorted({f["package_id"] for f in facts if f["kind"] == "awarded" and f.get("package_id")}))
    rows = []
    for user, watch in watches.items():
        mine = [f for f in facts if in_scope(watch, f)]
        for kind in ("new_notices", "reissued", "awarded", "report"):
            items = [f for f in mine if f["kind"] == kind]
            if items:
                title, detail = _alert(kind, items, days)
                refs = [i["ref"] | ({"days": days[i["package_id"]]} if i.get("package_id") in days else {})
                        for i in items][:50]
                rows.append((uuid.uuid4().hex[:12], user, kind, title, detail, json.dumps(refs), _now(), None))
    if rows:
        con = connect(db_path)
        try:
            con.executemany("INSERT INTO alert VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        finally:
            con.close()
    return len(rows)


def _awards() -> list[dict]:
    """Awarded packages with a measured award time, their award date and the attributes a watch-list matches on."""
    con = db.connect(read_only=True)
    try:
        q = con.execute("""SELECT k.package_id, k.project_id, k.proc_group, k.method_code, k.tender_to_award_days AS days,
                                  k.award_date::VARCHAR AS award_date, p.country_code, p.region, p.sector
                           FROM package k JOIN projects p USING (project_id)
                           WHERE k.tender_to_award_days IS NOT NULL AND k.award_date IS NOT NULL""")
        cols = [d[0] for d in q.description]
        return [dict(zip(cols, r)) for r in q.fetchall()]
    finally:
        con.close()


def _median(xs: list[float]) -> float:
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def award_shifts(db_path: Path | None = None, now: datetime | None = None) -> int:
    """Write award_shift alerts for every planner whose scope saw award times move; returns how many."""
    watches = _all_watches(db_path)
    if not watches:
        return 0
    now = now or _now()
    recent_from, base_from = now - timedelta(days=RECENT_DAYS), now - timedelta(days=RECENT_DAYS + BASELINE_DAYS)
    rows = []
    for a in _awards():
        at = datetime.fromisoformat(a["award_date"][:19])
        if at >= base_from:
            rows.append(a | {"recent": at >= recent_from})
    con = connect(db_path)
    try:
        said = {(u, json.loads(refs)[0]["key"]) for u, refs in con.execute(
            "SELECT username, refs FROM alert WHERE kind = 'award_shift' AND created_at >= ?",
            [now - timedelta(days=REPEAT_DAYS)]).fetchall() if refs and json.loads(refs)}
    finally:
        con.close()
    out = []
    for user, watch in watches.items():
        by_method: dict[str, dict[bool, list[float]]] = {}
        for a in rows:
            if in_scope(watch, a) and a["method_code"]:
                by_method.setdefault(a["method_code"], {True: [], False: []})[a["recent"]].append(float(a["days"]))
        for method, d in sorted(by_method.items()):
            if len(d[True]) < MIN_RECENT or len(d[False]) < MIN_BASELINE or (user, method) in said:
                continue
            now_m, before_m = _median(d[True]), _median(d[False])
            change = (now_m - before_m) / before_m if before_m else 0
            if abs(change) < SHIFT:
                continue
            title = f"Award times for {method} in your watch-list {'rose' if change > 0 else 'fell'} {abs(change):.0%}"
            detail = (f"median {now_m:.0f} days from tender to award for the {len(d[True])} awards recorded in the last "
                      f"12 months, against {before_m:.0f} days for the {len(d[False])} in the 3 years before")
            out.append((uuid.uuid4().hex[:12], user, "award_shift", title, detail,
                        json.dumps([{"type": "method", "key": method, "label": method}]), now, None))
    if out:
        con = connect(db_path)
        try:
            con.executemany("INSERT INTO alert VALUES (?, ?, ?, ?, ?, ?, ?, ?)", out)
        finally:
            con.close()
    return len(out)


def recent(username: str, limit: int = 50, db_path: Path | None = None) -> dict:
    con = connect(db_path)
    try:
        q = con.execute("SELECT alert_id, kind, title, detail, refs, created_at, read_at FROM alert WHERE username = ? "
                        "ORDER BY created_at DESC LIMIT ?", [username, limit])
        items = [{"id": i, "kind": k, "title": t, "detail": d, "refs": json.loads(r), "at": c.isoformat() + "Z",
                  "read": rd is not None} for i, k, t, d, r, c, rd in q.fetchall()]
        unread = con.execute("SELECT count(*) FROM alert WHERE username = ? AND read_at IS NULL", [username]).fetchone()[0]
        return {"alerts": items, "unread": unread}
    finally:
        con.close()


def mark_read(username: str, ids: list[str] | None = None, db_path: Path | None = None) -> None:
    con = connect(db_path)
    try:
        if ids is None:
            con.execute("UPDATE alert SET read_at = ? WHERE username = ? AND read_at IS NULL", [_now(), username])
        else:
            con.execute("UPDATE alert SET read_at = ? WHERE username = ? AND alert_id IN (SELECT unnest(?))",
                        [_now(), username, ids])
    finally:
        con.close()
