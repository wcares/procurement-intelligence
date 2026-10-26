"""What a document is. The document's own title decides when its opening names a kind (the phrase that appears
first wins: an ISR may mention the ICR it leads to); otherwise the decision model (procintel.core.decide) is asked
one fixed-option question, and below MIN_CONFIDENCE the document goes to review. The title is trusted over the model:
on 2026-10-25 the model called an ISR (titled "Implementation Status & Results Report") a completion report at 84%.
Whether a classification is "titled" matters downstream: only a titled completion report is added to the evidence.
"""
from __future__ import annotations

import re

from procintel.core import decide

TYPES = {
    "completion_report": "an Implementation Completion and Results Report (ICR): a closed project's evaluation",
    "supervision_report": "an Implementation Status and Results Report (ISR) or supervision mission aide-memoire",
    "procurement_notice": "a procurement notice: invitation for bids, request for expressions of interest, award notice",
    "contract": "a contract or contract agreement between a purchaser and a supplier or contractor",
    "amendment": "a contract amendment, variation order or project restructuring paper",
    "other": "something else",
}
QUESTION = "What kind of World Bank project document is this? " + "; ".join(f"{k}: {v}" for k, v in TYPES.items())
OPENING = 3000          # characters read by the model
MIN_CONFIDENCE = 0.6
KEYWORDS = [            # (type, title phrase in the opening); the earliest match decides
    ("completion_report", r"implementation completion (?:and|&) results report"),
    ("supervision_report", r"implementation status (?:and|&) results report|aide[- ]m[ée]moire"),
    ("amendment", r"\bamendment (?:no\.?|number)|variation order|restructuring paper"),
    ("procurement_notice", r"invitation for bids|request for (?:bids|proposals|expressions? of interest)|"
                           r"specific procurement notice|contract award notice"),
    ("contract", r"\bcontract agreement\b|this contract is made|form of contract"),
]


def by_keywords(text: str) -> str:
    head = text[:OPENING]
    found = [(m.start(), t) for t, pat in KEYWORDS if (m := re.search(pat, head, re.I))]
    return min(found)[1] if found else "other"


def _model(text: str) -> dict[str, float] | None:
    if not decide.available():
        return None
    return decide.choices(f"Document opening: {text[:OPENING]}", {"kind": (QUESTION, list(TYPES))})["kind"]


def classify(text: str) -> dict:
    """{"type", "confidence", "method", "titled", "scores"}. type "other" with method "review" when nothing is sure."""
    keyword = by_keywords(text)
    try:
        scores = _model(text)
    except Exception as e:  # the model being down must not lose the upload
        scores, failed = None, str(e)
    else:
        failed = None
    best = max(scores, key=scores.get) if scores else None
    if keyword != "other":
        note = ""
        if failed:
            note = f"; decision model failed: {failed}"
        elif best and best != keyword:
            note = f"; the decision model said {best.replace('_', ' ')} ({scores[best]:.0%})"
        return {"type": keyword, "confidence": round(scores[keyword], 3) if scores else None,
                "method": "title" + note, "titled": True, "scores": scores}
    if scores and scores[best] >= MIN_CONFIDENCE:
        return {"type": best, "confidence": round(scores[best], 3), "method": "decision model", "titled": False,
                "scores": scores}
    return {"type": "other", "confidence": round(scores[best], 3) if scores else None,
            "method": "review" if scores else "no title phrase" + (f"; decision model failed: {failed}" if failed else ""),
            "titled": False, "scores": scores}
