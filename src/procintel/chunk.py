"""Section-aware chunking of ICR plain text (the WDS `txturl` output, which is pdf-to-text).

Layout facts this relies on (observed in the ingested ICRs):
  - pages are separated by form feeds and end with an "Official Use Only ... Page N" footer;
  - footnotes sit at the bottom of a page: a line holding only the footnote number, then its text;
  - body paragraphs are numbered ("23.      Given the scope ..."), which gives a stable citation anchor;
  - section headings are short all-caps lines; the table of contents uses dot leaders.

    python -m procintel.chunk          # builds the `chunk` table from `documents`
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from procintel import paths

ROOT = paths.ROOT
DB_PATH = paths.DB_PATH
MAX_CHARS = 1400

_FOOTER_LINE = re.compile(r"^\s*(?:Page \d{1,3}(?: of \d{1,3})?)?\s*$")
_FOOTER_WORDS = re.compile(r"\s*(?:Official Use Only|Strictly Confidential)\s*")
# pdf-to-text sometimes glues the footer's page number onto the next line: "Page 3 enhanced resilience ..."
_PAGE_PREFIX = re.compile(r"^\s*Page \d{1,3}(?: of \d{1,3})?\s+(?=\S)")
_RUNNING_HEADER = re.compile(r"^\s*The World Bank\s*$|ICR DOCUMENT\s*$|\(P\d{6}\)\s*$")
_HEADER_END = re.compile(r"\(P\d{6}\)|ICR DOCUMENT", re.I)
_TEMPLATE_MARK = re.compile(r"@#&OPS~")
HEADER_WINDOW = 5  # the running header (bank name, project title wrapped over 1-3 lines) fits in this many lines
_FOOTNOTE_MARK = re.compile(r"^\s*\d{1,3}\s*$")
FOOTNOTE_MAX_LINES = 15  # a footnote block at the foot of a page is short
_PARA_START = re.compile(r"^\s{0,6}(\d{1,3})\.\s+(\S.*)$")
# "Annex 4. EFFICIENCY ANALYSIS" (mixed-case "Annex") must count too: otherwise its text stays in the previous section,
# often a skipped one (staff and cost tables), and a whole annex of findings is dropped (found 2026-10-25)
_HEADING = re.compile(r"^\s*(?:[IVX]+\.|(?i:annex)\s+\d+\.?|[A-H]\.)?\s*[A-Z][A-Z ,/&()'’:-]{6,90}$")
_TOC = re.compile(r"\.{5,}")
_MOJIBAKE = re.compile(r"�[^\w\s]?�?|�")
_COLUMN_GAP = re.compile(r"\S\s{3,}\S")

# Sections that hold staff lists or cost tables rather than findings.
# The data sheet's parts (staff names, sector percentages, ids, dates; 1,245 chunks, none judged relevant to any of
# the 100 evaluation questions, 2026-10-25) are matched by their whole name. Rating checks read the raw text instead.
SKIP_SECTIONS = re.compile(
    r"task team|bank lending|staff time|supervision cost|data sheet|front matter|abbreviations|acronyms|"
    r"table of contents|^(?:sectors and themes|clients|fiscal year|basic data|adm staff|ratings summary|key dates|"
    r"isr ratings|financing|product information|implementation completion and results report(?: \(icr\))?)$", re.I)


@dataclass
class Chunk:
    section: str
    para: str | None  # numbered paragraph anchor, e.g. "23"
    kind: str  # "text" | "table"
    text: str


def _drop_running_header(lines: list[str]) -> list[str]:
    """Remove each "The World Bank / <project title, possibly wrapped> (P######) ICR Document" block.

    Matched as a block rather than per line, because a wrapped title's first line matches nothing on its own.
    It usually sits at the top of a page, but some extractions have no form feeds, so it is found anywhere:
    a line that is exactly "The World Bank", through the last line carrying the project id or "ICR Document"
    in the unbroken run of lines after it. The run ends at a blank line or a numbered paragraph, so a project
    id in the body text that follows the header is never taken as the header's end."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == "The World Bank":
            run = []
            for j in range(i + 1, min(len(lines), i + HEADER_WINDOW)):
                if not lines[j].strip() or _PARA_START.match(lines[j]):
                    break
                run.append(j)
            ends = [j for j in run if _HEADER_END.search(lines[j])]
            i = (ends[-1] if ends else i) + 1
            continue
        out.append(lines[i])
        i += 1
    return out


