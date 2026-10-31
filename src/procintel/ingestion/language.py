"""What language each report is written in, and the few language-dependent settings the pipeline needs.

The language of a report is detected from its text (py3langid, offline, no model download): up to SAMPLES pieces spread
over the text are classified and the language with the most pieces wins, its share of the pieces is the confidence. A
report whose source states its language (the World Bank documents API has a `lang` label) can pass it in instead. The
result is kept in table `doc_lang` (doc_id, lang, confidence, source, text_hash); passages inherit their report's language.

Language-dependent behaviour is looked up here, so a new language is an entry in LANGUAGES (or in data/languages.json,
which overrides and extends the built-in entries) and not a code change:

    name       for messages and prompts ("Answer in French")
    stem       the PyStemmer algorithm for keyword search and sentence matching, or None
    sentence   sentence-end marks (used by the passage splitter)
    cjk        True for scripts written without spaces between words (keyword search indexes characters)

Detection candidates are limited to the languages listed (PROCINTEL_LANGUAGES, comma-separated codes, overrides the list)
because a detector offered 97 languages confuses short English with Nigerian Pidgin.

    python -m procintel.ingestion.language        # detect the language of every report not detected yet
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path

from procintel.core import db, paths

DB_PATH = paths.DB_PATH
SAMPLES = 12
SAMPLE_CHARS = 800
PASSAGE_CONFIDENCE = 0.8  # below this a passage keeps its report's language
MIN_CHARS = 60            # a text shorter than this is not classified: the default language is used
DEFAULT = "en"

LANGUAGES: dict[str, dict] = {
    "en": {"name": "English", "stem": "english", "sentence": ".;?!", "cjk": False},
    "fr": {"name": "French", "stem": "french", "sentence": ".;?!", "cjk": False},
    "es": {"name": "Spanish", "stem": "spanish", "sentence": ".;?!", "cjk": False},
    "pt": {"name": "Portuguese", "stem": "portuguese", "sentence": ".;?!", "cjk": False},
    "ar": {"name": "Arabic", "stem": "arabic", "sentence": ".;?!؟؛", "cjk": False},
    "ru": {"name": "Russian", "stem": "russian", "sentence": ".;?!", "cjk": False},
    "zh": {"name": "Chinese", "stem": None, "sentence": "。；？！.;?!", "cjk": True},
    "ja": {"name": "Japanese", "stem": None, "sentence": "。？！.?!", "cjk": True},
    "hi": {"name": "Hindi", "stem": None, "sentence": "।?!.", "cjk": False},
    "id": {"name": "Indonesian", "stem": "indonesian", "sentence": ".;?!", "cjk": False},
    "tr": {"name": "Turkish", "stem": "turkish", "sentence": ".;?!", "cjk": False},
    "de": {"name": "German", "stem": "german", "sentence": ".;?!", "cjk": False},
    "sw": {"name": "Swahili", "stem": None, "sentence": ".;?!", "cjk": False},
    "vi": {"name": "Vietnamese", "stem": None, "sentence": ".;?!", "cjk": False},
    "bn": {"name": "Bengali", "stem": None, "sentence": "।?!.", "cjk": False},
    "ne": {"name": "Nepali", "stem": "nepali", "sentence": "।?!.", "cjk": False},
    "fa": {"name": "Persian", "stem": None, "sentence": ".;?!؟", "cjk": False},
    "uk": {"name": "Ukrainian", "stem": None, "sentence": ".;?!", "cjk": False},
    "th": {"name": "Thai", "stem": None, "sentence": ".?!", "cjk": False},
    "ko": {"name": "Korean", "stem": None, "sentence": ".?!", "cjk": False},
}
_loaded: dict[str, dict] | None = None

# Keyword search: a word is a run of letters, digits and the combining vowel signs of Indic, Arabic and Hebrew scripts
# (the default \w pattern cuts Hindi words at every vowel sign). Scripts written without spaces between words
# (Chinese, Japanese, Thai, and Korean syllable runs) are indexed as overlapping character pairs.
TOKEN_PATTERN = r"(?u)[\w\u0300-\u036f\u0591-\u05c7\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0900-\u0dff\u0e00-\u0e7f]{2,}"
_NO_SPACES = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\u0e00-\u0e7f]{2,}")


def keyword_text(text: str) -> str:
    """The text as keyword search should index it: runs of a script without spaces become overlapping character pairs."""
    return _NO_SPACES.sub(lambda m: " " + " ".join(m.group(0)[i:i + 2] for i in range(len(m.group(0)) - 1)) + " ", text)


def languages() -> dict[str, dict]:
    """The built-in languages overlaid with data/languages.json (a code -> entry map; an entry may be partial)."""
    global _loaded
    if _loaded is None:
        out = {k: dict(v) for k, v in LANGUAGES.items()}
        f = paths.DATA_DIR / "languages.json"
        if f.exists():
            for code, entry in json.loads(f.read_text()).items():
                out[code] = {**out.get(code, {"name": code, "stem": None, "sentence": ".;?!", "cjk": False}), **entry}
        _loaded = out
    return _loaded


def settings(lang: str | None) -> dict:
    """The entry of `lang`, or a neutral entry for a language not listed (no stemming, common sentence marks)."""
    return languages().get(lang or DEFAULT) or {"name": lang or DEFAULT, "stem": None, "sentence": ".;?!", "cjk": False}


def candidates() -> list[str]:
    env = os.environ.get("PROCINTEL_LANGUAGES", "").strip()
    return [c.strip() for c in env.split(",") if c.strip()] if env else sorted(languages())


_ready = False


def _classifier():
    global _ready
    import py3langid
    if not _ready:
        py3langid.set_languages(candidates())
        _ready = True
    return py3langid


def _conf(text: str) -> tuple[str, float]:
    """(language, probability) of one piece of text, the scores turned into probabilities."""
    ranked = _classifier().rank(text)
    scores = [s for _, s in ranked]
    top = max(scores)
    exp = [math.exp(s - top) for s in scores]
    return ranked[0][0], exp[0] / sum(exp)


def detect(text: str, default: str = DEFAULT) -> tuple[str, float]:
    """(language, confidence) of a report: the language most of its sampled pieces are in. A text with no letters to
    classify gets `default` with confidence 0."""
    text = " ".join(text.split())
    if len(text) < MIN_CHARS:
        return default, 0.0
    step = max(SAMPLE_CHARS, len(text) // SAMPLES)
    pieces = [text[i:i + SAMPLE_CHARS] for i in range(0, max(1, len(text) - MIN_CHARS), step)][:SAMPLES]
    votes: dict[str, int] = {}
    for p in pieces:
        if sum(c.isalpha() for c in p) < MIN_CHARS // 2:      # a piece of numbers (a table) says nothing
            continue
        lang, p_ = _conf(p)
        if p_ >= 0.5:
            votes[lang] = votes.get(lang, 0) + 1
    if not votes:
        return default, 0.0
    lang = max(votes, key=votes.get)
    return lang, votes[lang] / sum(votes.values())


def passage_lang(text: str, default: str = DEFAULT) -> str:
    """The language of one passage: its own when it is long enough and the classifier is sure, else `default` (the report's)."""
    if len(text) < MIN_CHARS or sum(c.isalpha() for c in text) < MIN_CHARS // 2:
        return default
    lang, p = _conf(text)
    return lang if p >= PASSAGE_CONFIDENCE else default


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def ensure(con) -> None:
    con.execute("CREATE TABLE IF NOT EXISTS doc_lang (doc_id VARCHAR, lang VARCHAR, confidence DOUBLE, source VARCHAR, "
                "text_hash VARCHAR)")


def build(db_path: Path = DB_PATH, con=None) -> dict:
    """Detect the language of every report whose text is new or changed; returns a count per language of all reports."""
    own = con is None
    con = con or db.connect(db_path)
    try:
        ensure(con)
        have = {d: h for d, h in con.execute("SELECT doc_id, text_hash FROM doc_lang").fetchall()}
        for doc_id, text in con.execute("SELECT doc_id, text FROM documents").fetchall():
            h = _hash(text or "")
            if have.get(doc_id) == h:
                continue
            lang, conf = detect(text or "")
            con.execute("DELETE FROM doc_lang WHERE doc_id = ?", [doc_id])
            con.execute("INSERT INTO doc_lang VALUES (?, ?, ?, 'detected', ?)", [doc_id, lang, conf, h])
        con.execute("DELETE FROM doc_lang WHERE doc_id NOT IN (SELECT doc_id FROM documents)")
        return dict(con.execute("SELECT lang, count(*) FROM doc_lang GROUP BY 1 ORDER BY 2 DESC").fetchall())
    finally:
        if own:
            con.close()


def build_chunks(con) -> dict:
    """Table chunk_lang (chunk_id, lang): each passage's own language, its report's when it cannot tell (a report in one
    language with a French annex gets French passages for the annex). Rebuilt whole: classifying all passages takes seconds.
    Returns a passage count per language."""
    docs = of_documents(con)
    rows = [(cid, passage_lang(text, docs.get(doc, DEFAULT)))
            for cid, doc, text in con.execute("SELECT chunk_id, doc_id, text FROM chunk").fetchall()]
    con.execute("CREATE OR REPLACE TABLE chunk_lang (chunk_id VARCHAR, lang VARCHAR)")
    con.executemany("INSERT INTO chunk_lang VALUES (?, ?)", rows)
    out: dict[str, int] = {}
    for _, lang in rows:
        out[lang] = out.get(lang, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def of_documents(con) -> dict[str, str]:
    """doc_id -> language for the reports detected so far ({} before any detection)."""
    if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'doc_lang'").fetchone():
        return {}
    return dict(con.execute("SELECT doc_id, lang FROM doc_lang").fetchall())


if __name__ == "__main__":
    print(build())
