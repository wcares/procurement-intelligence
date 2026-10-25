from procintel.entities import is_org, key, resolve


def test_key_drops_case_punctuation_legal_forms_and_the_ms_prefix():
    assert key("M/S. Sapna Construction Ltd") == key("SAPNA CONSTRUCTION") == "SAPNA CONSTRUCTION"
    assert key("PT. Bumi Harmoni Indoguna") == key("BUMI HARMONI INDOGUNA")
    assert key("Interlock Construction Private Limited") == key("INTERLOCK CONSTRUCTION PVT. LTD")
    assert key("LTD") == ""


def test_people_merge_only_within_a_country_and_organisations_across_countries():
    rows = [(1, "JOHN BANDA", "MW", 1), (2, "JOHN BANDA", "MW", 1), (3, "JOHN BANDA", "ZM", 1),
            (10, "WAPCOS LIMITED", "GM", 1), (11, "WAPCOS LTD", "SZ", 1), (20, "LTD", "KE", 1), (21, "LTD", "KE", 1)]
    ent = resolve(rows)
    assert ent[1] == ent[2] == 1 and ent[3] == 3            # same personal name in another country stays apart
    assert ent[10] == ent[11] == 10                         # an organisation is one firm across countries
    assert ent[20] != ent[21]                               # nothing left after removing legal forms: not merged
    assert is_org("WAPCOS LIMITED") and is_org("UNITED NATIONS WORLD FOOD PROGRAMME") and not is_org("JOHN BANDA")