def strip_page_furniture(page: str) -> list[str]:
    """Lines of one page without running header, footer and the footnote block above the footer.

    Footer words ("Official Use Only", "Strictly Confidential") appear both in the page footer and as
    standalone lines elsewhere (cover page, top of page), so they are removed line by line; the header block
    and the footnote cut are positional.
    """
    lines = []
    for l in _drop_running_header(page.split("\n")):
        if _TEMPLATE_MARK.search(l):
            continue
        had_footer_words = bool(_FOOTER_WORDS.search(l))
        l = _FOOTER_WORDS.sub(" ", l)
        # a footer-only line is dropped, not left blank: a blank line would end an unnumbered block mid-passage
        if _FOOTER_LINE.match(l) and (l.strip() or had_footer_words):
            continue
        l = _PAGE_PREFIX.sub("", l)
        if _RUNNING_HEADER.search(l):
            continue
        lines.append(l)
    while lines and not lines[-1].strip():
        lines.pop()
    # footnote block: a bare number line in the lower part of the page, preceded by a blank line, with at most
    # FOOTNOTE_MAX_LINES after it. Without that limit a stray number (a page or table number) cut off the rest of the
    # page, up to 80 lines of findings ("Project Costs" in 40109737); keeping a footnote is the lesser harm.
    for i in range(int(len(lines) * 0.4), len(lines)):
        if (_FOOTNOTE_MARK.match(lines[i]) and i > 0 and not lines[i - 1].strip()
                and len(lines) - i <= FOOTNOTE_MAX_LINES):
            return lines[:i]
    return lines


_NUMBER = re.compile(r"^[\(\[]?[-+]?(?:US\$|\$)?\d[\d,]*(?:\.\d+)?%?[\)\]]?[.,;:]?$")
_SENTENCE_END = re.compile(r"[a-z]{3,}[.;] [A-Z]")
_CAPTION = re.compile(r"^\s*(?:TABLE|Table)\s+[A-Z]?\d+(?:\.\d+)*\W*(\w+)")
_CAPTION_VERBS = {"compares", "summarizes", "summarises", "presents", "shows", "lists", "provides", "reports",
                  "describes", "illustrates", "gives", "indicates", "sets", "below", "above", "in", "and"}


def is_flat_table(text: str) -> bool:
    """A table whose columns were flattened into running text by the text export (no column gaps left).

    Mostly numbers (>= 30% of tokens), or >= 20% numbers with no ordinary sentence boundary, or starting with a
    caption ("Table 4. ...", not "Table 4 shows ...") on a chunk that is at least 10% numbers. Set on 60 chunks
    labelled by hand and checked on 30 fresh ones (2026-10-25): flagged chunks were tables, lists, references or
    header data; three captioned prose passages ("Table 6 compares ...") led to the caption verb rule; of 688
    passages judged relevant in the evaluation, a one-sentence result with numbers and a table of written lessons
    led to counting a final full stop and to the 10% floor for captions. Misses: data-sheet sector tables and short
    lists with under 20% numbers."""
    toks = text.split()
    if not toks:
        return False
    num = sum(bool(_NUMBER.match(t)) for t in toks) / len(toks)
    ends = len(_SENTENCE_END.findall(text)) + bool(re.search(r"[a-z]{3,}\.\s*$", text))  # a final full stop counts
    sentences = 100 * ends / len(toks)
    m = _CAPTION.match(text)
    caption = bool(m) and m.group(1).lower() not in _CAPTION_VERBS and num >= 0.1  # tables of words stay searchable
    return num >= 0.3 or (num >= 0.2 and sentences < 0.5) or caption


def _is_table(lines: list[str]) -> bool:
    content = [l for l in lines if l.strip()]
    if not content:
        return False
    tabular = sum(1 for l in content if len(_COLUMN_GAP.findall(l.strip())) >= 2)
    return tabular / len(content) > 0.5


def _clean(s: str) -> str:
    s = _MOJIBAKE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def _split_words(text: str, limit: int) -> list[str]:
    out, cur = [], ""
    for w in text.split():
        if cur and len(cur) + len(w) + 1 > limit:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        out.append(cur)
    return out


def _split_long(text: str, limit: int = MAX_CHARS) -> list[str]:
    if len(text) <= limit:
        return [text]
    out, cur = [], ""
    pieces = []
    for sent in re.split(r"(?<=[.;])\s+(?=[A-Z0-9])", text):
        # a table row run or run-on text has no sentence end to cut at; fall back to word boundaries
        pieces.extend(_split_words(sent, limit) if len(sent) > limit else [sent])
    for sent in pieces:
        if cur and len(cur) + len(sent) + 1 > limit:
            out.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    return out


