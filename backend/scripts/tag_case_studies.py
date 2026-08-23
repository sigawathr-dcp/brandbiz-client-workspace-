"""
scripts/tag_case_studies.py

Propose case_study_tags for human review — the corpus side of the weighted
matcher (Interview_Details.xlsx column F).

Two passes, kept apart on purpose because they warrant very different trust:

  --industry  Derives the `industry` dimension from the committed manifest's
              `category` column by an explicit rule table below. Offline, no
              DB, no model. Every mapping is inspectable in this file, so
              these ship at confidence 1.00.

  --narrative Proposes the remaining five dimensions (stage, audience,
              challenge, asset_channel, objective) by reading each case's
              narrative out of the database. These are a MODEL'S OPINION
              about what a campaign was for, they ship at confidence < 1.00,
              and a human has to read them before they mean anything.

Output goes to a proposal file, never to case_tags.csv directly. The
reviewed file is what seed_case_tags.py reads, so nothing a model invents
reaches production without someone having looked at it:

    python scripts/tag_case_studies.py --industry            # -> stdout diff
    python scripts/tag_case_studies.py --industry --write    # -> case_tags.csv
    python scripts/tag_case_studies.py --narrative           # -> case_tags.proposed.csv
    python scripts/tag_case_studies.py --coverage            # what's still untagged

Why the corpus is read from the DB and not from disk: the case-study
markdown is not in this repo. It is ingested into files/file_chunks (see
scripts/seed_case_studies.py), so the database is the only place the
narrative actually exists.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.eval import corpus as corpus_mod  # noqa: E402
from app.eval.corpus import (  # noqa: E402
    DEFAULT_CASE_TAGS_PATH,
    CaseTagEntry,
    load_case_tags,
    load_manifest,
    tag_coverage,
    write_case_tags,
)
from app.services import case_taxonomy  # noqa: E402

MANIFEST_PATH = Path(__file__).resolve().parents[1] / "eval" / "case_match" / "corpus_manifest.csv"
PROPOSED_PATH = DEFAULT_CASE_TAGS_PATH.with_name("case_tags.proposed.csv")

# --- industry rule table --------------------------------------------------
#
# Matched case-insensitively as substrings against the manifest's `category`,
# most specific first. A category may yield SEVERAL industries: GrabFood is
# genuinely both an app business and an F&B one, and case_study_tags is
# many-to-many precisely so that does not have to be resolved to a lie.
#
# `secondary` tags carry lower confidence — they are a defensible reading of
# the category string rather than a restatement of it.
_CATEGORY_RULES: list[tuple[str, list[str], list[str]]] = [
    # (substring, primary industries, secondary industries)
    ("food delivery", ["tech_app"], ["food_beverage"]),
    ("application", ["tech_app"], []),
    ("health & supplements", ["health_supplement"], []),
    ("dietary supplements", ["health_supplement"], []),
    ("medicines", ["health_supplement"], []),
    ("skincare", ["beauty"], []),
    ("cosmetic", ["beauty"], []),
    ("beauty", ["beauty"], []),
    ("entertainment", ["entertainment_media"], []),
    ("movies", ["entertainment_media"], []),
    ("travel agency", ["property_travel"], []),
    ("mobile phone shop", ["retail_fmcg"], ["tech_app"]),
    # Categories introduced by "Case studies for DSMEs.xlsx". Both are
    # physical consumer products sold through retail, not digital services —
    # the same call app/eval/case_tag_map.py makes for these two cases, kept
    # in step so the two tagging paths cannot disagree about one corpus.
    ("tech & mobile store", ["retail_fmcg"], []),
    ("tech accessories", ["retail_fmcg"], []),
    ("lubricant", ["automotive"], []),
    ("challenger", ["automotive"], []),  # "PTT CHALLENGER" — PTT Lubricants
]

PRIMARY_CONFIDENCE = 1.00
SECONDARY_CONFIDENCE = 0.60


def industry_tags_for(category: str | None, client: str | None) -> list[tuple[str, float, str]]:
    """[(tag, confidence, note)] for one case, from its category string."""
    if not category:
        return []
    haystack = f"{category} {client or ''}".lower()
    primary: dict[str, None] = {}
    secondary: dict[str, None] = {}
    matched: list[str] = []
    for needle, prim, sec in _CATEGORY_RULES:
        if needle in haystack:
            matched.append(needle)
            for t in prim:
                primary.setdefault(t, None)
            for t in sec:
                secondary.setdefault(t, None)
    note = f"category rule: {', '.join(matched)}" if matched else ""
    out = [(t, PRIMARY_CONFIDENCE, note) for t in primary]
    out += [(t, SECONDARY_CONFIDENCE, note) for t in secondary if t not in primary]
    return out


def build_industry_entries() -> tuple[list[CaseTagEntry], list[str]]:
    manifest = load_manifest(MANIFEST_PATH)
    if not manifest:
        raise SystemExit(f"no manifest at {MANIFEST_PATH} — run eval_case_match_export.py first")
    entries: list[CaseTagEntry] = []
    unmatched: list[str] = []
    for filename, m in sorted(manifest.items()):
        tags = industry_tags_for(m.category, m.client)
        if not tags:
            unmatched.append(f"{filename}  (category={m.category!r})")
            continue
        for tag, confidence, note in tags:
            case_taxonomy.validate_tag("industry", tag)
            entries.append(CaseTagEntry(filename, "industry", tag, confidence, note))
    return entries, unmatched


async def build_narrative_proposals() -> list[CaseTagEntry]:
    """Read each case's text from the DB and propose the five judgement
    dimensions. Deliberately unimplemented as an automated model call: see
    the module docstring. This prints the material a reviewer needs instead,
    so the review pass is a reading task rather than an archaeology task.
    """
    from sqlalchemy import select

    from app.db import session_factory
    from app.models.client_intake import CaseStudy
    from app.models.file import File, FileChunk

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(File.filename, CaseStudy.title, CaseStudy.summary)
                .join(CaseStudy, CaseStudy.file_id == File.id)
                .order_by(File.filename)
            )
        ).all()
        if not rows:
            raise SystemExit(
                "no case studies in the database — run scripts/seed_case_studies.py first"
            )
        print(f"# {len(rows)} cases awaiting narrative review")
        print("# Dimensions to assign per case: " + ", ".join(
            d for d in case_taxonomy.DIMENSIONS if d != "industry"
        ))
        print()
        for filename, title, summary in rows:
            print(f"## {filename}")
            print(f"   title:   {title or '-'}")
            print(f"   summary: {(summary or '-')[:400]}")
            for dimension in case_taxonomy.DIMENSIONS:
                if dimension == "industry":
                    continue
                print(f"   {dimension}: ?   # one of {sorted(case_taxonomy.VOCAB[dimension])}")
            print()
    return []


def cmd_industry(write: bool) -> int:
    entries, unmatched = build_industry_entries()
    existing = load_case_tags(DEFAULT_CASE_TAGS_PATH)
    keep = [e for e in existing if e.tag_type != "industry"]

    print(f"{len(entries)} industry tags derived from {MANIFEST_PATH.name}")
    for e in entries:
        print(f"  {e.filename:<52} {e.tag_value:<22} conf={e.confidence:.2f}")
    if unmatched:
        print(f"\n{len(unmatched)} case(s) matched NO category rule — add a rule or tag by hand:")
        for u in unmatched:
            print(f"  {u}")

    if write:
        write_case_tags(DEFAULT_CASE_TAGS_PATH, keep + entries)
        print(f"\nwrote {len(keep) + len(entries)} tags -> {DEFAULT_CASE_TAGS_PATH}")
    else:
        print("\n(dry run — pass --write to update case_tags.csv)")
    return 1 if unmatched else 0


def cmd_coverage() -> int:
    manifest = load_manifest(MANIFEST_PATH)
    entries = load_case_tags(DEFAULT_CASE_TAGS_PATH)
    coverage = tag_coverage(manifest, entries)
    missing_total = sum(len(v) for v in coverage.values())
    full = [f for f, m in coverage.items() if not m]
    print(f"{len(manifest)} cases, {len(case_taxonomy.DIMENSIONS)} dimensions each")
    print(f"{len(entries)} tags committed; {missing_total} (case, dimension) pairs still untagged")
    print(f"{len(full)}/{len(manifest)} cases fully tagged\n")
    for filename, missing in coverage.items():
        if missing:
            print(f"  {filename:<52} missing: {', '.join(missing)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--industry", action="store_true", help="derive industry tags from the manifest")
    ap.add_argument("--narrative", action="store_true", help="dump cases for narrative review")
    ap.add_argument("--coverage", action="store_true", help="report untagged (case, dimension) pairs")
    ap.add_argument("--write", action="store_true", help="write results to case_tags.csv")
    args = ap.parse_args()

    if args.industry:
        return cmd_industry(args.write)
    if args.narrative:
        asyncio.run(build_narrative_proposals())
        return 0
    if args.coverage:
        return cmd_coverage()
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
