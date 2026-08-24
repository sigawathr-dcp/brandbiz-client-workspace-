"""
scripts/build_case_studies.py

Regenerate the case-study corpus from "Case studies for DSMEs.xlsx".

This replaces the old out-of-repo generator (Brandbiz_Data/make_case_studies.py,
referenced by seed_case_studies.py), which no longer exists. The corpus now
lives in this repo at backend/data/case_studies/, recovered byte-for-byte
from the running system, so a rebuild is reproducible from a clean checkout.

ADDITIVE BY CONSTRUCTION. The spreadsheet is the source of truth for the
fields it carries and for nothing else:

  * Every case study already on disk stays on disk. The six files no sheet
    row describes (the GrabMart / Grab x Disney / PPG / Siam Orchard / AURA
    ME scrapes) are left byte-identical, not deleted, not rewritten. They
    stay in the library untagged, where case_score treats them as "unknown"
    and defers to the embedding.

  * `## Execution details (from portfolio site)` is carried across verbatim.
    That section is scraped detail the spreadsheet never had, and losing it
    would quietly shrink what the retriever can match on.

  * Header fields the sheet leaves blank keep the value the existing file
    has. The sheet has no Source for three cases and no real Image for
    twenty; overwriting a good URL with a blank is a regression.

What the sheet does get to change: title, client, category, the service
bullets, the campaign narrative, and the new Approach block (Solution /
Mechanic / Fit / Matching keywords), which is written into the document so
the dense half of the match score can see it - those columns exist to help
matching and had nowhere to live before.

Usage (from backend/, host or container):
    python scripts/build_case_studies.py                # report, write nothing
    python scripts/build_case_studies.py --write        # regenerate the corpus
    python scripts/build_case_studies.py --write --tags # ...and case_tags.csv

Nothing here touches the database. Re-ingesting the regenerated files is
scripts/seed_case_studies.py --refresh; loading the tags is
scripts/seed_case_tags.py.
"""
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.eval import case_sheet, case_tag_map  # noqa: E402
from app.eval.corpus import CaseTagEntry, load_case_tags, write_case_tags  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHEET = BACKEND_ROOT / "data" / "case_studies_dsme.xlsx"
DEFAULT_CORPUS_DIR = BACKEND_ROOT / "data" / "case_studies"
DEFAULT_TAGS_PATH = BACKEND_ROOT / "eval" / "case_match" / "case_tags.csv"

_EXECUTION_HEADING = "## Execution details (from portfolio site)"
_FOOTER_SOURCE = "Case studies for DSMEs.xlsx"


# --- reading what is already on disk ---------------------------------------


def _existing_field(text: str, label: str) -> str:
    """The value of a `- **Label:** value` header line, or ""."""
    marker = f"- **{label}:**"
    for line in text.splitlines():
        if line.startswith(marker):
            return line[len(marker) :].strip()
        if line.startswith("## "):
            break
    return ""


def _existing_videos(text: str) -> list[str]:
    marker = "- **Video:**"
    out = []
    for line in text.splitlines():
        if line.startswith(marker):
            out.append(line[len(marker) :].strip())
        elif line.startswith("## "):
            break
    return out


def _execution_section(text: str) -> str:
    """The scraped `## Execution details` block, verbatim, footer stripped."""
    if _EXECUTION_HEADING not in text:
        return ""
    body = text.split(_EXECUTION_HEADING, 1)[1]
    # The trailing `---` + italic provenance line is regenerated below.
    body = body.split("\n---\n", 1)[0]
    return body.rstrip()


def _scraped_only_section(text: str) -> str:
    """For a file in the scrape-only shape (`## What we did` with bold
    inline labels), keep the whole body as execution detail so nothing the
    scrape captured is lost when the sheet's curated sections replace it."""
    if "## What we did" not in text:
        return ""
    body = text.split("## What we did", 1)[1].split("\n---\n", 1)[0]
    return "### What we did (scraped)\n\n" + body.strip("\n")


# --- writing the refreshed document ----------------------------------------


