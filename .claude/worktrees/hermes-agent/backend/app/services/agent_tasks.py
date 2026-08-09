"""
app/services/agent_tasks.py

Task 3.12 -- "Cowork-style" background tasks: assign Hermes Agent an outcome,
close the tab, come back later to a finished, reviewable result.

Reuses the same governance seam as POST /automations/agent:
prepare_chat() (PolicyEngine.decide -- tier detection, quota, 403-on-deny)
then run_chat_collect() (headless, non-streaming LangGraph run that persists
the encrypted assistant message and charges quota). The only new piece is
running run_chat_collect() inside a FastAPI BackgroundTasks worker so it
outlives the HTTP response instead of blocking it.

No Celery/Redis in demo mode (D9) -- BackgroundTasks runs in the API worker
process, same as AI Studio's video/music generation jobs. See "Known
limitations" in PLAN.md Task 3.12: an API container restart loses in-flight
tasks (they stay stuck "running").
"""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import func as sa_func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import crypto
from app.db import session_factory
from app.llm.router import HERMES_MODEL_CODE, get_router
from app.models.agent_task import ACTIVE_TASK_STATUSES, AgentTask
from app.models.user import User
from app.services import audit as audit_svc

logger = logging.getLogger(__name__)

# Minimum interval between progress-column writes while a task is running.
# Content deltas can arrive many times a second; without throttling every
# delta would trigger its own UPDATE + commit, which is wasteful and adds no
# visible value to a UI polling every ~2s anyway.
_PROGRESS_FLUSH_INTERVAL_S = 2.0


