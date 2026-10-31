import duckdb

from procintel.monitoring import places


class FakeClient:
    def _get(self, url, params=None):
        return [{"page": 1}, [
            {"iso2Code": "KE", "name": "Kenya", "capitalCity": "Nairobi", "latitude": "-1.27975", "longitude": "36.8126"},
            {"iso2Code": "ZG", "name": "Sub-Saharan Africa", "capitalCity": "", "latitude": "", "longitude": ""}]]


def test_projects_are_pinned_at_their_countrys_capital_and_regional_ones_are_reported(tmp_path):
    db = tmp_path / "t.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE projects AS SELECT * FROM (VALUES ('P1', 'KE'), ('P2', '1W')) t(project_id, country_code)")
    con.execute("CREATE TABLE project_place (project_id VARCHAR, level VARCHAR, place VARCHAR, lat DOUBLE, lon DOUBLE, "
                "source VARCHAR, chunk_id VARCHAR)")
    con.execute("INSERT INTO project_place VALUES ('P1', 'site', 'Kisumu bridge', -0.1, 34.7, 'report', 'd:4')")
    con.close()
    assert places.build(db, FakeClient()) == {"pinned": 1, "no_location": ["1W"]}
    assert places.build(db, FakeClient())["pinned"] == 1                        # rebuilding replaces, never doubles
    got = places.of_projects(["P1", "P2"], db)
    assert list(got) == ["P1"]
    assert [(p["level"], p["place"]) for p in got["P1"]] == [("site", "Kisumu bridge"), ("country", "Nairobi, Kenya")]
    assert got["P1"][1]["lat"] == -1.27975 and got["P1"][0]["chunkId"] == "d:4"   # other sources' rows are kept
