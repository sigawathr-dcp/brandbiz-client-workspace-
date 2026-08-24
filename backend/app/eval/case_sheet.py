"""
app/eval/case_sheet.py

Read "Case studies for DSMEs.xlsx" - the curated case library - into typed
records, and resolve each row to the corpus file it describes.

Why a hand-rolled .xlsx reader: neither openpyxl nor pandas is a dependency
of this service, and adding one so an offline corpus build can run once a
quarter is a poor trade. An .xlsx is a zip of XML; the subset this one file
uses (shared strings, inline strings, sparse cells) is small enough to read
directly, and `read_sheet()` is deliberately minimal rather than general -
it will not cope with formulas, dates, or styling, and does not pretend to.

The identity problem is the interesting part. The spreadsheet and the
corpus name the same campaign differently:

  - Titles drift ("BENOVA GOBAL" in the sheet is "case-study_benova_-
    rejuvenus.md" on disk, whose title is the campaign's, not the client's).
  - Source URLs are the stable key, EXCEPT where the sheet has a
    copy-paste error (row 1 carries row 6's URL) or no URL at all.

So `resolve_filenames()` matches on the portfolio-URL slug first, falls
back to exact title, and reports whatever it could not place instead of
guessing - a mis-resolved row would overwrite one case study with another
one's tags, which is worse than a build that stops.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path
from xml.etree import ElementTree as ET

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _col_index(ref: str) -> int:
    """"C7" -> 2. Sheet cells carry their own address, so a row with gaps
    still lands its values in the right columns."""
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def read_sheet(path: Path | str, sheet_name: str | None = None) -> list[list[str]]:
    """One sheet as a dense list of rows of strings. Blank cells are "".

    Reads the first sheet when `sheet_name` is None. Values come back as
    the spreadsheet stored them, so a number is "0.0", not 0.
    """
    path = Path(path)
    with zipfile.ZipFile(path) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(f"{_NS}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{_NS}t")))

        workbook = ET.fromstring(z.read("xl/workbook.xml"))
        rel_root = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rel_targets = {r.get("Id"): r.get("Target") for r in rel_root}

        target = None
        for sheet in workbook.find(f"{_NS}sheets"):
            if sheet_name is None or sheet.get("name") == sheet_name:
                target = rel_targets[sheet.get(f"{_RNS}id")]
                break
        if target is None:
            raise ValueError(f"{path}: no sheet named {sheet_name!r}")
        if not target.startswith("xl/"):
            target = "xl/" + target.lstrip("/")

        rows: list[list[str]] = []
        root = ET.fromstring(z.read(target))
        for row_el in root.iter(f"{_NS}row"):
            cells: dict[int, str] = {}
            for c in row_el.findall(f"{_NS}c"):
                kind = c.get("t")
                v = c.find(f"{_NS}v")
                if kind == "s" and v is not None:
                    value = shared[int(v.text)]
                elif kind == "inlineStr":
                    is_el = c.find(f"{_NS}is")
                    value = (
                        "".join(x.text or "" for x in is_el.iter(f"{_NS}t"))
                        if is_el is not None
                        else ""
                    )
                else:
                    value = v.text if v is not None else ""
                if value and value.strip():
                    cells[_col_index(c.get("r"))] = value.strip()
            width = max(cells) + 1 if cells else 0
            rows.append([cells.get(i, "") for i in range(width)])
        return rows


# Column positions in "Case studies for DSMEs.xlsx". Positional rather than
# header-matched because the headers are two-line Thai question text; if the
# sheet is ever restructured this should fail loudly at load_cases(), which
# checks the header row.
COL = {
    "case_no": 0,
    "title": 1,
    "client": 2,
    "category": 3,
    "source": 4,
    "image": 5,
    "video": 6,
    "our_work": 7,
    "brand_communication": 8,
    "industry": 9,
    "stage": 10,
    "audience": 11,
    "challenge": 12,
    "own_commerce": 13,
    "asset_channel": 14,
    "objective": 15,
    "timeframe": 16,
    "budget": 17,
    "solution": 18,
    "mechanic": 19,
    "keywords": 20,
}

# The six weighted dimensions, in interview order. `own_commerce` is column
# 13 and is deliberately NOT here: it is a solution trigger, never a corpus
# tag (app/services/solution_trigger.py), and the sheet leaves it empty for
# every case for that reason. `timeframe` and `budget` are feasibility
# fields that size scope after a case is chosen, so they are not tags either.
TAG_DIMENSIONS = ("industry", "stage", "audience", "challenge", "asset_channel", "objective")

# The Thai placeholder the sheet uses where a thumbnail is still owed.
_IMAGE_TODO_MARKERS = ("ทีม", "ต้องหา")


@dataclass(frozen=True)
class SheetCase:
    """One curated case study, as the spreadsheet states it."""

    case_no: str
    title: str
    client: str
    category: str
    source: str
    image: str
    video: str
    our_work: str
    brand_communication: str
    tags: dict[str, str]  # dimension -> raw sheet phrase
    timeframe: str
    budget: str
    solution: str
    mechanic: str
    keywords: str

    @property
    def source_slug(self) -> str:
        """The portfolio page's basename, the sheet's most stable join key.
        Empty for rows with no portfolio URL or a non-portfolio one."""
        if "brandbizsolution.co.th" not in self.source:
            return ""
        return self.source.rstrip("/").rsplit("/", 1)[-1].removesuffix(".html")

    @property
    def has_image(self) -> bool:
        return bool(self.image) and not any(m in self.image for m in _IMAGE_TODO_MARKERS)

    def work_bullets(self) -> list[str]:
        """The "OUR WORK :" cell as a list. The sheet uses newlines inside
        one cell for what is really a bulleted list of services."""
        return [line.strip() for line in self.our_work.splitlines() if line.strip()]


def load_cases(path: Path | str, sheet_name: str = "Case study") -> list[SheetCase]:
    """Every row of the sheet that actually describes a case study.

    The trailing rows carrying only column A are the sheet author's notes to
    the AI ("select on Industry + Core Challenge + Business Objective..."),
    not data; they are skipped by requiring a title.
    """
    rows = read_sheet(path, sheet_name)
    if not rows:
        raise ValueError(f"{path}: sheet {sheet_name!r} is empty")

    header = rows[0]
    expected = {"case_no": "Case #", "title": "Case Study", "client": "Client"}
    for key, text in expected.items():
        idx = COL[key]
        if idx >= len(header) or header[idx].strip() != text:
            raise ValueError(
                f"{path}: column {idx} is "
                f"{header[idx].strip()!r} if present, expected {text!r} - the sheet "
                f"layout changed, so app/eval/case_sheet.py::COL needs updating."
            )

    def cell(row: list[str], key: str) -> str:
        idx = COL[key]
        return row[idx] if idx < len(row) else ""

    cases: list[SheetCase] = []
    for row in rows[1:]:
        if not cell(row, "title"):
            continue
        cases.append(
            SheetCase(
                case_no=cell(row, "case_no").split(".")[0],
                title=cell(row, "title"),
                client=cell(row, "client"),
                category=cell(row, "category"),
                source=cell(row, "source"),
                image=cell(row, "image"),
                video=cell(row, "video"),
                our_work=cell(row, "our_work"),
                brand_communication=cell(row, "brand_communication"),
                tags={d: cell(row, d) for d in TAG_DIMENSIONS},
                timeframe=cell(row, "timeframe"),
                budget=cell(row, "budget"),
                solution=cell(row, "solution"),
                mechanic=cell(row, "mechanic"),
                keywords=cell(row, "keywords"),
            )
        )
    return cases


# --- errata ---------------------------------------------------------------
#
# Two rows of the spreadsheet are wrong in ways that cannot be worked around
# downstream, so they are corrected here, in the open, rather than silently
# absorbed. Both were confirmed against the corpus file the previous build
# produced from the earlier revision of this sheet.
#
# The corrections are keyed by case number and assert what they expect to
# find, so if a future revision of the sheet fixes these at source,
# apply_errata() reports the erratum as stale instead of quietly reversing a
# fix.

_ERRATUM_1_WRONG = "https://www.brandbizsolution.co.th/TH/works/aura_blue_x_bar_b_gon.html"
_ERRATUM_1_RIGHT = "https://www.brandbizsolution.co.th/TH/works/grabfood__mega_sale.html"


@dataclass(frozen=True)
class Erratum:
    case_no: str
    what: str
    why: str


def apply_errata(cases: list[SheetCase]) -> tuple[list[SheetCase], list[Erratum], list[str]]:
    """Return (corrected cases, corrections applied, errata that no longer bite).

    Erratum A - case #1's Source cell holds case #6's URL (AURA BLUE's
    portfolio page). Case #1 is a GrabFood campaign; its title, narrative and
    video all match case-study_grabfood__mega_sale.md, whose Source is the
    URL case #0 carries. Left uncorrected, case #1 overwrites the AURA BLUE
    case study with GrabFood's content.

    Erratum B - case #0 is a stale duplicate of case #1: same client, same
    category, identical values in all six tag columns, and a title truncated
    mid-word ("...MEGA SALE ดีลทร"). Its narrative is the scraped write-up
    that case #1 replaced with a curated one. The only thing it holds that
    case #1 does not is the correct Source URL, which erratum A transplants,
    so once A is applied #0 carries nothing unique and is dropped.
    """
    applied: list[Erratum] = []
    stale: list[str] = []

    by_no = {c.case_no: c for c in cases}
    case_1 = by_no.get("1")
    if case_1 is None:
        stale.append("A: case #1 is no longer in the sheet")
    elif case_1.source != _ERRATUM_1_WRONG:
        stale.append(
            f"A: case #1's Source is {case_1.source!r}, not the known-wrong "
            f"{_ERRATUM_1_WRONG!r} - the sheet may have been fixed at source"
        )
    else:
        cases = [
            replace(c, source=_ERRATUM_1_RIGHT) if c.case_no == "1" else c for c in cases
        ]
        applied.append(
            Erratum(
                case_no="1",
                what=f"Source {_ERRATUM_1_WRONG} -> {_ERRATUM_1_RIGHT}",
                why="cell holds case #6's URL; this row is a GrabFood campaign",
            )
        )

    case_0 = by_no.get("0")
    if case_0 is None:
        stale.append("B: case #0 is no longer in the sheet")
    elif case_1 is None or case_0.tags != case_1.tags or case_0.client != case_1.client:
        stale.append(
            "B: case #0 no longer duplicates case #1 (tags or client differ) - "
            "it may now be a distinct campaign and should be reviewed"
        )
    else:
        cases = [c for c in cases if c.case_no != "0"]
        applied.append(
            Erratum(
                case_no="0",
                what="dropped from the build",
                why="duplicate of case #1 with a truncated title; its only unique "
                "cell (Source) is transplanted by erratum A",
            )
        )

    return cases, applied, stale


_SOURCE_RE = re.compile(r"\*\*Source:\*\*\s*(\S+)")
_TITLE_RE = re.compile(r"^#\s*Case Study:\s*(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class CorpusFileFacts:
    filename: str
    title: str
    source_slug: str


def scan_corpus_dir(directory: Path | str) -> list[CorpusFileFacts]:
    """Title and portfolio slug for every case-study markdown on disk."""
    out: list[CorpusFileFacts] = []
    for path in sorted(Path(directory).glob("case-study_*.md")):
        text = path.read_text(encoding="utf-8")
        title_match = _TITLE_RE.search(text)
        source_match = _SOURCE_RE.search(text)
        slug = ""
        if source_match and "brandbizsolution.co.th" in source_match.group(1):
            slug = source_match.group(1).rstrip("/").rsplit("/", 1)[-1].removesuffix(".html")
        out.append(
            CorpusFileFacts(
                filename=path.name,
                title=title_match.group(1).strip() if title_match else "",
                source_slug=slug,
            )
        )
    return out


@dataclass(frozen=True)
class Resolution:
    """How the sheet's rows line up with the files already on disk."""

    by_case_no: dict[str, str]  # sheet case_no -> existing filename
    how: dict[str, str]  # sheet case_no -> "source slug" | "title"
    unresolved: list[SheetCase]  # rows with no existing file (genuinely new)
    unclaimed: list[str]  # files no sheet row describes (keep untouched)
    collisions: dict[str, list[str]]  # filename -> [case_no, ...] claiming it