def render(case: case_sheet.SheetCase, existing: str | None) -> str:
    """The markdown for one curated case, merged over its existing file.

    Field precedence is sheet-first, existing-as-fallback, so a blank cell
    never erases a value we already have.
    """
    existing = existing or ""

    source = case.source or _existing_field(existing, "Source")
    videos = [case.video] if case.video else _existing_videos(existing)
    image = case.image if case.has_image else _existing_field(existing, "Image")

    lines = [f"# Case Study: {case.title}", ""]
    lines.append(f"- **Client:** {case.client or _existing_field(existing, 'Client')}")
    category = case.category or _existing_field(existing, "Category")
    if category:
        lines.append(f"- **Category:** {category}")
    if source:
        lines.append(f"- **Source:** {source}")
    for video in videos:
        if video:
            lines.append(f"- **Video:** {video}")
    if image:
        lines.append(f"- **Image:** {image}")

    bullets = case.work_bullets()
    if bullets:
        lines += ["", "## Our work", ""]
        lines += [f"- {b}" for b in bullets]

    if case.brand_communication:
        lines += ["", "## Brand communication", "", case.brand_communication]

    # Solution / Mechanic / Fit / Keywords: curated columns with no other
    # home. Emitted as bullets, not prose, so _narrative_summary() in
    # services/case_card.py cannot mistake them for the campaign narrative
    # and put them on the client's card.
    approach = []
    if case.solution:
        approach.append(f"- **Solution:** {case.solution}")
    if case.mechanic:
        approach.append(f"- **Mechanic:** {case.mechanic}")
    fit = " / ".join(x for x in (case.timeframe, case.budget) if x)
    if fit:
        approach.append(f"- **Typical fit:** {fit}")
    if case.keywords:
        approach.append(f"- **Matching keywords:** {case.keywords}")
    if approach:
        lines += ["", "## Approach", ""] + approach

    execution = _execution_section(existing) or _scraped_only_section(existing)
    if execution:
        lines += ["", _EXECUTION_HEADING, "", execution.strip("\n")]

    provenance = f'_Curated case study from "{_FOOTER_SOURCE}" (case #{case.case_no})'
    provenance += (
        ", merged with the portfolio write-up scraped from brandbizsolution.co.th._"
        if execution
        else ". No matching page on the portfolio site._"
        if not source
        else "._"
    )
    lines += ["", "---", provenance, ""]
    return "\n".join(lines)


def slug_for(case: case_sheet.SheetCase) -> str:
    """Filename for a case with no existing file. Prefers the portfolio
    slug, which is how every other file in the corpus is named."""
    if case.source_slug:
        return f"case-study_{case.source_slug}.md"
    base = "".join(ch.lower() if ch.isalnum() else "_" for ch in case.title)
    base = "_".join(p for p in base.split("_") if p)
    return f"case-study_{base}.md"


# --- tags ------------------------------------------------------------------


def tag_entries(
    cases: list[case_sheet.SheetCase], filenames: dict[str, str]
) -> tuple[list[CaseTagEntry], list[str]]:
    """case_tags.csv rows for every resolved case, plus per-case problems.

    Confidence is 1.00 throughout: these are a human's assertions in the
    spreadsheet, transcribed through an explicit mapping table, not a
    model's reading of a narrative.
    """
    entries: list[CaseTagEntry] = []
    problems: list[str] = []
    for case in cases:
        filename = filenames.get(case.case_no)
        if not filename:
            continue
        for dimension in case_sheet.TAG_DIMENSIONS:
            raw = case.tags.get(dimension, "")
            if not raw:
                problems.append(f"#{case.case_no} {filename}: {dimension} is blank")
                continue
            try:
                tokens = case_tag_map.tags_for(dimension, raw)
            except ValueError as exc:
                problems.append(f"#{case.case_no} {filename}: {exc}")
                continue
            if not tokens:
                problems.append(
                    f"#{case.case_no} {filename}: {dimension} {raw!r} maps to no token"
                )
            for token in tokens:
                entries.append(
                    CaseTagEntry(
                        filename=filename,
                        tag_type=dimension,
                        tag_value=token,
                        confidence=1.0,
                        note=f"sheet case #{case.case_no}: {raw}",
                    )
                )
    return entries, problems


