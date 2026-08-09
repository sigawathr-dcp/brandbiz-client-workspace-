"""
app/routers/vault.py

Admin-only self-service Obsidian vault connection + sync, under /admin/vault/*.

Complements the pre-existing standalone CLI (backend/scripts/sync_vault.py,
still cron-runnable) by letting an ADMIN configure the vault git URL /
access token / branch from the frontend and trigger + poll a sync with
live progress, instead of editing VAULT_* env vars and shelling into the
container. See app/services/vault_connection.py (config CRUD + token
crypto) and app/services/vault_runner.py (git + reconcile job, run via
BackgroundTasks — no Celery in demo mode, D9).

Security note (D13 deviation, explicitly user-approved — see
app/models/vault.py): the access token is never included in any response
body, audit `details`, or log line. GET /config only reports whether a
token is currently stored (`token_set`).

Endpoints:
  GET  /admin/vault/config       — current connection (token never returned)
  PUT  /admin/vault/config       — create/update the connection
  POST /admin/vault/sync         — trigger a sync (202); 409 if one is active
  GET  /admin/vault/sync/latest  — most recent run, or null
  GET  /admin/vault/sync/{id}    — poll one run's status (stepper target)
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db, session_factory
from app.deps import require_admin
from app.models.user import User
from app.models.vault import ACTIVE_SYNC_STATUSES, VaultSyncRun
from app.schemas.vault import VaultConfigIn, VaultConfigOut, VaultSyncRunOut, VaultSyncTrigger
from app.services import audit as audit_svc
from app.services import vault_connection
from app.services.vault_runner import run_sync

router = APIRouter(prefix="/admin/vault", tags=["vault"])


def _config_out(conn) -> VaultConfigOut:
    if conn is None:
        return VaultConfigOut(
            git_url=None, branch="main", bot_email="", templates_dirname="templates",
            token_set=False, updated_at=None,
        )
    return VaultConfigOut(
        git_url=conn.git_url,
        branch=conn.branch,
        bot_email=conn.bot_email,
        templates_dirname=conn.templates_dirname,
        token_set=conn.token_ciphertext is not None,
        updated_at=conn.updated_at,
    )


@router.get("/config", response_model=VaultConfigOut)
async def get_config(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> VaultConfigOut:
    return _config_out(await vault_connection.get_connection(session))


@router.put("/config", response_model=VaultConfigOut)
async def put_config(
    body: VaultConfigIn,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> VaultConfigOut:
    conn = await vault_connection.upsert_connection(
        session,
        git_url=body.git_url,
        branch=body.branch,
        token=body.token,
        bot_email=body.bot_email,
        templates_dirname=body.templates_dirname,
        updated_by=admin.id,
    )
    await audit_svc.log(
        action="vault_connection_updated",
        user_id=admin.id,
        details={
            "git_url": conn.git_url,
            "branch": conn.branch,
            "token_changed": bool(body.token),
        },
    )
    return _config_out(conn)


@router.post("/sync", status_code=202, response_model=VaultSyncRunOut)
async def trigger_sync(
    body: VaultSyncTrigger,
    background_tasks: BackgroundTasks,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> VaultSyncRunOut:
    active = (
        await session.execute(
            select(VaultSyncRun)
            .where(VaultSyncRun.status.in_(ACTIVE_SYNC_STATUSES))
            .order_by(VaultSyncRun.started_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail=f"A sync is already in progress (run_id={active.id}, status={active.status}).",
        )

    run = VaultSyncRun(status="cloning", dry_run=body.dry_run, triggered_by=admin.id)
    session.add(run)
    await session.commit()
    await session.refresh(run)

    background_tasks.add_task(run_sync, session_factory, run_id=run.id, dry_run=body.dry_run)

    await audit_svc.log(
        action="vault_sync_triggered",
        user_id=admin.id,
        details={"run_id": str(run.id), "dry_run": body.dry_run},
    )
    return VaultSyncRunOut.model_validate(run)


@router.get("/sync/latest", response_model=VaultSyncRunOut | None)
async def latest_sync(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> VaultSyncRunOut | None:
    """Registered before /sync/{run_id} — 'latest' must not match the UUID path param."""
    run = (
        await session.execute(
            select(VaultSyncRun).order_by(VaultSyncRun.started_at.desc()).limit(1)
        )
    ).scalars().first()
    return VaultSyncRunOut.model_validate(run) if run is not None else None


@router.get("/sync/{run_id}", response_model=VaultSyncRunOut)
async def get_sync(
    run_id: uuid.UUID,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> VaultSyncRunOut:
    run = (
        await session.execute(select(VaultSyncRun).where(VaultSyncRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Sync run not found")
    return VaultSyncRunOut.model_validate(run)