def resolve_filenames(cases: list[SheetCase], corpus: list[CorpusFileFacts]) -> Resolution:
    """Match sheet rows to corpus files on portfolio slug, then exact title.

    Collisions are returned rather than resolved. Two rows pointing at one
    file means the sheet has a duplicate campaign (the GrabFood Mega Sale
    pair) or a mistyped URL, and which of the two should win is a content
    decision, not something to settle by iteration order.
    """
    by_slug = {c.source_slug: c.filename for c in corpus if c.source_slug}
    by_title = {c.title: c.filename for c in corpus if c.title}

    by_case_no: dict[str, str] = {}
    how: dict[str, str] = {}
    unresolved: list[SheetCase] = []
    claimed: dict[str, list[str]] = {}

    for case in cases:
        filename = by_slug.get(case.source_slug) if case.source_slug else None
        method = "source slug"
        if filename is None:
            filename = by_title.get(case.title)
            method = "title"
        if filename is None:
            unresolved.append(case)
            continue
        by_case_no[case.case_no] = filename
        how[case.case_no] = method
        claimed.setdefault(filename, []).append(case.case_no)

    return Resolution(
        by_case_no=by_case_no,
        how=how,
        unresolved=unresolved,
        unclaimed=sorted(c.filename for c in corpus if c.filename not in claimed),
        collisions={fn: nos for fn, nos in claimed.items() if len(nos) > 1},
    )
