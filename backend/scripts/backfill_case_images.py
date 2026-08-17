"""
scripts/backfill_case_images.py

Populate case_studies.image_url so the Cases cards can show a campaign
thumbnail (services/case_image.py explains where the images come from and why
the scraped corpus has none).

Also catalogs any case-study file that has no case_studies row yet. Until now
rows were only created lazily, the first time a file happened to win a match
(routers/client.py::run_case_match) — so most of the corpus had no catalog row
at all, and the very first client to match a file would have seen it without a
thumbnail even after this backfill.

Run inside the backend container. Use `-m`: running the file by path puts
/app/scripts on sys.path instead of /app, so `import app` fails.

    docker compose exec backend-api python -m scripts.backfill_case_images --dry-run
    docker compose exec backend-api python -m scripts.backfill_case_images
    docker compose exec backend-api python -m scripts.backfill_case_images --force

Idempotent: rows that already have an image_url are skipped unless --force.
One HTTP GET per case study against the public portfolio site; failures are
reported and skipped, never fatal.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import httpx
from sqlalchemy import select, text

from app.db import session_factory
from app.models.client_intake import CaseStudy
from app.services.case_card import parse_case_card
from app.services.case_image import fetch_case_image

_CASE_FILE_PREFIX = "case-study"
_USER_AGENT = "Mozilla/5.0 (compatible; brandbiz-case-image-backfill)"


async def _load_case_files(session) -> list[tuple[str, str, str]]:
    """(file_id, filename, full_markdown) for every case-study file, rebuilt
    from its chunks the same way case_match does."""
    rows = (
        await session.execute(
            text(
                """
                SELECT f.id::text, f.filename,
                       string_agg(c.content, E'\n' ORDER BY c.chunk_index) AS body
                FROM files f
                JOIN file_chunks c ON c.file_id = f.id
                WHERE f.filename LIKE :prefix
                GROUP BY f.id, f.filename
                ORDER BY f.filename
                """
            ),
            {"prefix": f"{_CASE_FILE_PREFIX}%"},
        )
    ).all()
    return [(r[0], r[1], r[2] or "") for r in rows]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    parser.add_argument(
        "--force", action="store_true", help="refetch even when image_url is already set"
    )
    args = parser.parse_args()

    cataloged = updated = skipped = failed = cleared = 0
    studies: list[tuple[CaseStudy, str]] = []

    async with session_factory() as session:
        files = await _load_case_files(session)
        print(f"{len(files)} case-study file(s) in the corpus")

        async with httpx.AsyncClient(
            timeout=20.0, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
        ) as client:
            for file_id, filename, body in files:
                card = parse_case_card(body)
                study = (
                    await session.execute(
                        select(CaseStudy).where(CaseStudy.file_id == file_id)
                    )
                ).scalar_one_or_none()

                if study is None:
                    # Never matched, so never cataloged. Seed the row from the
                    # markdown exactly as run_case_match would.
                    study = CaseStudy(
                        file_id=file_id,
                        title=card.title,
                        client_name=card.client,
                        category=card.category,
                        source_url=card.source_url,
                        image_url=card.image_url,
                        summary=card.summary,
                    )
                    session.add(study)
                    cataloged += 1

                # Collected before the skip branches below so the uniqueness
                # sweep sees every case in the corpus, not just the ones this
                # run happened to fetch.
                studies.append((study, filename))

                if study.image_url and not args.force:
                    skipped += 1
                    continue
                if not study.source_url:
                    print(f"  no Source URL, skipped: {filename}")
                    failed += 1
                    continue

                image_url = await fetch_case_image(client, study.source_url)
                if image_url is None:
                    # Reached only on a fresh row or under --force, i.e. this is
                    # an authoritative re-evaluation. A stored value that no
                    # longer passes selection has to go — leaving it would keep
                    # serving a thumbnail the current rules reject.
                    if study.image_url:
                        study.image_url = None
                        cleared += 1
                        print(f"  no image found, cleared stale value: {filename}")
                    else:
                        print(f"  no image found: {filename}")
                    failed += 1
                    continue

                study.image_url = image_url
                updated += 1
                print(f"  {filename} -> {image_url}")

        # No two cases may show the same thumbnail. pick_image_url() only ever
        # returns per-campaign gallery images, so this should find nothing —
        # but a shared image is indistinguishable from a correct one when you
        # can only see one page at a time, which is exactly how the promo-strip
        # fallback used to put one identical photo on three cards. Enforce the
        # invariant across the corpus instead of trusting the per-page rule.
        by_url: dict[str, list[tuple[CaseStudy, str]]] = {}
        for study, filename in studies:
            if study.image_url:
                by_url.setdefault(study.image_url, []).append((study, filename))
        for url, group in sorted(by_url.items()):
            if len(group) < 2:
                continue
            print(f"  shared by {len(group)} cases — cleared all, cannot tell whose it is:")
            print(f"      {url}")
            for study, filename in group:
                print(f"      - {filename}")
                study.image_url = None
                cleared += 1

        if args.dry_run:
            await session.rollback()
            print("\n--dry-run: rolled back")
        else:
            await session.commit()

    print(
        f"\ncataloged={cataloged} images_set={updated} "
        f"already_had_image={skipped} no_image={failed} cleared={cleared}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
