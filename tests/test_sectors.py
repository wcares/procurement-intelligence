from procintel.answering.retrieve import Hit
from procintel.ingestion import sectors
from procintel.prediction import assess


def test_families_map_detailed_sectors_to_major_ones():
    assert sectors.family("Public Administration - Education") == "Education"
    assert sectors.family("Rural and Inter-Urban Roads") == sectors.family("Aviation") == "Transportation"
    assert sectors.family("Health") == "Health" and sectors.family("") is None and sectors.family("Unknown") is None


def hit(i, pid, cc):
    return Hit(chunk_id=f"d{i}:1", doc_id=f"d{i}", title="T", doc_type="ICR", url="u", section="Lessons", para="1",
               kind="text", text=f"lesson {i}", project_id=pid, project_name="P", country_code=cc, score=1.0)


def test_widened_precedents_put_the_same_sector_family_first_and_say_so(monkeypatch):
    other = [hit(1, "P1", "BD"), hit(2, "P2", "BD"), hit(3, "P3", "BD")]

    class R:
        project_family = {"P1": "Health", "P2": "Transportation", "P3": "Transportation"}
        rating_conflicts = {}

        def search(self, q, k, country=None, proc_group=None):
            return [] if country else other            # nothing in the asked country: the search widens
    monkeypatch.setattr(assess, "_relevant", lambda hits, package: (hits, 0))
    precs, widened, _, _ = assess.precedents(R(), "TV", "CW", "rural roads", "Rural and Inter-Urban Roads")
    assert widened and [p["citation"]["projectId"] for p in precs] == ["P2", "P3", "P1"]
    assert "same sector family: Transportation" in precs[0]["matchedOn"]
    assert not any(m.startswith("same sector family") for m in precs[2]["matchedOn"])


def test_country_lessons_from_another_sector_family_bring_in_same_family_lessons_first(monkeypatch):
    own = [hit(1, "P1", "TV"), hit(2, "P1", "TV"), hit(3, "P1", "TV")]            # Tuvalu's ICT project
    other = [hit(4, "P4", "BD"), hit(5, "P5", "KE")]

    class R:
        project_family = {"P1": "Information and Communications Technologies", "P4": "Transportation", "P5": "Health"}
        rating_conflicts = {}

        def search(self, q, k, country=None, proc_group=None):
            return own if country else own + other
    monkeypatch.setattr(assess, "_relevant", lambda hits, package: (hits, 0))
    precs, widened, _, _ = assess.precedents(R(), "TV", "CW", "rural roads", "Rural and Inter-Urban Roads")
    assert widened and [p["citation"]["projectId"] for p in precs] == ["P4", "P1", "P1", "P1"]   # health one not added
    precs, widened, _, _ = assess.precedents(R(), "TV", "CW", "rural roads", "")                  # no sector: as before
    assert not widened and [p["citation"]["projectId"] for p in precs] == ["P1", "P1", "P1"]
