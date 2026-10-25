"""Yearly exchange rates to convert contract prices to USD.

Source: World Bank indicator PA.NUS.FCRF, official exchange rate in local currency units per USD (period average).
A currency is looked up under its issuing country, taken from the first two letters of its ISO 4217 code (IDR -> ID),
except shared currencies, which use a member's or the area's series (EUR -> EMU, XOF -> SEN, XAF -> CMR).
Old units after a redenomination are scaled (REDENOMINATED). Award notices that state both a USD and a local amount give an
independent rate; `check()` compares the two, but many such notices split one price across currencies, so a mismatch
there is not proof of a wrong rate. Converted values were also compared with USD-priced awards of the same method:
apart from SLL (fixed by the factor), large ratios came from genuinely large or small contracts (KZT, GEL highway
contracts; MZN small medical-goods lots), checked against the notice text.

    python -m procintel.fx            # builds table fx, then prints the check
"""
from __future__ import annotations

import re
from pathlib import Path
from statistics import median

import duckdb

from procintel import parse_notice as pn
from procintel.wb_client import WBClient

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "procintel.duckdb"
INDICATOR = "PA.NUS.FCRF"
SHARED = {"EUR": "EMU", "XOF": "SEN", "XAF": "CMR", "XCD": "DMA"}
# Old currency units after a redenomination: the indicator reports every year in the new unit (1 SLE = 1,000 SLL from
# 2022; 1 STN = 1,000 STD from 2018), so amounts in the old unit need the rate times the factor. Found by SLL awards
# converting to ~700x the value of comparable USD-priced awards.
REDENOMINATED = {"SLL": 1000.0, "STD": 1000.0}


def issuer(currency: str) -> str:
    return SHARED.get(currency, currency[:2])


def build(db_path: Path = DB_PATH) -> None:
    con = duckdb.connect(str(db_path))
    currencies = [c for (c,) in con.execute(
        "SELECT DISTINCT price_currency FROM notice_m WHERE price_currency IS NOT NULL AND price_currency <> 'USD'").fetchall()]
    client = WBClient()
    rows, missing = [], []
    for cur in sorted(currencies):
        series = [(int(r["date"]), float(r["value"])) for r in client.indicator(issuer(cur), INDICATOR, per_page=80)
                  if r.get("value") is not None]
        if not series:
            missing.append(cur)
        rows += [(cur, issuer(cur), y, v * REDENOMINATED.get(cur, 1.0)) for y, v in series]
    con.execute("CREATE OR REPLACE TABLE fx (currency VARCHAR, source_country VARCHAR, year INTEGER, lcu_per_usd DOUBLE)")
    con.executemany("INSERT INTO fx VALUES (?, ?, ?, ?)", rows)
    con.close()
    print(f"fx: {len(currencies) - len(missing)} of {len(currencies)} currencies have rates ({len(rows)} currency-years); "
          f"no series for: {', '.join(missing) or 'none'}")


def rates(con: duckdb.DuckDBPyConnection) -> dict[str, dict[int, float]]:
    if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'fx'").fetchone():
        return {}
    out: dict[str, dict[int, float]] = {}
    for cur, year, v in con.execute("SELECT currency, year, lcu_per_usd FROM fx").fetchall():
        out.setdefault(cur, {})[year] = v
    return out


def to_usd(amount: float | None, currency: str | None, year: int | None, table: dict[str, dict[int, float]]) -> float | None:
    """Amount in USD using the rate of the given year, else the nearest year within 2; None if not convertible."""
    if amount is None or currency is None or year is None:
        return None
    if currency == "USD":
        return amount
    series = table.get(currency)
    if not series:
        return None
    nearest = min(series, key=lambda y: abs(y - year))
    return amount / series[nearest] if abs(nearest - year) <= 2 else None


def check(db_path: Path = DB_PATH) -> list[tuple[str, int, float, float]]:
    """Notices stating a USD and a local amount: (currency, n, median implied rate, median WDI rate) per currency."""
    con = duckdb.connect(str(db_path), read_only=True)
    table = rates(con)
    pairs: dict[str, list[tuple[float, float]]] = {}
    for text, year in con.execute("""SELECT n.text, year(m.notice_date::DATE) FROM notices n JOIN notice_m m USING (notice_id)
                                     WHERE m.notice_type = 'Contract Award' AND n.text LIKE '%USD%'""").fetchall():
        m = pn._PRICE_BLOCK.search(text)
        found = pn._MONEY.findall(m.group(1)) if m else []
        usd = [float(a.replace(",", "")) for c, a in found if c == "USD"]
        local = [(c, float(a.replace(",", ""))) for c, a in found if c != "USD"]
        if len(usd) == 1 and len(local) == 1 and usd[0] > 0 and local[0][0] in table:
            cur, amt = local[0]
            wdi = table[cur].get(year)
            if wdi:
                pairs.setdefault(cur, []).append((amt / usd[0], wdi))
    con.close()
    return sorted(((c, len(v), median(a for a, _ in v), median(w for _, w in v)) for c, v in pairs.items()),
                  key=lambda r: -r[1])


if __name__ == "__main__":
    build()
    print("currency   n   implied rate (notice)   WDI rate   ratio")
    for cur, n, implied, wdi in check():
        print(f"{cur:8s} {n:4d}   {implied:18.2f}   {wdi:10.2f}   {implied / wdi:5.2f}")
