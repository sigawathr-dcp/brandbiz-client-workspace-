"""
backend/scripts/eval_case_match_export.py

Step 1 of the case-match eval harness's human-labeling loop (see
backend/eval/case_match/README or PLAN.md for the harness overview):
inspects the case-study corpus a workspace's agent has attached, and
writes the artifacts a Brandbiz consultant needs to label ground truth
without ever reading raw markdown or a database:

  - labeling_sheet.csv  — one row per (golden profile x case file),
    ordered by the system's current deep-mode rank, with the profile and
    case rendered in Thai from parse_case_card()'s fields. Only the last
    two columns (relevance grade, note) are meant to be filled in.
  - corpus_manifest.csv — filename -> sha256 snapshot (committed), so a
    later eval run can detect "this case's content changed since it was
    labeled" instead of silently trusting stale labels.
  - labels.placeholder.csv (--bootstrap-labels) — label=2 on each
    profile's current top-1 result, 0 elsewhere. Its metrics are perfect
    by construction and therefore meaningless; it exists only so
    eval_case_match_run.py's plumbing can be exercised end-to-end before
    any human has labeled anything (see PLAN.md Phase A).

Preflight aborts (corpus-health problems that would make labeling
pointless — see app.eval.corpus.CorpusReport.is_healthy()): duplicate
filenames, unprocessed files, zero-chunk files, unembedded chunks. Fix
those (re-upload, scripts/reembed_pending.py) and re-run.

Run from inside the backend-api container:
    docker compose exec backend-api sh -c "cd /app && PYTHONPATH=/app \
        python scripts/eval_case_match_export.py --workspace-slug brandbiz-demo \
        --out /app/eval/case_match/out/labeling_sheet.csv \
        --manifest /app/eval/case_match/corpus_manifest.csv \
        --bootstrap-labels /app/eval/case_match/labels.placeholder.csv"

Idempotent: re-running overwrites the same output files with fresh data.
"""
import argparse
import asyncio
import csv
import math
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.eval import corpus as corpus_mod
from app.eval import goldens
from app.models.client_intake import CaseStudy
from app.models.file import File
from app.models.user import User
from app.models.workspace import Workspace
from app.services import agent as agent_svc
from app.services import case_match as case_match_svc
from app.services import workspace as workspace_svc

DEEP_POOL_CHUNKS = 500


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workspace-slug", default="brandbiz-demo")
    p.add_argument("--profiles", default=str(goldens.DEFAULT_PROFILES_PATH))
    p.add_argument("--out", required=True, help="path to write labeling_sheet.csv")
    p.add_argument("--manifest", required=True, help="path to write corpus_manifest.csv")
    p.add_argument("--bootstrap-labels", default=None, help="optional path to write a placeholder labels CSV")
    return p.parse_args()


async def _resolve_agent_file_ids(session, workspace_slug: str) -> tuple[Workspace, list[uuid.UUID]]:
    workspace = (
        await session.execute(select(Workspace).where(Workspace.slug == workspace_slug))
    ).scalar_one_or_none()
    if workspace is None:
        print(f"ERROR: no workspace with slug {workspace_slug!r}. Run scripts/seed_client_demo.py first.")
        sys.exit(1)

    agent = await workspace_svc.get_workspace_agent(session, workspace.id)
    if agent is None:
        print(f"ERROR: workspace {workspace_slug!r} has no published agent assigned.")
        sys.exit(1)

    file_ids = await agent_svc.get_agent_file_ids(session, agent.id)
    if not file_ids:
        print(
            f"ERROR: agent {agent.name!r} has no attached knowledge files. "
            f"Run scripts/attach_case_studies.py first."
        )
        sys.exit(1)
    return workspace, file_ids


async def _resolve_seat(session, workspace: Workspace) -> User:
    existing = (
        await session.execute(
            select(User).where(User.workspace_id == workspace.id).order_by(User.created_at.asc())
        )
    ).scalars().first()
    if existing is not None:
        return existing
    # Transient — never added to the session. rag_search._scope_filter only
    # ever reads user.id / user.workspace_id, so this is safe to fabricate.
    return User(
        id=uuid.uuid4(),
        google_email=f"eval-harness@{workspace.slug}.client.invalid",
        workspace_id=workspace.id,
        role="L1",
    )