async def submit_task(
    session: AsyncSession,
    user: User,
    *,
    prompt: str,
    background: BackgroundTasks,
) -> AgentTask:
    """Authorize and enqueue a background task. Returns the 'queued' row.

    Raises HTTPException(403) via prepare_chat() on policy deny, and
    HTTPException(503) if Hermes isn't configured (blank HERMES_API_KEY).
    Consent is enforced by the router's require_consent dependency, not here
    (matches app/services/studio.py's convention).
    """
    # Lazy import: chat_policy pulls in app.tools.image_gen -> app.llm.google,
    # which requires the [external] extras (google-genai). Importing here
    # avoids that chain being triggered at module-load time, and mirrors
    # app/routers/automations.py's identical lazy import of the same function.
    from app.services.chat_policy import prepare_chat  # noqa: PLC0415

    try:
        get_router().get(HERMES_MODEL_CODE)
    except KeyError:
        raise HTTPException(
            status_code=503,
            detail="Hermes is not configured on this gateway (HERMES_API_KEY is blank).",
        )

    # The governance gate -- identical to POST /chat and POST /automations/agent.
    # A new conversation_id=None seeds a fresh conversation per task; Tier 3/4
    # prompts silently downgrade prepared.model_code to local (Hermes never
    # sees confidential data).
    prepared = await prepare_chat(
        session=session,
        user=user,
        conversation_id=None,
        user_content=prompt,
        requested_model=HERMES_MODEL_CODE,
    )

    ct, nonce, tag, kv = crypto.encrypt(prompt)
    task = AgentTask(
        user_id=user.id,
        conversation_id=prepared.resolved_conversation_id,
        title=prompt[:60].strip() or None,
        prompt_ciphertext=ct,
        prompt_nonce=nonce,
        prompt_tag=tag,
        key_version=kv,
        status="queued",
        downgrade_to_local=prepared.downgrade_to_local,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    await audit_svc.log(
        action="agent_task_submitted",
        user_id=user.id,
        resource_type="agent_task",
        resource_id=task.id,
        details={
            "downgrade_to_local": prepared.downgrade_to_local,
            "prompt_length": len(prompt),
        },
    )

    background.add_task(
        _run_task,
        task_id=task.id,
        user_id=user.id,
        resolved_conversation_id=prepared.resolved_conversation_id,
        prompt=prompt,
        model_code=prepared.model_code,
        history=prepared.history,
        downgrade_to_local=prepared.downgrade_to_local,
        reasons=prepared.reasons,
    )

    return task


async def _run_task(
    task_id: uuid.UUID,
    user_id: uuid.UUID,
    resolved_conversation_id: uuid.UUID,
    prompt: str,
    model_code: str,
    history: list[dict],
    downgrade_to_local: bool,
    reasons: list[str],
) -> None:
    """Background worker: run the agent headlessly, update the task row.

    Opens its own DB session because the request session has already been
    closed by the time this task runs (same pattern as
    studio._run_video_generation). Never raises -- BackgroundTasks has no
    error channel, so any failure is caught and recorded on the row instead.
    """
    # Lazy import: orchestrator pulls in LLM clients (openai, google-genai)
    # that are only available in the [external] extras. Mirrors
    # app/routers/automations.py's import-time guard.
    from app.agents.orchestrator import run_chat_collect_streamed  # noqa: PLC0415

    async with session_factory() as session:
        await session.execute(
            update(AgentTask).where(AgentTask.id == task_id).values(status="running")
        )
        await session.commit()

    await audit_svc.log(
        action="agent_task_running",
        user_id=user_id,
        resource_type="agent_task",
        resource_id=task_id,
    )

    status = "failed"
    error_text: str | None = None
    result: dict | None = None

    # Accumulates into the live activity log shown on the Tasks detail page.
    # Only "start"/"notice"/"error" become their own log lines -- "content" is
    # streamed text, so it's appended to a running partial-answer buffer
    # instead of one line per delta.
    log_lines: list[str] = []
    partial_response = ""
    last_flush = 0.0  # 0 forces the first event through regardless of timing

    async def on_event(data: dict) -> None:
        nonlocal partial_response, last_flush
        kind = data.get("type")
        if kind == "start":
            log_lines.append("Task started on Hermes")
        elif kind == "notice" and data.get("event") == "downgrade_to_local":
            reason = data.get("reason", "policy")
            log_lines.append(f"Routed to the local model ({reason}) — Hermes did not see this prompt")
        elif kind == "sources":
            n = len(data.get("sources") or [])
            if n:
                log_lines.append(f"Retrieved {n} knowledge source(s)")
        elif kind == "content":
            partial_response += data.get("delta", "")
        elif kind == "error":
            log_lines.append(f"Error: {data.get('message', 'unknown error')}")

        now = time.monotonic()
        if now - last_flush < _PROGRESS_FLUSH_INTERVAL_S:
            return
        last_flush = now
        await _flush_progress(task_id, log_lines, partial_response)

    try:
        result_user = await _reload_user(user_id)
        result = await _run_collect(
            run_chat_collect_streamed,
            on_event=on_event,
            user_id=user_id,
            user=result_user,
            resolved_conversation_id=resolved_conversation_id,
            user_content=prompt,
            model_code=model_code,
            history=history,
            downgrade_to_local=downgrade_to_local,
            reasons=reasons,
        )
        status = "succeeded"
    except Exception as exc:  # noqa: BLE001 -- must never propagate out of BackgroundTasks
        error_text = str(exc)
        logger.warning("agent task %s failed: %s", task_id, exc, exc_info=True)

    async with session_factory() as session:
        # Progress is only meaningful while running -- clear it now that the
        # task has a terminal, durable result_*/error_text record instead.
        values: dict = {
            "status": status,
            "progress_ciphertext": None,
            "progress_nonce": None,
            "progress_tag": None,
            "progress_key_version": None,
        }
        if status == "succeeded" and result is not None:
            ct, nonce, tag, kv = crypto.encrypt(result["output"])
            values.update(
                result_ciphertext=ct,
                result_nonce=nonce,
                result_tag=tag,
                result_key_version=kv,
                model_used=result["model_used"],
                tokens_input=result["tokens_input"],
                tokens_output=result["tokens_output"],
            )
        else:
            values["error_text"] = error_text
        values["finished_at"] = sa_func.now()
        await session.execute(update(AgentTask).where(AgentTask.id == task_id).values(**values))
        await session.commit()

    await audit_svc.log(
        action="agent_task_succeeded" if status == "succeeded" else "agent_task_failed",
        user_id=user_id,
        resource_type="agent_task",
        resource_id=task_id,
        details={"error": error_text} if error_text else None,
    )


async def _flush_progress(task_id: uuid.UUID, log_lines: list[str], partial_response: str) -> None:
    """Throttled write of the accumulated activity log + partial answer to
    the task row, encrypted the same way as prompt/result (§7.1). Called from
    _run_task's on_event callback at most once every _PROGRESS_FLUSH_INTERVAL_S.
    """
    text = "\n".join(f"- {line}" for line in log_lines)
    if partial_response:
        text = f"{text}\n\n{partial_response}" if text else partial_response
    if not text:
        return
    ct, nonce, tag, kv = crypto.encrypt(text)
    async with session_factory() as session:
        await session.execute(
            update(AgentTask)
            .where(AgentTask.id == task_id)
            .values(
                progress_ciphertext=ct,
                progress_nonce=nonce,
                progress_tag=tag,
                progress_key_version=kv,
            )
        )
        await session.commit()


async def _reload_user(user_id: uuid.UUID) -> User:
    """The request-scoped User instance is bound to a closed session by the
    time the background worker runs -- reload it on the worker's own session."""
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one()
        session.expunge(user)
        return user


async def _run_collect(run_chat_collect, **kwargs) -> dict:
    """Runs run_chat_collect on its own fresh session -- kept as a thin
    wrapper so the session lifecycle is explicit and symmetric with the
    other steps in _run_task."""
    async with session_factory() as session:
        return await run_chat_collect(session=session, **kwargs)


async def list_tasks(session: AsyncSession, user: User) -> list[AgentTask]:
    result = await session.execute(
        select(AgentTask)
        .where(AgentTask.user_id == user.id)
        .order_by(AgentTask.created_at.desc())
    )
    return list(result.scalars().all())


async def get_task(session: AsyncSession, user: User, task_id: uuid.UUID) -> AgentTask:
    result = await session.execute(
        select(AgentTask).where(AgentTask.id == task_id, AgentTask.user_id == user.id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def decrypt_prompt(task: AgentTask) -> str:
    return crypto.decrypt(task.prompt_ciphertext, task.prompt_nonce, task.prompt_tag, task.key_version)


def decrypt_result(task: AgentTask) -> str | None:
    if task.result_ciphertext is None:
        return None
    return crypto.decrypt(
        task.result_ciphertext, task.result_nonce, task.result_tag, task.result_key_version
    )


def decrypt_progress(task: AgentTask) -> str | None:
    """Live activity log + partial output while the task is running. None
    once the task reaches a terminal state (see _run_task's terminal update,
    which clears progress_* in favor of the durable result_*/error_text)."""
    if task.progress_ciphertext is None:
        return None
    return crypto.decrypt(
        task.progress_ciphertext, task.progress_nonce, task.progress_tag, task.progress_key_version
    )


async def cancel_task(session: AsyncSession, user: User, task_id: uuid.UUID) -> AgentTask:
    """Best-effort cancel: flips the row to 'cancelled' if still active.

    Cannot interrupt an already-running run_chat_collect() call -- documented
    limitation (PLAN.md Task 3.12). The in-flight worker will still overwrite
    the row with its terminal status when it finishes; this only prevents a
    'queued' task's worker from being trusted, and reflects operator intent
    in the UI immediately.
    """
    task = await get_task(session, user, task_id)
    if task.status not in ACTIVE_TASK_STATUSES:
        raise HTTPException(status_code=409, detail=f"Task is already {task.status}")

    await session.execute(
        update(AgentTask)
        .where(AgentTask.id == task_id)
        .values(status="cancelled", finished_at=sa_func.now())
    )
    await session.commit()
    await session.refresh(task)

    await audit_svc.log(
        action="agent_task_cancelled",
        user_id=user.id,
        resource_type="agent_task",
        resource_id=task_id,
    )
    return task
