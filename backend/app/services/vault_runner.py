"""Git checkout + preamble, shared by the HTTP-triggered sync and the CLI.

This logic originally lived only in scripts/sync_vault.py. It is lifted
here so POST /admin/vault/sync (app/routers/vault.py, run via FastAPI
BackgroundTasks) and the cron CLI entrypoint (scripts/sync_vault.py) run
the identical clone/fetch -> classify -> reconcile path, sourcing
connection details from the admin-configured VaultConnection row instead
of (or as a fallback, from) VAULT_* env vars.

``run_sync`` owns a vault_sync_run row end to end and never raises —
BackgroundTasks has no channel to surface an exception to the client, so
every failure path is caught and written into the run row instead (mirrors
the "one bad note must not abort the run" philosophy in vault_sync.py).
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.models.user import User
from app.models.vault import VaultSyncRun
from app.services import audit as audit_svc
from app.services import classifier
from app.services.vault_connection import build_authenticated_url, decrypt_token, get_connection
from app.services.vault_sync import sync_vault

_log = logging.getLogger(__name__)

_ERROR_TEXT_MAX = 2000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _run_git(args: list[str], **kwargs) -> None:
    subprocess.run(["git", *args], check=True, **kwargs)


def sync_repo(git_url: str, vault_dir: Path, branch: str) -> None:
    """Clone the vault repo if absent, otherwise fetch + hard-reset to
    origin/<branch>. Hard-reset (not merge/pull) because this is a read-only
    mirror — any local drift must never block ingestion.

    Moved verbatim (behavior-wise) from scripts/sync_vault.py::_sync_repo.
    Blocking (shells out to git) — callers on the event loop must invoke
    this via ``asyncio.to_thread``.
    """
    if (vault_dir / ".git").exists():
        _log.info("sync_repo: fetching %s into %s", branch, vault_dir)
        # An admin may have repointed the connection to a different repo
        # since the last checkout (this is new with the self-service UI —
        # the old env-only config never changed without a restart, so this
        # never mattered before). Plain `git fetch origin` would otherwise
        # silently keep using whatever remote URL is already configured on
        # disk instead of the current connection's git_url.
        _run_git(["remote", "set-url", "origin", git_url], cwd=vault_dir)
        _run_git(["fetch", "origin", branch], cwd=vault_dir)
        _run_git(["reset", "--hard", f"origin/{branch}"], cwd=vault_dir)
    else:
        vault_dir.parent.mkdir(parents=True, exist_ok=True)
        _log.info("sync_repo: cloning %s into %s", branch, vault_dir)
        _run_git(["clone", "--branch", branch, "--single-branch", git_url, str(vault_dir)])


async def resolve_bot_user(
    session_factory: async_sessionmaker[AsyncSession], email: str
) -> User | None:
    """Moved from scripts/sync_vault.py::_resolve_bot_user."""
    async with session_factory() as session:
        return (
            await session.execute(select(User).where(User.google_email == email))
        ).scalar_one_or_none()


async def _set_run(
    session_factory: async_sessionmaker[AsyncSession], run_id: uuid.UUID, **values
) -> None:
    async with session_factory() as session:
        await session.execute(
            sa_update(VaultSyncRun).where(VaultSyncRun.id == run_id).values(**values)
        )
        await session.commit()


async def _fail(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    error: str,
    *,
    user_id: uuid.UUID | None = None,
) -> None:
    await _set_run(
        session_factory, run_id,
        status="failed", error_text=error[:_ERROR_TEXT_MAX], finished_at=_now(),
    )
    await audit_svc.log(
        action="vault_sync_failed", user_id=user_id,
        details={"run_id": str(run_id), "error": error[:500]},
    )


async def run_sync(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    dry_run: bool = False,
) -> None:
    """Background job body for POST /admin/vault/sync. Never raises."""
    try:
        async with session_factory() as session:
            conn = await get_connection(session)

        if conn is None or not conn.git_url:
            await _fail(session_factory, run_id, "No vault connection configured.")
            return

        token = decrypt_token(conn)
        url = build_authenticated_url(conn.git_url, token)
        vault_dir = Path(get_settings().vault_dir)

        stage = "pulling" if (vault_dir / ".git").exists() else "cloning"
        await _set_run(session_factory, run_id, status=stage)
        try:
            await asyncio.to_thread(sync_repo, url, vault_dir, conn.branch)
        except subprocess.CalledProcessError as exc:
            await _fail(session_factory, run_id, f"git sync failed: {exc}")
            return

        async with session_factory() as session:
            rule_count = await classifier.load_rules(session)
        warning: str | None = None
        if rule_count == 0:
            warning = (
                "0 classification rules loaded — Tier 3+ quarantine cannot "
                "function; confidential notes may be ingested into the "
                "org-wide corpus."
            )
            _log.warning("run_sync: %s", warning)

        bot = await resolve_bot_user(session_factory, conn.bot_email)
        if bot is None:
            await _fail(
                session_factory, run_id,
                f"No user with email={conn.bot_email!r}. "
                f"Run scripts/create_service_account.py --email {conn.bot_email} first.",
            )
            return

        await _set_run(session_factory, run_id, status="reconciling")
        summary = await sync_vault(
            session_factory,
            bot.id,
            vault_dir,
            templates_dirname=conn.templates_dirname,
            dry_run=dry_run,
        )

        await _set_run(
            session_factory, run_id,
            status="done",
            added=summary.added,
            updated=summary.updated,
            deleted=summary.deleted,
            quarantined=summary.quarantined,
            skipped=summary.skipped,
            failed_count=summary.failed,
            error_text=warning,
            finished_at=_now(),
        )
        await audit_svc.log(
            action="vault_sync_completed",
            user_id=bot.id,
            details={
                "run_id": str(run_id),
                "added": summary.added, "updated": summary.updated,
                "deleted": summary.deleted, "quarantined": summary.quarantined,
                "skipped": summary.skipped, "failed": summary.failed,
            },
        )
    except Exception as exc:  # noqa: BLE001 — BackgroundTasks has no error channel
        _log.exception("run_sync: unhandled error for run_id=%s", run_id)
        try:
            await _fail(session_factory, run_id, str(exc))
        except Exception:
            _log.exception("run_sync: failed to record failure for run_id=%s", run_id)