async def main() -> None:
    args = _parse_args()
    from app.db import session_factory

    async with session_factory() as session:
        workspace, agent_file_ids = await _resolve_agent_file_ids(session, args.workspace_slug)

        print("--- Corpus preflight ---")
        report = await corpus_mod.load_corpus(session, agent_file_ids)
        if not report.is_healthy():
            print("ERROR: corpus is not eval-ready:")
            for problem in report.problems():
                print(f"  - {problem}")
            sys.exit(1)
        print(f"  OK: {len(report.files)} files, all processed and embedded, no duplicate filenames.")

        filename_map = corpus_mod.resolve_filenames(report)
        chunk_count_by_filename = {f.filename: f.chunk_count for f in report.files}

        profiles = goldens.load_profiles(args.profiles)
        print(f"\n--- Loaded {len(profiles)} golden profiles ---")

        seat = await _resolve_seat(session, workspace)
        print(f"  Impersonating: {seat.google_email} (workspace={workspace.slug})")

        print("\n--- Running deep-pool retrieval per profile (for sheet ordering + cards) ---")
        sheet_rows: list[dict] = []
        card_by_filename: dict[str, object] = {}
        bootstrap_rows: list[str] = []
        now_str = datetime.now(timezone.utc).date().isoformat()

        for profile in profiles:
            run = await case_match_svc.match_cases(
                session,
                seat,
                profile.fields,
                agent_file_ids=agent_file_ids,
                effective_workspace_id=workspace.id,
                top_k=DEEP_POOL_CHUNKS,
                max_distance=math.inf,
                include_cards=True,
                strict=True,
            )
            summary_th = goldens.profile_thai_summary(profile)
            for r in run.results:
                if r.card is not None:
                    card_by_filename[r.filename] = r.card
                card = r.card
                sheet_rows.append(
                    {
                        "profile_id": profile.id,
                        "โปรไฟล์ลูกค้า": summary_th,
                        "filename": r.filename,
                        "ชื่อเคส": (card.title if card else None) or "",
                        "แบรนด์": (card.client if card else None) or "",
                        "หมวดหมู่": (card.category if card else None) or "",
                        "สรุปย่อ": (card.summary if card else None) or "",
                        "ลิงก์": (card.source_url if card else None) or "",
                        "อันดับที่ระบบจัด": r.rank + 1,
                        "คะแนนระบบ": round(r.score, 2),
                        "ระดับความเกี่ยวข้อง (0/1/2)": "",
                        "หมายเหตุ": "",
                    }
                )
            if run.results:
                top1 = run.results[0].filename
                for r in run.results:
                    label = 2 if r.filename == top1 else 0
                    bootstrap_rows.append(
                        f"{profile.id},{r.filename},{label},bootstrap,{now_str},"
                        f"placeholder — perfect by construction, do not use for real analysis"
                    )
            print(f"  {profile.id}: {len(run.results)} cases ranked")

        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "profile_id", "โปรไฟล์ลูกค้า", "filename", "ชื่อเคส", "แบรนด์", "หมวดหมู่",
            "สรุปย่อ", "ลิงก์", "อันดับที่ระบบจัด", "คะแนนระบบ",
            "ระดับความเกี่ยวข้อง (0/1/2)", "หมายเหตุ",
        ]
        with out_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(sheet_rows)
        print(f"\nWrote labeling sheet: {out_path} ({len(sheet_rows)} rows)")

        # Descriptive columns come from the case_studies catalog, which covers
        # the whole corpus, and fall back to a retrieved card only where the
        # catalog is silent. Sourcing them from `card_by_filename` alone would
        # leave a file blank whenever it happened not to surface for any golden
        # profile — and `category` is what scripts/tag_case_studies.py
        # --industry derives from, so a blank there silently drops that case's
        # industry tag on the next run.
        catalog_rows = (
            await session.execute(
                select(File.filename, CaseStudy.title, CaseStudy.client_name, CaseStudy.category)
                .join(CaseStudy, CaseStudy.file_id == File.id)
                .where(File.filename.in_(list(filename_map)))
            )
        ).all()
        catalog_by_filename = {r[0]: r for r in catalog_rows}

        def described(fn: str, index: int, attr: str) -> str | None:
            row = catalog_by_filename.get(fn)
            if row is not None and row[index]:
                return row[index]
            return getattr(card_by_filename.get(fn), attr, None)

        manifest_entries = [
            corpus_mod.ManifestEntry(
                filename=fn,
                sha256=next((cf.sha256_hash for cf in report.files if cf.filename == fn), "") or "",
                title=described(fn, 1, "title"),
                client=described(fn, 2, "client"),
                category=described(fn, 3, "category"),
                chunk_count=chunk_count_by_filename.get(fn, 0),
            )
            for fn in filename_map
        ]
        corpus_mod.write_manifest(args.manifest, manifest_entries)
        print(f"Wrote corpus manifest: {args.manifest} ({len(manifest_entries)} files)")

        if args.bootstrap_labels:
            boot_path = Path(args.bootstrap_labels)
            if not boot_path.name.endswith(".placeholder.csv"):
                print(
                    f"  WARNING: {boot_path.name!r} doesn't end in '.placeholder.csv' — "
                    f"app.eval.goldens.load_labels() flags placeholder files by that suffix; "
                    f"the report's loud banner won't fire for this file."
                )
            boot_path.parent.mkdir(parents=True, exist_ok=True)
            with boot_path.open("w", encoding="utf-8") as f:
                f.write("profile_id,filename,label,labeled_by,labeled_at,note\n")
                f.write("\n".join(bootstrap_rows) + ("\n" if bootstrap_rows else ""))
            print(f"Wrote bootstrap labels: {boot_path} ({len(bootstrap_rows)} rows) — PLACEHOLDER, perfect by construction")

    print("\nDone. Send labeling_sheet.csv + LABELING.th.md to a consultant, then run "
          "scripts/eval_case_match_import.py on the filled-in copy.")


if __name__ == "__main__":
    asyncio.run(main())
