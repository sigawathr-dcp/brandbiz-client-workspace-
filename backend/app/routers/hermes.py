"""
app/routers/hermes.py

Task 3.13/3.14 -- Hermes host-setup support for the Tasks page.

Hermes runs natively on the Docker host, so the backend can't install or
start it directly. Two escalating conveniences:

Task 3.13 (manual, always available):
  GET  /hermes/status                 — reachability + helper liveness (consented users)
  GET  /hermes/setup-script           — downloadable install-hermes.ps1 (ADMIN, audited)

Task 3.14 (one-click, once the host helper is installed):
  GET  /hermes/helper-script          — downloadable one-time helper installer (ADMIN, audited;
                                        mints/rotates the helper's service-account key)
  POST /hermes/host-jobs              — enqueue a setup job = the "Set up Hermes now" button
                                        (ADMIN, audited, 409 if one is active)
  GET  /hermes/host-jobs/latest       — poll target for the banner's live job log (consented users)
  GET  /hermes/host-jobs/pending      — helper claim poll; 204 when idle (helper key only)
  POST /hermes/host-jobs/{id}/report  — helper progress/terminal reports (helper key only)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.deps import get_api_principal, require_admin, require_consent
from app.models.hermes_host_job import HermesHostJob
from app.models.user import User
from app.services import audit as audit_svc
from app.services import hermes_host_jobs
from app.services import hermes_setup

router = APIRouter(prefix="/hermes", tags=["hermes"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class StatusOut(BaseModel):
    configured: bool      # HERMES_API_KEY set -> the model is registered at all
    reachable: bool       # GET {HERMES_API_URL}/models answered 200 just now
    helper_online: bool   # host helper polled for jobs within the last ~15s


class HostJobOut(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    log_text: str | None
    created_at: datetime
    updated_at: datetime
    claimed_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class PendingJobOut(BaseModel):
    """What the helper receives when it claims a job: lifecycle identity plus
    Hermes's two config FILES (data, never code — the helper's behavior is
    fixed at helper-install time)."""
    id: uuid.UUID
    kind: str
    config_yaml: str
    env_file: str


class ReportIn(BaseModel):
    status: str | None = None   # 'running' | 'succeeded' | 'failed'
    log: str | None = None      # one progress line to append


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

async def _require_helper(
    user: Annotated[User, Depends(get_api_principal)],
) -> User:
    """Only the dedicated helper service account may claim/report jobs —
    any other API key (e.g. the n8n bot's) is rejected."""
    if user.google_email != hermes_host_jobs.HELPER_EMAIL:
        raise HTTPException(status_code=403, detail="Reserved for the Hermes host helper")
    return user


def _require_hermes_configured() -> None:
    if not settings.hermes_api_key:
        raise HTTPException(
            status_code=503,
            detail="Hermes is not configured on this gateway (HERMES_API_KEY is blank)",
        )


def _script_download(script: str, filename: str) -> Response:
    return Response(
        content=script,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Status + manual setup script (Task 3.13)
# ---------------------------------------------------------------------------

@router.get("/status", response_model=StatusOut)
async def status(
    user: Annotated[User, Depends(require_consent)],
) -> StatusOut:
    probe = await hermes_setup.probe()
    return StatusOut(
        configured=probe.configured,
        reachable=probe.reachable,
        helper_online=hermes_host_jobs.helper_online(),
    )


@router.get("/setup-script")
async def setup_script(
    admin: Annotated[User, Depends(require_admin)],
) -> Response:
    _require_hermes_configured()
    script = hermes_setup.render_setup_script()
    # The script hands out the gateway<->Hermes shared secret — record who took it.
    await audit_svc.log(
        action="hermes_setup_script_downloaded",
        user_id=admin.id,
        details={"ollama_url": settings.hermes_ollama_url,
                 "ollama_model": settings.hermes_ollama_model},
    )
    return _script_download(script, "install-hermes.ps1")


# ---------------------------------------------------------------------------
# One-click host jobs (Task 3.14)
# ---------------------------------------------------------------------------

@router.get("/helper-script")
async def helper_script(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    _require_hermes_configured()
    # Each download rotates the helper credential; only the newest installed
    # helper keeps working.
    raw_key = await hermes_host_jobs.mint_helper_key(session)
    script = hermes_host_jobs.render_helper_installer_cmd(raw_key)
    await audit_svc.log(
        action="hermes_helper_script_downloaded",
        user_id=admin.id,
        details={"helper_account": hermes_host_jobs.HELPER_EMAIL, "key_rotated": True},
    )
    return _script_download(script, "install-helper.cmd")


@router.post("/host-jobs", response_model=HostJobOut, status_code=202)
async def create_host_job(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> HermesHostJob:
    _require_hermes_configured()
    job = await hermes_host_jobs.create_job(session, admin)
    await audit_svc.log(
        action="hermes_host_job_created",
        user_id=admin.id,
        resource_type="hermes_host_job",
        resource_id=job.id,
        details={"kind": job.kind},
    )
    return job


@router.get("/host-jobs/latest", response_model=HostJobOut | None)
async def latest_host_job(
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> HermesHostJob | None:
    return await hermes_host_jobs.latest(session)


@router.get("/host-jobs/pending", response_model=None)
async def pending_host_job(
    helper: Annotated[User, Depends(_require_helper)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response | PendingJobOut:
    job = await hermes_host_jobs.claim_pending(session)
    if job is None:
        return Response(status_code=204)
    return PendingJobOut(
        id=job.id,
        kind=job.kind,
        config_yaml=hermes_setup.render_config_yaml(),
        env_file=hermes_setup.render_env_file(),
    )


@router.post("/host-jobs/{job_id}/report", response_model=HostJobOut)
async def report_host_job(
    job_id: uuid.UUID,
    body: ReportIn,
    helper: Annotated[User, Depends(_require_helper)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> HermesHostJob:
    return await hermes_host_jobs.report(session, job_id, status=body.status, log=body.log)
