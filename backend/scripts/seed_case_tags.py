"""
scripts/seed_case_tags.py

Load the REVIEWED case-study tags (backend/eval/case_match/case_tags.csv)
into case_study_tags — the corpus side of the weighted matcher.

Reads only the committed file, never a model. scripts/tag_case_studies.py
proposes; a human reviews; this ships what survived. Keeping the two apart
is the point: a tag decides which clients ever see a case, so a model must
not be able to change that as a side effect of a deploy.

Idempotent. Tags are keyed (case_study_id, tag_type, tag_value) and matched
to cases through files.filename, so re-running after editing the CSV
converges rather than duplicating: rows in the file are upserted, and rows
in the database that the file no longer lists are deleted (a tag removed in
review must actually go away, otherwise review can only ever add).

    python scripts/seed_case_tags.py            # dry run — prints the plan
    python scripts/seed_case_tags.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402

from app.db import session_factory  # noqa: E402
from app.eval.corpus import DEFAULT_CASE_TAGS_PATH, load_case_tags  # noqa: E402
from app.models.client_intake import CaseStudy, CaseStudyTag  # noqa: E402
from app.models.file import File  # noqa: E402


async def run(path: Path, apply: bool) -> int:
    entries = load_case_tags(path)  # validates every token against the vocabulary
    if not entries:
        print(f"no tags in {path} — nothing to do")
        return 0

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(File.filename, CaseStudy.id).join(CaseStudy, CaseStudy.file_id == File.id)
            )
        ).all()
        case_id_by_filename = {filename: cid for filename, cid in rows}
        if not case_id_by_filename:
            print("no case studies in the database — run scripts/seed_case_studies.py first")
            return 1

        unknown = sorted({e.filename for e in entries} - set(case_id_by_filename))
        if unknown:
            # Refuse rather than skip: a filename that does not resolve means
            # the CSV and the corpus have diverged, and silently dropping
            # those tags would leave the matcher quietly under-informed.
            print(f"{len(unknown)} filename(s) in {path.name} are not in the corpus:")
            for u in unknown:
                print(f"  {u}")
            return 1

        existing = (
            await session.execute(
                select(CaseStudyTag.id, CaseStudyTag.case_study_id,
                       CaseStudyTag.tag_type, CaseStudyTag.tag_value, CaseStudyTag.confidence)
            )
        ).all()
        existing_by_key = {(c, t, v): (i, conf) for i, c, t, v, conf in existing}

        wanted: dict[tuple, float] = {}
        for e in entries:
            wanted[(case_id_by_filename[e.filename], e.tag_type, e.tag_value)] = e.confidence

        to_insert = [k for k in wanted if k not in existing_by_key]
        to_update = [
            k for k in wanted
            if k in existing_by_key and float(existing_by_key[k][1]) != wanted[k]
        ]
        to_delete = [k for k in existing_by_key if k not in wanted]

        print(f"{len(entries)} tags in {path.name} across {len({e.filename for e in entries})} cases")
        print(f"  insert: {len(to_insert)}   update: {len(to_update)}   delete: {len(to_delete)}")

        if not apply:
            print("\n(dry run — pass --apply to write)")
            return 0

        for key in to_insert:
            case_id, tag_type, tag_value = key
            session.add(
                CaseStudyTag(
                    case_study_id=case_id, tag_type=tag_type,
                    tag_value=tag_value, confidence=wanted[key],
                )
            )
        for key in to_update:
            tag_id = existing_by_key[key][0]
            obj = await session.get(CaseStudyTag, tag_id)
            if obj is not None:
                obj.confidence = wanted[key]
        for key in to_delete:
            await session.execute(delete(CaseStudyTag).where(CaseStudyTag.id == existing_by_key[key][0]))

        await session.commit()
        print("committed")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", default=str(DEFAULT_CASE_TAGS_PATH))
    ap.add_argument("--apply", action="store_true", help="write to the database")
    args = ap.parse_args()
    return asyncio.run(run(Path(args.path), args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
