"""Sync the shared Obsidian vault (git repo) into the RAG corpus.

Run from inside the backend-api container, on a schedule (no Celery in demo
mode — this is invoked directly, e.g. by host cron):

    docker compose exec backend-api python -m scripts.sync_vault
    docker compose exec backend-api python -m scripts.sync_vault --dry-run

Prerequisites (one-time):
  1. `alembic upgrade head` (0028_vault_connection, which comes after
     0027_obsidian_source_columns).
  2. Mint the bot user that will own every ingested vault file:
       python scripts/create_service_account.py --email obsidian-bot@service.local --role L1
     (the API key it prints is unused here — only the User row matters.)
  3. Configure the connection. Two ways, checked in this order:
       a. Admin UI (preferred) — Vault sync settings page, backed by
          POST/GET /admin/vault/config (app/routers/vault.py) and stored
          encrypted in the vault_connection table
          (app/services/vault_connection.py).
       b. VAULT_GIT_URL (with an embedded access token), VAULT_BRANCH,
          VAULT_BOT_EMAIL in .env — used only when no vault_connection row
          exists yet, so existing env-only deployments keep working
          unchanged.

Cron example (hourly, host-side, no TTY):
    0 * * * * docker compose exec -T backend-api python -m scripts.sync_vault \
        >> /var/log/vault_sync.log 2>&1
"""
from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.db import session_factory
from app.services import classifier
from app.services.vault_connection import build_authenticated_url, decrypt_token, get_connection
from app.services.vault_runner import resolve_bot_user, sync_repo
from app.services.vault_sync import sync_vault


@dataclass
class _ResolvedConnection:
    git_url: str  # may embed a token — never print/log this value
    branch: str
    bot_email: str
    templates_dirname: str
    source: str  # "db" or "env" — informational only, safe to log


async def _resolve_connection() -> _ResolvedConnection | None:
    """The admin-configured DB connection (app/services/vault_connection.py)
    takes priority; VAULT_* env vars remain a fallback for deployments that
    haven't used the admin UI yet."""
    cfg = get_settings()

    async with session_factory() as session:
        conn = await get_connection(session)

    if conn is not None and conn.git_url:
        token = decrypt_token(conn)
        return _ResolvedConnection(
            git_url=build_authenticated_url(conn.git_url, token),
            branch=conn.branch,
            bot_email=conn.bot_email,
            templates_dirname=conn.templates_dirname,
            source="db",
        )

    if cfg.vault_git_url:
        return _ResolvedConnection(
            git_url=cfg.vault_git_url,
            branch=cfg.vault_branch,
            bot_email=cfg.vault_bot_email,
            templates_dirname=cfg.vault_templates_dirname,
            source="env",
        )

    return None


async def main(dry_run: bool, vault_dir_override: str | None) -> int:
    cfg = get_settings()

    resolved = await _resolve_connection()
    if resolved is None:
        print(
            "[sync_vault] no vault connection configured (admin UI or "
            "VAULT_GIT_URL) — sync disabled, nothing to do."
        )
        return 0

    print(f"[sync_vault] using {resolved.source}-configured connection (branch={resolved.branch})")
    vault_dir = Path(vault_dir_override or cfg.vault_dir)

    try:
        sync_repo(resolved.git_url, vault_dir, resolved.branch)
    except subprocess.CalledProcessError as exc:
        print(f"[sync_vault] ERROR: git sync failed: {exc}", file=sys.stderr)
        return 1

    async with session_factory() as session:
        rule_count = await classifier.load_rules(session)
    print(f"[sync_vault] loaded {rule_count} classifier rules")
    if rule_count == 0:
        print(
            "[sync_vault] WARNING: 0 classification rules loaded — Tier 3+ "
            "quarantine cannot function; confidential notes may be ingested "
            "into the org-wide corpus. Check data_classification_rules.",
            file=sys.stderr,
        )

    bot = await resolve_bot_user(session_factory, resolved.bot_email)
    if bot is None:
        print(
            f"[sync_vault] ERROR: no user with email={resolved.bot_email!r}. "
            f"Run scripts/create_service_account.py --email {resolved.bot_email} first.",
            file=sys.stderr,
        )
        return 2

    summary = await sync_vault(
        session_factory,
        bot.id,
        vault_dir,
        templates_dirname=resolved.templates_dirname,
        dry_run=dry_run,
    )

    label = "[sync_vault DRY RUN]" if dry_run else "[sync_vault]"
    print(
        f"{label} added={summary.added} updated={summary.updated} "
        f"deleted={summary.deleted} quarantined={summary.quarantined} "
        f"skipped={summary.skipped} failed={summary.failed}"
    )
    for err in summary.errors:
        print(f"[sync_vault]   error: {err}", file=sys.stderr)

    return 1 if summary.failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Walk, hash, and classify the vault; print what would change without writing anything.",
    )
    parser.add_argument(
        "--vault-dir", default=None,
        help="Override VAULT_DIR (the local checkout path).",
    )
    args = parser.parse_args()

    sys.exit(asyncio.run(main(dry_run=args.dry_run, vault_dir_override=args.vault_dir)))