def chunk_document(text: str) -> list[Chunk]:
    lines: list[str] = []
    for page in text.split("\x0c"):
        lines.extend(strip_page_furniture(page))

    chunks: list[Chunk] = []
    section, para = "Front Matter", None
    last_para: str | None = None  # survives section changes, which reset `para`
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        kind = "table" if _is_table(buf) else "text"
        body = _clean(" ".join(buf))
        buf.clear()
        if len(body) < 80:
            return
        for piece in _split_long(body):
            chunks.append(Chunk(section, para, "table" if kind == "table" or is_flat_table(piece) else "text", piece))

    for line in lines:
        if _TOC.search(line):
            continue
        stripped = line.strip()
        if _HEADING.match(line) and not stripped.endswith(".") and len(stripped) < 95:
            flush()
            section, para = re.sub(r"\s+", " ", stripped).title(), None
            continue
        m = _PARA_START.match(line)
        # paragraph numbers run in sequence through the body; requiring the next number keeps
        # numbered lists inside a paragraph ("1. ...", "2. ...") from being taken as new paragraphs
        # a gap of up to 3 tolerates a paragraph whose number the text extraction mangled
        if m and (last_para is None or 0 < int(m.group(1)) - int(last_para) <= 3):
            flush()
            para = last_para = m.group(1)
            buf.append(m.group(2))
            continue
        if not stripped:
            # blank lines separate un-numbered blocks (tables, bullet groups); numbered paragraphs
            # often contain page breaks, so only flush when the buffer is not a numbered paragraph
            if para is None:
                flush()
            continue
        buf.append(line)
    flush()
    return [c for c in chunks if not SKIP_SECTIONS.search(c.section)]


# Tables and files that refer to passages by chunk id ("<doc_id>:<seq>"). Ids are positions, so a chunker change that adds or
# removes a passage shifts every later id in that report; build() moves what refers to an unchanged text to its new id.
ID_KEYED_TABLES = ("chunk_vec", "chunk_tag", "chunk_problem")
ID_KEYED_FILES = (ROOT / "eval" / "judgments.jsonl", ROOT / "eval" / "precedent_labels.json")


def remap_ids(old: dict[str, str], new: dict[str, str]) -> dict[str, str]:
    """old chunk id -> new chunk id, for texts that moved: the same exact text, found once in the same report."""
    by_text: dict[tuple[str, str], list[str]] = {}
    for cid, text in new.items():
        by_text.setdefault((cid.split(":")[0], text), []).append(cid)
    out = {}
    for cid, text in old.items():
        if new.get(cid) == text:
            continue
        hits = by_text.get((cid.split(":")[0], text), [])
        if len(hits) == 1:
            out[cid] = hits[0]
    return out


def _remap_value(v, mapping: dict[str, str]):
    """Replace every string (value or key) that is an old chunk id in mapping; nothing else can match it."""
    if isinstance(v, str):
        return mapping.get(v, v)
    if isinstance(v, list):
        return [_remap_value(x, mapping) for x in v]
    if isinstance(v, dict):
        return {mapping.get(k, k): _remap_value(x, mapping) for k, x in v.items()}
    return v


def remap_files(mapping: dict[str, str], files=None) -> int:
    """Rewrite chunk ids in the evaluation files (JSON lines or JSON); returns how many values changed."""
    changed = 0
    for f in ID_KEYED_FILES if files is None else files:
        if not f.exists() or not mapping:
            continue
        if f.suffix == ".jsonl":
            rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
            out = [_remap_value(r, mapping) for r in rows]
            changed += sum(a != b for a, b in zip(rows, out))
            f.write_text("".join(json.dumps(r) + "\n" for r in out))
        else:
            data = json.loads(f.read_text())
            out = _remap_value(data, mapping)
            changed += json.dumps(data) != json.dumps(out)
            f.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    return changed


def build(db_path: Path = DB_PATH) -> None:
    con = duckdb.connect(str(db_path))
    has_chunks = con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'chunk'").fetchone()
    old = dict(con.execute("SELECT chunk_id, text FROM chunk").fetchall()) if has_chunks else {}
    rows = []
    for doc_id, text in con.execute("SELECT doc_id, text FROM documents").fetchall():
        for i, c in enumerate(chunk_document(text)):
            rows.append({"chunk_id": f"{doc_id}:{i}", "doc_id": doc_id, "seq": i, "section": c.section,
                         "para": c.para, "kind": c.kind, "text": c.text, "n_chars": len(c.text)})
    df = pd.DataFrame(rows)
    con.execute("CREATE OR REPLACE TABLE chunk AS SELECT * FROM df")
    mapping = remap_ids(old, dict(zip(df.chunk_id, df.text)))
    if mapping:  # vectors and tags of moved texts follow them, so only new texts are embedded and tagged again
        con.execute("CREATE OR REPLACE TEMP TABLE id_map (old_id VARCHAR, new_id VARCHAR)")
        con.executemany("INSERT INTO id_map VALUES (?, ?)", list(mapping.items()))
        for t in ID_KEYED_TABLES:
            if con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = ?", [t]).fetchone():
                # rows whose own id is now another text's become stale first, then moved rows take their new ids
                con.execute(f"DELETE FROM {t} WHERE chunk_id IN (SELECT new_id FROM id_map) "
                            f"AND chunk_id NOT IN (SELECT old_id FROM id_map)")
                con.execute(f"UPDATE {t} SET chunk_id = m.new_id FROM id_map m WHERE {t}.chunk_id = m.old_id")
    files = remap_files(mapping)
    print(f"chunk: {len(df)} rows from {df.doc_id.nunique()} documents; {len(mapping)} passages moved to a new id "
          f"(vectors, tags and {files} evaluation labels follow them)")
    con.close()


if __name__ == "__main__":
    build()
