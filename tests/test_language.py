import duckdb

from procintel.ingestion import language

EN = "The project rehabilitated feeder roads and procurement of civil works was delayed by re-bidding of two lots. " * 12
FR = "Le projet a réhabilité des routes rurales et la passation des marchés de travaux a été retardée par un nouvel appel d'offres. " * 12
ES = "El proyecto rehabilitó caminos rurales y la adquisición de obras civiles se retrasó por una nueva licitación de dos lotes. " * 12
ZH = "该项目修复了农村道路，土建工程的采购因重新招标而延误，两个标段的合同授予推迟了。" * 30
TABLE = "500 300 12.5 14.2 18.9 2021 2022 2023 " * 60


def test_the_language_of_a_report_is_the_one_most_of_its_text_is_in():
    for text, want in ((EN, "en"), (FR, "fr"), (ES, "es"), (ZH, "zh")):
        lang, conf = language.detect(text)
        assert lang == want and conf > 0.9
    assert language.detect(EN + FR * 3)[0] == "fr"                       # a report mostly in French with some English
    assert language.detect(TABLE) == ("en", 0.0)                         # only numbers: the default, no confidence
    assert language.detect("short") == ("en", 0.0) and language.detect("court", default="fr") == ("fr", 0.0)


def test_settings_come_from_the_table_and_a_json_file_can_add_a_language(tmp_path, monkeypatch):
    from procintel.core import paths
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(language, "_loaded", None)
    (tmp_path / "languages.json").write_text('{"fr": {"name": "Français"}, "xx": {"name": "Xish", "cjk": true}}')
    assert language.settings("fr") == {"name": "Français", "stem": "french", "sentence": ".;?!", "cjk": False}
    assert language.settings("xx")["cjk"] is True and language.settings("xx")["stem"] is None
    assert language.settings("qq")["name"] == "qq" and language.settings(None)["name"] == "English"
    monkeypatch.setattr(language, "_loaded", None)


def test_build_detects_new_and_changed_reports_only(tmp_path):
    db = tmp_path / "t.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE documents (doc_id VARCHAR, text VARCHAR)")
    con.executemany("INSERT INTO documents VALUES (?, ?)", [("a", EN), ("b", FR)])
    assert language.build(con=con) == {"en": 1, "fr": 1}
    con.execute("UPDATE doc_lang SET lang = 'xx' WHERE doc_id = 'a'")      # an unchanged text is not detected again
    language.build(con=con)
    assert language.of_documents(con) == {"a": "xx", "b": "fr"}
    con.execute("UPDATE documents SET text = ? WHERE doc_id = 'a'", [ES])
    con.execute("DELETE FROM documents WHERE doc_id = 'b'")
    assert language.build(con=con) == {"es": 1}
    con.close()


def test_passages_get_their_own_language_and_short_ones_their_reports():
    assert language.passage_lang(FR[:400], "en") == "fr"
    assert language.passage_lang("Roads 500", "fr") == "fr"                          # too short to tell
    db = duckdb.connect()
    db.execute("CREATE TABLE documents (doc_id VARCHAR, text VARCHAR)")
    db.execute("INSERT INTO documents VALUES ('d', ?)", [EN * 3 + FR])
    db.execute("CREATE TABLE chunk (chunk_id VARCHAR, doc_id VARCHAR, text VARCHAR)")
    db.executemany("INSERT INTO chunk VALUES (?, 'd', ?)", [("d:0", EN[:500]), ("d:1", FR[:500]), ("d:2", "Total 1,200")])
    language.build(con=db)
    assert language.build_chunks(db) == {"en": 2, "fr": 1}
    assert dict(db.execute("SELECT chunk_id, lang FROM chunk_lang").fetchall()) == {"d:0": "en", "d:1": "fr", "d:2": "en"}


def test_keyword_text_pairs_characters_of_scripts_without_spaces_and_keeps_others():
    import re
    assert language.keyword_text("土建工程 delays") == " 土建 建工 工程  delays"
    assert language.keyword_text("Delays in civil works") == "Delays in civil works"
    words = re.findall(language.TOKEN_PATTERN, "सिविल कार्यों में देरी, civil works")
    assert words == ["सिविल", "कार्यों", "में", "देरी", "civil", "works"]               # vowel signs stay in the word
