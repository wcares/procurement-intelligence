"""Field extraction from the flattened text of a World Bank procurement notice.

The text is the notice HTML flattened with ' | ' between elements (see ingest.notice_row).
Patterns were written against notices in data/procintel.duckdb; see tests/test_parse_notice.py.
"""
from __future__ import annotations

import re
from datetime import date

_UNIT_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}

# Two labels are used for the same event depending on notice template.
_DATE_LABELS = (
    r"Date Notification of Award Issued",
    r"Contract Signature Date",
)
_DATE = re.compile(
    r"(?:%s)\s*\|?\s*(?:\(YYYY/MM/DD\)\s*\|?\s*)?(\d{4}/\d{2}/\d{2})" % "|".join(_DATE_LABELS)
)
_DURATION = re.compile(r"Duration of Contract\s*\|?\s*(\d+)\s*(Day|Week|Month|Year)", re.I)
_VERSION = re.compile(r"Notice Version No:\s*\|?\s*(\d+)")

# "Signed Contract price | USD 953944.91; ARS 170134294.86"
_PRICE_BLOCK = re.compile(r"Signed Contract price\s*\|\s*([^|]+)", re.I)
_MONEY = re.compile(r"\b([A-Z]{3})\s+([\d,]+(?:\.\d+)?)")

_SUPPLIER_START = re.compile(r"Awarded (?:Bidder|Firm|Consultant)\(?s?\)?(?:/Individual)?:\s*\|", re.I)
# One '|'-delimited token per supplier: "NAME (firm_id)". Splitting on '|' first keeps parentheses
# that are part of the name, e.g. "ABC (INDIA) LTD (12345)" -> name "ABC (INDIA) LTD".
_SUPPLIER_TOKEN = re.compile(r"(.+?)\s*\((\d{4,9})\)\.?")
_SUPPLIER_END = re.compile(r"\|\s*(?:Bid Price|Evaluated|Signed Contract|Scores|Contract Price|Minimum Qualifying)", re.I)


def award_date(text: str) -> date | None:
    m = _DATE.search(text)
    if not m:
        return None
    y, mo, d = (int(x) for x in m.group(1).split("/"))
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def duration_days(text: str) -> int | None:
    m = _DURATION.search(text)
    return int(m.group(1)) * _UNIT_DAYS[m.group(2).lower()] if m else None


def notice_version(text: str) -> int | None:
    m = _VERSION.search(text)
    return int(m.group(1)) if m else None


def signed_price(text: str) -> tuple[str, float] | None:
    """(currency, amount). Prefers USD when several currencies are listed, else the first."""
    m = _PRICE_BLOCK.search(text)
    if not m:
        return None
    found = [(c, float(a.replace(",", ""))) for c, a in _MONEY.findall(m.group(1))]
    if not found:
        return None
    return next((f for f in found if f[0] == "USD"), found[0])


def suppliers(text: str) -> list[tuple[str, int]]:
    """[(name, firm_id)] for awarded firms that carry a Bank firm id. Notices without ids yield []."""
    s = _SUPPLIER_START.search(text)
    if not s:
        return []
    tail = text[s.end():]
    e = _SUPPLIER_END.search(tail)
    block = tail[: e.start()] if e else tail[:1500]
    out, seen = [], set()
    for tok in (t.strip() for t in block.split("|")):
        m = _SUPPLIER_TOKEN.fullmatch(tok)
        if not m:
            continue
        name = re.sub(r"\s+", " ", m.group(1)).strip(" .-,;")
        fid = int(m.group(2))
        if name and fid not in seen:
            seen.add(fid)
            out.append((name, fid))
    return out