# --- main ------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet", type=Path, default=DEFAULT_SHEET)
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--tags-path", type=Path, default=DEFAULT_TAGS_PATH)
    parser.add_argument("--write", action="store_true", help="write the markdown files")
    parser.add_argument("--tags", action="store_true", help="also write case_tags.csv")
    parser.add_argument("--diff", action="store_true", help="show a unified diff per file")
    args = parser.parse_args()

    cases = case_sheet.load_cases(args.sheet)
    cases, applied, stale = case_sheet.apply_errata(cases)
    print(f"sheet: {len(cases)} case(s) after errata")
    for e in applied:
        print(f"  erratum #{e.case_no}: {e.what}\n      reason: {e.why}")
    for s in stale:
        print(f"  STALE ERRATUM - review app/eval/case_sheet.py: {s}")

    corpus = case_sheet.scan_corpus_dir(args.corpus_dir)
    resolution = case_sheet.resolve_filenames(cases, corpus)
    if resolution.collisions:
        print("\nERROR: two sheet rows claim one corpus file:")
        for filename, nos in sorted(resolution.collisions.items()):
            print(f"  {filename} <- cases {', '.join('#' + n for n in nos)}")
        print("Resolve in app/eval/case_sheet.py errata before building.")
        return 1

    filenames = dict(resolution.by_case_no)
    for case in resolution.unresolved:
        filenames[case.case_no] = slug_for(case)
        print(f"\nNEW case #{case.case_no} {case.title!r} -> {filenames[case.case_no]}")

    print(f"\nkeeping {len(resolution.unclaimed)} file(s) no sheet row describes:")
    for filename in resolution.unclaimed:
        print(f"  {filename}")

    changed, unchanged, created = [], [], []
    for case in cases:
        filename = filenames[case.case_no]
        path = args.corpus_dir / filename
        existing = path.read_text(encoding="utf-8") if path.exists() else None
        rendered = render(case, existing)
        if existing is None:
            created.append(filename)
        elif rendered != existing:
            changed.append(filename)
            if args.diff:
                print(f"\n--- {filename}")
                sys.stdout.writelines(
                    difflib.unified_diff(
                        existing.splitlines(True),
                        rendered.splitlines(True),
                        fromfile=f"a/{filename}",
                        tofile=f"b/{filename}",
                    )
                )
        else:
            unchanged.append(filename)
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8", newline="\n")

    print(
        f"\nmarkdown: {len(created)} created, {len(changed)} changed, "
        f"{len(unchanged)} unchanged, {len(resolution.unclaimed)} untouched"
        f"{'' if args.write else '  (dry run - pass --write)'}"
    )

    entries, problems = tag_entries(cases, filenames)
    by_dimension: dict[str, int] = {}
    for e in entries:
        by_dimension[e.tag_type] = by_dimension.get(e.tag_type, 0) + 1
    print(f"\ntags: {len(entries)} across {len(set(e.filename for e in entries))} case(s)")
    for dimension in case_sheet.TAG_DIMENSIONS:
        print(f"  {dimension:<14} {by_dimension.get(dimension, 0)}")
    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print(f"  {p}")

    # Tags for files no sheet row describes are carried across untouched.
    # Those six cases were tagged before this sheet existed (the category
    # rule in scripts/tag_case_studies.py --industry); the sheet is silent
    # about them, and silence is not a retraction.
    preserved = [e for e in load_case_tags(args.tags_path) if e.filename not in set(filenames.values())]
    if preserved:
        print(
            f"\npreserving {len(preserved)} existing tag(s) on "
            f"{len(set(e.filename for e in preserved))} case(s) the sheet does not describe"
        )

    if args.tags:
        if problems:
            print("\nRefusing to write case_tags.csv while problems are unresolved.")
            return 1
        if not args.write:
            print("\n--tags requires --write.")
            return 1
        write_case_tags(args.tags_path, preserved + entries)
        print(f"\nwrote {len(preserved) + len(entries)} tags -> {args.tags_path}")

    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
