"""
app/routers/tasks.py

Task 3.12 -- "Cowork-style" background tasks.

POST   /tasks              — submit a task; runs unattended via Hermes (202)
GET    /tasks               — list the caller's tasks (no result body — for polling lists)
GET    /tasks/{id}          — fetch one task, including decrypted prompt/result/transcript
POST   /tasks/{id}/cancel   — best-effort cancel of a queued/running task
POST   /tasks/{id}/messages — send a follow-up on an existing task's conversation (202)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import require_consent
from app.models.agent_task import AgentTask
from app.models.user import User
from app.services import agent_tasks as agent_tasks_svc

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SubmitTaskRequest(BaseModel):
    prompt: str


class FollowupRequest(BaseModel):
    prompt: str


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    model_used: str | None
    created_at: str


class TaskSummary(BaseModel):
    id: uuid.UUID
    title: str | None
    status: str
    downgrade_to_local: bool
    model_used: str | None
    tokens_input: int | None
    tokens_output: int | None
    cost_usd: Decimal | None
    error_text: str | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    # Cheap presence check (no decryption) so the list view can show a "live
    # activity" hint on running cards without paying to decrypt every row's
    # progress log on every 5s list poll -- the full log is decrypted only on
    # the single-record detail endpoint below.
    has_progress: bool = False

    model_config = {"from_attributes": True}


class TaskDetail(TaskSummary):
    """Adds the decrypted prompt + result + live progress — only returned for
    the single-record detail endpoint, scoped to the owning user (§7.1
    decrypt-on-read)."""
    prompt: str
    result: str | None
    # Live activity log / partial output while status is queued/running; None
    # once the task reaches a terminal state (result/error_text take over).
    progress: str | None
    # Full turn-by-turn history from the task's conversation (Task 3.15 --
    # multi-turn follow-ups). Empty until the first turn reaches call_llm.
    messages: list[MessageOut] = []


def _to_summary(task: AgentTask) -> TaskSummary:
    summary = TaskSummary.model_validate(task)
    summary.has_progress = task.progress_ciphertext is not None
    return summary


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("", response_model=TaskSummary, status_code=202)
async def submit(
    body: SubmitTaskRequest,
    background: BackgroundTasks,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TaskSummary:
    # submit_task's only raises are HTTPException (403 via prepare_chat's policy
    # gate, 503 if Hermes isn't configured) — FastAPI handles those directly.
    # Hermes itself isn't called until the background worker runs, so
    # LLMProviderError can never surface here.
    task = await agent_tasks_svc.submit_task(
        session=session, user=user, prompt=body.prompt, background=background
    )
    return _to_summary(task)


@router.get("", response_model=list[TaskSummary])
async def list_tasks(
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[TaskSummary]:
    tasks = await agent_tasks_svc.list_tasks(session, user)
    return [_to_summary(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskDetail)
async def get_task(
    task_id: uuid.UUID,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TaskDetail:
    task = await agent_tasks_svc.get_task(session, user, task_id)
    transcript = await agent_tasks_svc.get_transcript(session, task)
    return TaskDetail(
        **_to_summary(task).model_dump(),
        prompt=agent_tasks_svc.decrypt_prompt(task),
        result=agent_tasks_svc.decrypt_result(task),
        progress=agent_tasks_svc.decrypt_progress(task),
        messages=[MessageOut(**m) for m in transcript],
    )


@router.post("/{task_id}/cancel", response_model=TaskSummary)
async def cancel(
    task_id: uuid.UUID,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TaskSummary:
    task = await agent_tasks_svc.cancel_task(session, user, task_id)
    return _to_summary(task)


@router.post("/{task_id}/messages", response_model=TaskSummary, status_code=202)
async def send_followup(
    task_id: uuid.UUID,
    body: FollowupRequest,
    background: BackgroundTasks,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TaskSummary:
    # add_followup's only raises are HTTPException (404 unowned task, 409 if a
    # turn is already in flight, 403 via prepare_chat's policy gate) —
    # FastAPI handles those directly, same as submit() above.
    task = await agent_tasks_svc.add_followup(
        session=session, user=user, task_id=task_id, prompt=body.prompt, background=background
    )
    return _to_summary(task)
