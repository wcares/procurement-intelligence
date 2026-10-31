"""Where a project is, for the map: table project_place (project_id, level, place, lat, lon, source, chunk_id).

Level "country" is what the data has today: the projects API gives no locations (its `locations` field is empty for
every tracked project, checked 2026-10-31), so a project is pinned at its country's capital as the World Bank country
API gives it (latitude/longitude of the capital city), and the map says it is country level. Rows of other levels
(a district or a site named in a report, with the passage that names it in chunk_id) can be added by another source
later; build() only replaces the country rows.

    python -m procintel.monitoring.places        # (re)build the country rows
"""
from __future__ import annotations

from pathlib import Path

from procintel.core import db, paths
from procintel.ingestion.wb_client import INDICATORS, WBClient

DB_PATH = paths.DB_PATH
SOURCE = "World Bank country API: capital city"


def ensure(con) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS project_place (project_id VARCHAR, level VARCHAR, place VARCHAR, lat DOUBLE,
                   lon DOUBLE, source VARCHAR, chunk_id VARCHAR)""")


def countries(client: WBClient | None = None) -> dict[str, dict]:
    """ISO2 code -> {name, capital, lat, lon} for every country with a capital (aggregates have none)."""
    d = (client or WBClient())._get(f"{INDICATORS}/country", {"format": "json", "per_page": 400})
    out = {}
    for c in (d[1] if isinstance(d, list) and len(d) > 1 else []):
        try:
            lat, lon = float(c["latitude"]), float(c["longitude"])
        except (TypeError, ValueError, KeyError):
            continue
        out[c["iso2Code"]] = {"name": c["name"], "capital": c["capitalCity"], "lat": lat, "lon": lon}
    return out


def build(db_path: Path = DB_PATH, client: WBClient | None = None) -> dict:
    """Country rows for every tracked project; returns how many were pinned and which country codes had no capital
    (regional and multi-country projects)."""
    where = countries(client)
    con = db.connect(db_path)
    try:
        ensure(con)
        con.execute("DELETE FROM project_place WHERE level = 'country'")
        rows, missing = [], set()
        for pid, code in con.execute("SELECT project_id, country_code FROM projects").fetchall():
            c = where.get(code or "")
            if not c:
                missing.add(code)
                continue
            rows.append((pid, "country", f"{c['capital']}, {c['name']}", c["lat"], c["lon"], SOURCE, None))
        if rows:
            con.executemany("INSERT INTO project_place VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        return {"pinned": len(rows), "no_location": sorted(m for m in missing if m)}
    finally:
        con.close()


def of_projects(project_ids: list[str], db_path: Path = DB_PATH) -> dict[str, list[dict]]:
    """project_id -> its places (most precise level first); {} when the table was never built."""
    con = db.connect(db_path, read_only=True)
    try:
        if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'project_place'").fetchone():
            return {}
        out: dict[str, list[dict]] = {}
        for pid, level, place, lat, lon, source, chunk_id in con.execute(
                """SELECT project_id, level, place, lat, lon, source, chunk_id FROM project_place
                   WHERE project_id IN (SELECT unnest(?)) ORDER BY project_id, level = 'country', place""",
                [project_ids]).fetchall():
            out.setdefault(pid, []).append({"level": level, "place": place, "lat": lat, "lon": lon, "source": source,
                                            "chunkId": chunk_id})
        return out
    finally:
        con.close()


if __name__ == "__main__":
    print(build())
