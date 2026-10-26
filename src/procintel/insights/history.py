"""Past recommendations (procintel.insights.recommendations) and what planners did with them, for the Insights page.

Each recommendation request is a logged response (procintel.learning.feedback, kind "recommend"); accepting or
dismissing one is a rating on that response whose comment names the recommendation ("accepted recommendation
method:RFQ"). The list is the signed-in planner's own; the counts are over everyone's, by kind of recommendation, so
a kind people keep dismissing shows up.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from procintel.learning import feedback

DECISION = re.compile(r"^(accepted|dismissed) recommendation (\S+)$")


def _decisions(con, response_ids: list[str] | None) -> dict[tuple[str, str], str]:
    """(response id, recommendation id) -> the latest decision."""
    where, args = ("AND response_id IN (SELECT unnest(?))", [response_ids]) if response_ids is not None else ("", [])
    out = {}
    for rid, comment in con.execute(f"SELECT response_id, comment FROM feedback WHERE comment IS NOT NULL {where} "
                                    "ORDER BY created_at", args).fetchall():
        if m := DECISION.match(comment.strip()):
            out[(rid, m.group(2))] = m.group(1)
    return out


def past(user_id: str | None, limit: int = 50, db_path: Path | None = None) -> dict:
    """{"items": [{responseId, at, package, recommendations: [{id, kind, title, decision}]}], "totals": {kind:
    {shown, accepted, dismissed}}}: items newest first (the user's own), totals over everyone."""
    con = feedback._connect(db_path)
    try:
        mine = con.execute("""SELECT response_id, created_at, request, response FROM response_log
                              WHERE kind = 'recommend' AND user_id IS NOT DISTINCT FROM ?
                              ORDER BY created_at DESC LIMIT ?""", [user_id, limit]).fetchall()
        everyone = con.execute("SELECT response_id, response FROM response_log WHERE kind = 'recommend'").fetchall()
        decided = _decisions(con, None)
    finally:
        con.close()
    items = []
    for rid, at, req, resp in mine:
        req, resp = json.loads(req), json.loads(resp)
        items.append({"responseId": rid, "at": at.isoformat() + "Z",
                      "package": {k: req.get(k) for k in ("countryCode", "procGroup", "methodCode", "estimatedValueUsd")},
                      "recommendations": [{"id": r["id"], "kind": r["kind"], "title": r["title"],
                                           "decision": decided.get((rid, r["id"]))}
                                          for r in resp.get("recommendations", [])]})
    totals: dict[str, dict[str, int]] = {}
    for rid, resp in everyone:
        for r in json.loads(resp).get("recommendations", []):
            t = totals.setdefault(r["kind"], {"shown": 0, "accepted": 0, "dismissed": 0})
            t["shown"] += 1
            if d := decided.get((rid, r["id"])):
                t[d] += 1
    return {"items": items, "totals": totals}
