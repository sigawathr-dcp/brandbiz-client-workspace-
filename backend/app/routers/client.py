"""
app/routers/client.py

Client-workspace endpoints (Phase 5 §3-4, D21/D22; restructured by the
"Client Workspace — Database Redesign" plan) — require_client_context-gated
(a real client seat uses its own workspace; internal staff with no
workspace of their own preview the seeded demo workspace instead — see
app/deps.py::ClientContext):
  GET  /client/bootstrap      — workspace, agent, engagement journey
  POST /client/engagements    — start a fresh engagement (a returning
                                    client's second brief)
  POST /client/intake/answer  — record an answer, return the next step
  PATCH /client/intake/fields — correct an already-answered field (Task 5.11)
  POST /client/chat            — chat with the workspace's agent (SSE), with
                                    the seat's current plan injected as
                                    context so follow-ups about it land
  POST /client/research        — run the market scan (Perplexity)
  POST /client/cases           — match against the case library (RAG)
  POST /client/plan/draft      — draft a plan (not saved yet)
  POST /client/plan/revise     — apply a client's plain-language edit and
                                    commit it as the next version
  POST /client/plans           — save a drafted plan as an artifact
  PUT  /client/plans/{id}      — save a re-drafted plan as the next version
                                    of an existing plan (Task 5.11)
  GET  /client/plans           — list this seat's saved plans
  GET  /client/plans/{id}      — one plan, decrypted
  GET  /client/plans/{id}/versions/{v} — one historical version's body, read-only (Task 5.12)
  POST /client/plans/{id}/rating — rate a plan (upserted; surfaced on the
                                    expert leads inbox, app/routers/admin_leads.py)

Every governance path (PolicyEngine.decide, quota, audit, encryption) is
inherited unchanged from the internal chat path — this router only decides
WHICH agent a client seat's chat is forced through; it never bypasses how
that call is gated.

DB redesign summary: every step's state now lives on one
app.models.engagement.EngagementStep row (see app/services/engagement.py),
replacing three separate status vocabularies and the old bootstrap helper
that queried audit_log as if it were application state to tell "case
matching never ran" from "ran, found zero matches". Interview answers are
now rows (app/models/intake.py::IntakeAnswer) instead of one encrypted
JSON blob.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import crypto
from app.agents.orchestrator import _compute_cost, run_chat_stream
from app.config import settings
from app.db import get_db
from app.deps import ClientContext, require_client_context
from app.llm.base import ChatMessage
from app.llm.embeddings import EmbeddingError
from app.llm.router import PERPLEXITY_MODEL_CODE, get_router
from app.models.client_intake import (
    CaseMatch,
    CaseMatchExecution,
    CaseStudy,
    ResearchCitation,
    ResearchFinding,
    ResearchRun,
)
from app.models.engagement import Engagement, EngagementStep
from app.models.file import File
from app.models.intake import IntakeAnswer, IntakeOption, IntakeQuestion
from app.models.message import Message
from app.models.plan import Plan
from app.services import agent as agent_svc
from app.services import audit as audit_svc
from app.services import case_match as case_match_svc
from app.services.case_card import CaseCard
from app.services import client_intake as intake_svc
from app.services import engagement as engagement_svc
from app.services import lead as lead_svc
from app.services import plan as plan_svc
from app.services import plan_edit_intent
from app.services import plan_rating as plan_rating_svc
from app.services import quota as quota_svc
from app.services import rate_limit as rate_limit_svc
from app.services import skill as skill_svc
from app.services import workspace as workspace_svc
from app.services.chat_policy import prepare_chat
from app.services.classifier import detect_tier
from app.services.policy_engine import PolicyEngine

router = APIRouter(prefix="/client", tags=["client-workspace"])

_logger = logging.getLogger(__name__)


# The CLIENT_SURFACE_ENABLED kill switch is enforced by
# Depends(require_client_surface) at include_router() level in main.py, not
# per handler — see app/deps.py::require_client_surface for why.


# ---------------------------------------------------------------------------
# Intake-answer helpers
# ---------------------------------------------------------------------------

async def _load_field_values(
    session: AsyncSession, step1: EngagementStep, *, thai_labels: bool
) -> dict[str, list[str]]:
    """The seat's live (non-superseded) intake answers as {field_key:
    [value, ...]} — usually one value, several when the question was
    multi-select. Chip rows resolve through IntakeOption and come back in
    ordinal order (the same order resolve_answers() stored them in), so a
    profile renders identically regardless of click order; free text is
    decrypted."""
    rows = (
        await session.execute(
            select(IntakeAnswer, IntakeOption)
            .outerjoin(IntakeOption, IntakeOption.id == IntakeAnswer.option_id)
            .where(
                IntakeAnswer.engagement_step_id == step1.id, IntakeAnswer.superseded_at.is_(None)
            )
            .order_by(IntakeOption.ordinal)
        )
    ).all()

    fields: dict[str, list[str]] = {}
    for answer, option in rows:
        if option is not None:
            value = option.label if thai_labels else option.value
        else:
            value = crypto.decrypt(
                answer.value_ciphertext, answer.value_nonce, answer.value_tag, answer.key_version
            )
        fields.setdefault(answer.field_key, []).append(value)
    return fields


async def _load_fields(session: AsyncSession, step1: EngagementStep) -> dict[str, str]:
    """Read the seat's live (non-superseded) intake answers as
    {field_key: display_value} — a chip pick resolves through its
    IntakeOption.value; free text is decrypted. A multi-select answer joins
    its values with client_intake.ANSWER_JOINER ("; "), which every consumer
    of this dict (Profile tab, build_context_query's embedding string, the
    drafting prompt) carries as-is; the scorer splits it back apart with
    client_intake.split_answer_values()."""
    values = await _load_field_values(session, step1, thai_labels=False)
    return {k: intake_svc.join_answer_values(v) for k, v in values.items()}


async def _load_fields_th(session: AsyncSession, step1: EngagementStep) -> dict[str, str]:
    """Same as _load_fields(), but a chip answer resolves through
    IntakeOption.LABEL (the Thai text the client actually clicked) instead of
    IntakeOption.value (English, by design — see client_intake.IntakeOption).

    Only the market-scan prompt uses this. _load_fields() stays the canonical
    reader: its English values feed the Profile tab and, more importantly,
    case_match.build_context_query()'s bge-m3 embedding query, where changing
    the language would move every match score shown to a client.

    Reads labels off the engagement's own intake_script_id via the option row,
    so a republished script never retranslates an in-flight engagement.
    """
    values = await _load_field_values(session, step1, thai_labels=True)
    return {k: intake_svc.join_answer_values(v) for k, v in values.items()}


async def _record_answer(
    session: AsyncSession,
    step1: EngagementStep,
    *,
    question_id: uuid.UUID,
    field_key: str,
    option_ids: list[uuid.UUID],
    free_text_value: str | None,
    source: str,
) -> None:
    """Supersede any live answer for this field, then insert the new one —
    one row per picked chip (several on a multi-select question), or a
    single encrypted free-text row. Superseding EVERY live row first is what
    keeps a field's live answer all-chips or one-free-text, never a mix —
    append-only, so PATCH /client/intake/fields leaves real edit history
    behind instead of the old blob-overwrite (the intake_edited audit row
    only ever recorded {"field": name}, never old/new)."""
    await session.execute(
        update(IntakeAnswer)
        .where(IntakeAnswer.engagement_step_id == step1.id, IntakeAnswer.field_key == field_key,
               IntakeAnswer.superseded_at.is_(None))
        .values(superseded_at=datetime.now(timezone.utc))
    )
    if option_ids:
        for option_id in option_ids:
            session.add(IntakeAnswer(
                engagement_step_id=step1.id, question_id=question_id, field_key=field_key,
                option_id=option_id, source=source,
            ))
    else:
        ct, nonce, tag, kv = crypto.encrypt(free_text_value or "")
        session.add(IntakeAnswer(
            engagement_step_id=step1.id, question_id=question_id, field_key=field_key,
            value_ciphertext=ct, value_nonce=nonce, value_tag=tag, key_version=kv, source=source,
        ))


async def _resolve_answer_value(
    session: AsyncSession,
    engagement: Engagement,
    index: int,
    *,
    option_indices: list[int] | None,
    free_text: str | None,
) -> tuple[dict, str, uuid.UUID, list[uuid.UUID], str]:
    """Resolve a chip/free-text answer against the script — no DB write.
    Returns (step_def, display_value, question_id, option_ids, source).
    `display_value` is the joined value string (one value, or a
    multi-select answer's values joined by client_intake.ANSWER_JOINER) —
    the same shape _load_fields() reads back; `option_ids` is empty for
    free text."""
    step_def = await intake_svc.step_at_db(session, engagement.intake_script_id, index)
    if step_def is None:
        raise HTTPException(status_code=400, detail="Unknown intake step")
    try:
        values = intake_svc.resolve_answers(
            step_def, option_indices=option_indices, free_text=free_text
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    question_id = await intake_svc.question_id_at_db(session, engagement.intake_script_id, index)
    option_ids: list[uuid.UUID] = []
    source = "free_text"
    if option_indices:
        option_ids = await intake_svc.option_ids_at_db(session, question_id, option_indices) or []
        source = "chip"
    return step_def, intake_svc.join_answer_values(values), question_id, option_ids, source


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ChipOut(BaseModel):
    index: int
    label: str
    # What resolve_answer() stores for this chip — i.e. the exact string that
    # ends up in `fields`. Only populated on the Profile tab's field manifest
    # (intake_fields), where edit mode needs it to mark which chip is the
    # current answer; the labels are Thai and the stored values English, so
    # matching on `label` can never find it. Stays None for `current_step`,
    # which is asking the question, not replaying an answer.
    value: str | None = None


class CurrentStepOut(BaseModel):
    field: str
    question: str
    options: list[ChipOut]
    # True when IntakeChips should offer toggles + a confirm button (pick
    # several) instead of answering on first tap.
    multi_select: bool = False


async def _current_step_out(session: AsyncSession, engagement: Engagement, step_index: int) -> CurrentStepOut | None:
    step_def = await intake_svc.step_at_db(session, engagement.intake_script_id, step_index)
    if step_def is None:
        return None
    return CurrentStepOut(
        field=step_def["field"],
        question=step_def["question"],
        options=[ChipOut(index=i, label=o["label"]) for i, o in enumerate(step_def["options"])],
        multi_select=bool(step_def.get("multi_select")),
    )


class IntakeFieldOut(BaseModel):
    key: str
    label: str
    options: list[ChipOut] = []
    multi_select: bool = False


class PlanSummaryOut(BaseModel):
    id: uuid.UUID
    title: str
    version: int


class TranscriptTurnOut(BaseModel):
    """One replayed chat bubble. Deliberately the smallest possible shape —
    the rich turn kinds ('research', 'cases', 'plan') are replayed from their
    own tables via research/cases/plans above, so the transcript only ever
    carries plain text.

    `stage` is what lets the frontend slot those rich cards back into the
    right place in the thread: everything 'interview' precedes them,
    everything 'chat' follows.
    """

    who: str  # 'ai' | 'user'
    stage: str  # 'interview' | 'chat'
    text: str


class BootstrapOut(BaseModel):
    workspace: dict
    agent: dict | None
    conversation_id: uuid.UUID | None
    # engagement_id lets the frontend call POST /client/engagements
    # relative to "the current one" later, and active_plan_id replaces the
    # old `bb:activePlan:${workspaceId}` localStorage key — which plan a
    # PUT /client/plans/{id} revision targets is server state now.
    engagement_id: uuid.UUID
    active_plan_id: uuid.UUID | None
    step: int
    total_steps: int
    completed: bool
    fields: dict[str, str]
    intake_fields: list[IntakeFieldOut]
    current_step: CurrentStepOut | None
    plan_count: int
    is_preview: bool
    internal_app_enabled: bool
    # 'idle' | 'pending' | 'done' | 'error' — 'pending' is deliberately
    # never surfaced (see engagement_steps' 5-state status: a step stuck at
    # 'running' with no way to finish reports as 'error' here, same
    # behavior as before the redesign, now driven by one real status
    # column instead of a hardcoded {"pending": "error"} map).
    research_status: str = "idle"
    research: dict | None = None
    cases_status: str = "idle"
    cases: dict | None = None
    # The engagement's saved plan, body included, so the in-thread plan card
    # survives a reload — bootstrap only ever carried plan *titles* (`plans`
    # below), so a refresh dropped the card out of the chat entirely while
    # /w/plans still listed the plan. No status field alongside it, unlike
    # research/cases: this is populated only from a saved artifact, so it is
    # always the equivalent of 'done'. See _plan_replay().
    plan: dict | None = None
    plans: list[PlanSummaryOut] = []
    # The chat bubbles to re-render, oldest first: the interview Q&A followed
    # by any free-form turns. Before this existed the frontend rebuilt the
    # thread synthetically on every reload ("Welcome back — your profile is
    # complete."), so a refresh, a tab close, or a phone locking its screen
    # threw away everything the client had read. See _transcript().
    transcript: list[TranscriptTurnOut] = []


class IntakeAnswerIn(BaseModel):
    option_index: int | None = None
    # Multi-select questions send every picked chip here; single-select
    # callers may keep sending option_index (normalised to a one-item list
    # by `indices`). Setting both is fine as long as they agree.
    option_indices: list[int] | None = None
    free_text: str | None = None

    def indices(self) -> list[int] | None:
        if self.option_indices:
            return self.option_indices
        if self.option_index is not None:
            return [self.option_index]
        return None


class IntakeAnswerOut(BaseModel):
    step: int
    total_steps: int
    completed: bool
    completion_message: str | None
    current_step: CurrentStepOut | None
    insight: str | None = None
    fields: dict[str, str] = Field(default_factory=dict)


class IntakeFieldEditIn(BaseModel):
    field: str
    option_index: int | None = None
    option_indices: list[int] | None = None
    free_text: str | None = None

    def indices(self) -> list[int] | None:
        if self.option_indices:
            return self.option_indices
        if self.option_index is not None:
            return [self.option_index]
        return None


class IntakeEditIn(BaseModel):
    updates: list[IntakeFieldEditIn] = Field(min_length=1)


class IntakeEditOut(BaseModel):
    fields: dict[str, str]
    changed: list[str]
    step: int
    total_steps: int
    completed: bool


class ClientChatIn(BaseModel):
    conversation_id: uuid.UUID | None = None
    content: str
    # Which saved plan this turn is about. Omitted → the engagement's
    # active plan (engagements.active_plan_id). Send it explicitly from a
    # surface that renders one specific plan (the plan document page), so
    # the answer is about the plan on screen rather than whatever was
    # activated last.
    plan_id: uuid.UUID | None = None


_STATUS_OUT = {"idle": "idle", "running": "pending", "done": "done", "failed": "error"}


async def _research_out(session: AsyncSession, run: ResearchRun) -> dict:
    findings = (
        await session.execute(
            select(ResearchFinding.text).where(ResearchFinding.research_run_id == run.id).order_by(ResearchFinding.ordinal)
        )
    ).scalars().all()
    citations = (
        await session.execute(
            select(ResearchCitation).where(ResearchCitation.research_run_id == run.id).order_by(ResearchCitation.ordinal)
        )
    ).scalars().all()
    return {
        "id": str(run.id),
        "findings": [{"text": t} for t in findings],
        "citations": [{"index": i + 1, "source": c.url} for i, c in enumerate(citations)],
    }


def _breakdown_json(result) -> dict | None:
    """The per-dimension contributions behind a match, as stored JSONB.

    None when the tag model is off (case_match_tag_weight = 0) or the corpus
    is untagged — in both cases `score` is the plain cosine similarity it has
    always been, and a breakdown claiming otherwise would be a lie about how
    the number was produced.
    """
    b = getattr(result, "breakdown", None)
    if b is None:
        return None
    return {
        "tag_score": round(b.tag_score, 4),
        "dense_score": round(b.dense_score, 4),
        "final": round(b.final, 4),
        "matched_on": list(b.matched_dimensions),
        "dimensions": [
            {
                "dimension": d.dimension,
                "weight": d.weight,
                "raw": round(d.raw, 4),
                "contribution": round(d.contribution, 4),
                "reason": d.reason,
            }
            for d in b.dimensions
        ],
    }


# Thai names for the scoring dimensions, for the card's "ตรงกับ: …" line.
# Separate from THAI_FIELD_LABELS: that maps intake FIELDS (which include the
# feasibility ones) while this maps the six scoring dimensions a card can
# claim a match on.
_DIMENSION_TH: dict[str, str] = {
    "industry": "อุตสาหกรรม",
    "stage": "ระยะธุรกิจ",
    "audience": "กลุ่มลูกค้า",
    "challenge": "ปัญหา",
    "asset_channel": "ช่องทาง",
    "objective": "เป้าหมาย",
}


def _cases_out(
    rows: list[tuple[CaseMatch, str, uuid.UUID, CaseCard | None, str | None]],
    *,
    library_available: bool,
) -> dict:
    """`image_url` is passed in separately rather than read off `card`: the
    scraped corpus has no images at all, so the parsed CaseCard's image_url is
    always None and the thumbnail has to come from the case_studies catalog
    (populated offline by scripts/backfill_case_images.py). GET /client/
    bootstrap's replay already read the catalog; this is the fresh-match path
    catching up, so a card doesn't gain its image only after a reload.

    `library_available` is False when retrieval saw ZERO chunks — the seat
    can't reach any case file at all (unseeded corpus, scope misconfigured,
    agent with no attachments). That is a setup fault, not "nothing matched
    closely enough", and the two used to render identically; the frontend
    now says which it is."""
    return {
        "library_available": library_available,
        "matches": [
            {
                "file_id": str(file_id),
                "filename": filename,
                "score": round(row.score, 2),
                "rationale": row.rationale,
                "title": card.title if card else None,
                "client": card.client if card else None,
                "category": card.category if card else None,
                "source_url": card.source_url if card else None,
                "summary": card.summary if card else None,
                "image_url": image_url,
                # Which dimensions matched outright, in Thai, for the card's
                # "ตรงกับ: …" line. Empty for matches scored before the tag
                # model existed (score_breakdown IS NULL) — the card then
                # shows the percentage alone, exactly as it used to.
                "matched_on": [
                    _DIMENSION_TH.get(d, d)
                    for d in ((row.score_breakdown or {}).get("matched_on") or [])
                ],
            }
            for row, filename, file_id, card, image_url in rows
        ]
    }


async def _latest_research_run(session: AsyncSession, step2_id: uuid.UUID) -> ResearchRun | None:
    return (
        await session.execute(
            select(ResearchRun).where(ResearchRun.engagement_step_id == step2_id).order_by(ResearchRun.created_at.desc()).limit(1)
        )
    ).scalars().first()


async def _latest_case_run(session: AsyncSession, step3_id: uuid.UUID) -> CaseMatchExecution | None:
    return (
        await session.execute(
            select(CaseMatchExecution).where(CaseMatchExecution.engagement_step_id == step3_id)
            .order_by(CaseMatchExecution.created_at.desc()).limit(1)
        )
    ).scalars().first()


async def _case_matches_for_run(session: AsyncSession, run_id: uuid.UUID) -> dict:
    rows = (
        await session.execute(
            select(CaseMatch, File.filename, File.id, CaseStudy)
            .join(CaseStudy, CaseStudy.id == CaseMatch.case_study_id)
            .join(File, File.id == CaseStudy.file_id)
            .where(CaseMatch.case_match_run_id == run_id)
            .order_by(CaseMatch.rank)
        )
    ).all()
    return {
        # A replay can't re-check reachability; a done run with stored rows
        # necessarily saw the library. With no rows it's unknown, and the
        # frontend falls back to the neutral "nothing matched" copy.
        "library_available": True if rows else None,
        "matches": [
            {
                "file_id": str(file_id),
                "filename": filename,
                "score": round(match.score, 2),
                "rationale": match.rationale,
                "title": card.title,
                "client": card.client_name,
                "category": card.category,
                "source_url": card.source_url,
                "summary": card.summary,
                "image_url": card.image_url,
                # Replayed from the stored breakdown so a reload shows the
                # same "ตรงกับ: …" line the fresh match did. Empty for rows
                # written before 0061 — those cards degrade to the score
                # alone rather than claiming a match they cannot evidence.
                "matched_on": [
                    _DIMENSION_TH.get(d, d)
                    for d in ((match.score_breakdown or {}).get("matched_on") or [])
                ],
            }
            for match, filename, file_id, card in rows
        ]
    }


async def _journey_status(
    session: AsyncSession, steps: dict[str, EngagementStep]
) -> tuple[str, dict | None, str, dict | None]:
    """Replays the latest research run + case match run for bootstrap, in
    the same response shape POST /client/research and POST /client/cases
    return. Step status now comes straight from engagement_steps — no more
    querying audit_log to distinguish 'never ran' from 'ran, found
    nothing' (see app/models/client_intake.py::CaseMatchExecution)."""
    market = steps["market"]
    research_status = _STATUS_OUT.get(market.status, "idle")
    research_out: dict | None = None
    if market.status == "done":
        run = await _latest_research_run(session, market.id)
        if run is not None:
            research_out = await _research_out(session, run)

    cases = steps["cases"]
    cases_status = _STATUS_OUT.get(cases.status, "idle")
    cases_out: dict | None = None
    if cases.status == "done":
        run = await _latest_case_run(session, cases.id)
        if run is not None:
            cases_out = await _case_matches_for_run(session, run.id)

    return research_status, research_out, cases_status, cases_out


# What a plan version with no recorded budget lines replays as. The card
# renders a table only when `lines` is non-empty, so this shows the pricing
# disclaimer and nothing else — the frontend's DraftPlan contract wants a
# budget object, and inventing a null-check on the card for a case that only
# arises on pre-normalization rows buys nothing.
_EMPTY_BUDGET = {
    "lines": [],
    "needs_expert": [],
    "subtotal": "0.00",
    "contingency": "0.00",
    "total": "0.00",
    "currency": "THB",
}


async def _plan_replay(
    session: AsyncSession, engagement: Engagement
) -> dict | None:
    """This engagement's saved plan, in the shape POST /client/plan/draft
    returns plus `id`/`version`, so the frontend can re-render the in-thread
    plan card after a reload.

    Scoped to plans.engagement_id, not just engagements.active_plan_id: the
    plan switcher can point active_plan_id at a plan saved during an EARLIER
    engagement, and replaying that one would drop a foreign plan into this
    engagement's thread. Prefer the active plan when it belongs here, else
    the newest one this engagement produced.

    An unsaved draft is not replayable — POST /client/plan/draft deliberately
    persists nothing (only the drafting prompt + raw JSON reply land in
    messages, tagged with the 'plan' step and filtered out of the
    transcript), so a client who drafted but never pressed Save still comes
    back to a thread with no card. That is the honest state: there is no
    artifact yet.
    """
    plan: Plan | None = None
    if engagement.active_plan_id is not None:
        plan = (
            await session.execute(
                select(Plan).where(
                    Plan.id == engagement.active_plan_id,
                    Plan.engagement_id == engagement.id,
                )
            )
        ).scalars().first()
    if plan is None:
        plan = (
            await session.execute(
                select(Plan)
                .where(Plan.engagement_id == engagement.id)
                .order_by(Plan.created_at.desc())
                .limit(1)
            )
        ).scalars().first()
    if plan is None:
        return None

    version = await plan_svc.get_current_version(session, plan)
    body = plan_svc.decrypt_body(version)
    return {
        "id": str(plan.id),
        "version": version.version_no,
        "title": version.title,
        "core_idea": body.get("core_idea", ""),
        "analogous_case": body.get("analogous_case", ""),
        "adapted_plan": body.get("adapted_plan", []),
        "budget": await plan_svc.budget_out(session, version) or _EMPTY_BUDGET,
        "provenance": await plan_svc.provenance_out(session, version) or {},
        "conversation_id": str(engagement.conversation_id) if engagement.conversation_id else "",
    }


# How many free-form chat bubbles bootstrap replays. Independent of
# chat_policy._HISTORY_LIMIT (which bounds what the *model* is shown, and is
# deliberately much tighter): this is what the *client* is shown, and a long
# thread costs a scrollback, not context window.
_TRANSCRIPT_CHAT_LIMIT = 100


async def _intake_transcript(
    session: AsyncSession, step1: EngagementStep
) -> list[TranscriptTurnOut]:
    """The interview replayed as question/answer bubbles, in script order.

    Reads only live answers (superseded_at IS NULL), so a field edited via
    PATCH /client/intake/fields replays with its current value — the same
    value the Profile tab shows. A chip pick renders through IntakeOption.
    LABEL (the Thai text the client actually clicked), matching what
    ClientWorkspace.tsx echoes as the user turn at answer time; free text
    is decrypted. A multi-select answer spans several live rows but replays
    as ONE user bubble — its labels joined the same way the live echo
    joined them.
    """
    rows = (
        await session.execute(
            select(IntakeAnswer, IntakeQuestion, IntakeOption)
            .join(IntakeQuestion, IntakeQuestion.id == IntakeAnswer.question_id)
            .outerjoin(IntakeOption, IntakeOption.id == IntakeAnswer.option_id)
            .where(
                IntakeAnswer.engagement_step_id == step1.id,
                IntakeAnswer.superseded_at.is_(None),
            )
            .order_by(IntakeQuestion.ordinal, IntakeOption.ordinal)
        )
    ).all()

    # Group the (possibly several) live rows of each question into one
    # answer bubble, keeping question order.
    grouped: dict[uuid.UUID, tuple[IntakeQuestion, list[str]]] = {}
    for answer, question, option in rows:
        if option is not None:
            value = option.label
        else:
            value = crypto.decrypt(
                answer.value_ciphertext,
                answer.value_nonce,
                answer.value_tag,
                answer.key_version,
            )
        grouped.setdefault(question.id, (question, []))[1].append(value)

    turns: list[TranscriptTurnOut] = []
    for question, values in grouped.values():
        turns.append(TranscriptTurnOut(who="ai", stage="interview", text=question.prompt))
        turns.append(
            TranscriptTurnOut(
                who="user", stage="interview", text=intake_svc.join_answer_values(values)
            )
        )
    return turns


async def _chat_transcript(
    session: AsyncSession, conversation_id: uuid.UUID | None
) -> list[TranscriptTurnOut]:
    """The engagement's free-form chat, oldest first, last
    _TRANSCRIPT_CHAT_LIMIT turns only.

    `engagement_step_id IS NULL` is the filter that keeps machine turns out:
    services/plan.py::draft_plan shares this conversation but stamps its
    ~8k-char prompt and raw JSON reply with the 'plan' step, and the client
    saw a plan card for those, not two chat bubbles.

    A turn whose content was purged by D14 retention decrypts to
    crypto.PURGED_PLACEHOLDER; those are dropped rather than shown, since a
    row of placeholders reads as corruption to a client.
    """
    if conversation_id is None:
        return []
    rows = (
        await session.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.engagement_step_id.is_(None),
                Message.role.in_(("user", "assistant")),
            )
            .order_by(Message.created_at.desc())
            .limit(_TRANSCRIPT_CHAT_LIMIT)
        )
    ).scalars().all()

    # created_at is func.now() — TRANSACTION start time in Postgres, so the
    # user turn and the assistant turn of one exchange (persisted in a single
    # commit by agents/orchestrator.py::call_llm) carry the IDENTICAL
    # timestamp and ORDER BY created_at alone leaves them in an arbitrary
    # order. Tie-break on role so the question always precedes its answer.
    ordered = sorted(rows, key=lambda r: (r.created_at, 0 if r.role == "user" else 1))

    turns: list[TranscriptTurnOut] = []
    for row in ordered:
        text = crypto.decrypt_message(
            row.content_ciphertext, row.content_nonce, row.content_tag, row.key_version
        )
        if not text or text == crypto.PURGED_PLACEHOLDER:
            continue
        turns.append(
            TranscriptTurnOut(
                who="user" if row.role == "user" else "ai", stage="chat", text=text
            )
        )
    return turns


async def _transcript(
    session: AsyncSession, step1: EngagementStep, conversation_id: uuid.UUID | None
) -> list[TranscriptTurnOut]:
    """Interview Q&A first, then free-form chat.

    Not a strict merge on timestamp: the interview and the free-form thread
    live in different tables (intake_answers vs messages) and an edited
    answer's answered_at would drag it out of script order. Sequencing by
    funnel stage is both stable and what the client experienced, since the
    interview always precedes free-form chat. The research/cases cards go
    between the two stages — the frontend splits on TranscriptTurnOut.stage
    to place them (see ClientWorkspace.tsx's bootstrap effect).
    """
    return await _intake_transcript(session, step1) + await _chat_transcript(
        session, conversation_id
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/bootstrap", response_model=BootstrapOut)
async def bootstrap(
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> BootstrapOut:
    workspace = await workspace_svc.get_workspace(session, ctx.workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    agent = await workspace_svc.get_workspace_agent(session, ctx.workspace_id)
    engagement = await engagement_svc.get_or_create_active(session, ctx.user, ctx.workspace_id)
    steps = await engagement_svc.get_steps(session, engagement.id)
    step1 = steps["interview"]

    fields = await _load_fields(session, step1)
    total_steps = await intake_svc.total_steps_db(session, engagement.intake_script_id)
    current_index = step1.progress_current or 0
    completed = step1.status == "done"

    plans = await plan_svc.list_plans(session, ctx.user, ctx.workspace_id)
    plan_summaries = []
    for p in plans:
        version = await plan_svc.get_current_version(session, p)
        plan_summaries.append(PlanSummaryOut(id=p.id, title=version.title, version=version.version_no))

    research_status, research_out, cases_status, cases_out = await _journey_status(session, steps)
    plan_out = await _plan_replay(session, engagement)

    agent_out = None
    if agent is not None:
        skill_ids = await skill_svc.get_agent_skill_ids(session, agent.id)
        file_ids = await agent_svc.get_agent_file_ids(session, agent.id)
        agent_out = {
            "id": str(agent.id),
            "name": agent.name,
            "avatar_color": agent.avatar_color,
            "skill_count": len(skill_ids),
            "file_count": len(file_ids),
            "web_search": bool((agent.capabilities or {}).get("web_search", False)),
        }

    return BootstrapOut(
        workspace={"id": str(workspace.id), "name": workspace.name, "slug": workspace.slug},
        agent=agent_out,
        conversation_id=engagement.conversation_id,
        engagement_id=engagement.id,
        active_plan_id=engagement.active_plan_id,
        step=current_index,
        total_steps=total_steps,
        completed=completed,
        fields=fields,
        intake_fields=[IntakeFieldOut(**f) for f in await intake_svc.field_manifest_db(session, engagement.intake_script_id)],
        current_step=await _current_step_out(session, engagement, current_index),
        plan_count=len(plans),
        is_preview=ctx.is_preview,
        internal_app_enabled=settings.client_internal_access_enabled,
        research_status=research_status,
        research=research_out,
        cases_status=cases_status,
        cases=cases_out,
        plan=plan_out,
        plans=plan_summaries,
        transcript=await _transcript(session, step1, engagement.conversation_id),
    )


@router.post("/engagements", response_model=BootstrapOut)
async def start_engagement(
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> BootstrapOut:
    """Start a fresh engagement — a returning client's second brief. The
    old schema's uq_client_profiles_workspace_user made this impossible;
    engagements.status lets a seat hold one ACTIVE engagement plus
    unlimited completed/abandoned ones (see app/models/engagement.py)."""
    await engagement_svc.start_new(session, ctx.user, ctx.workspace_id)
    return await bootstrap(ctx, session)


@router.post("/intake/answer", response_model=IntakeAnswerOut)
async def answer_intake(
    body: IntakeAnswerIn,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> IntakeAnswerOut:
    engagement = await engagement_svc.get_or_create_active(session, ctx.user, ctx.workspace_id)
    step1 = await engagement_svc.get_step(session, engagement.id, "interview")
    total_steps = await intake_svc.total_steps_db(session, engagement.intake_script_id)
    current_index = step1.progress_current or 0
    if current_index >= total_steps:
        raise HTTPException(status_code=400, detail="Intake is already complete")

    step_def, value, question_id, option_ids, source = await _resolve_answer_value(
        session, engagement, current_index,
        option_indices=body.indices(), free_text=body.free_text,
    )
    await _record_answer(
        session, step1, question_id=question_id, field_key=step_def["field"],
        option_ids=option_ids, free_text_value=None if option_ids else value, source=source,
    )

    next_index = current_index + 1
    completed = next_index >= total_steps
    completion_message = None
    if completed:
        await engagement_svc.mark_step(
            session, step1, "done", progress_current=next_index, progress_total=total_steps, commit=False,
        )
        completion_message = intake_svc.INTAKE_COMPLETE_MESSAGE
    else:
        await engagement_svc.mark_step(
            session, step1, "running", progress_current=next_index, progress_total=total_steps, commit=False,
        )
    await session.commit()

    fields = await _load_fields(session, step1)

    await audit_svc.log(
        action="intake_answered",
        user_id=ctx.user.id,
        resource_type="workspace",
        resource_id=ctx.workspace_id,
        details={"field": step_def["field"], "step": current_index},
    )

    return IntakeAnswerOut(
        step=next_index,
        total_steps=total_steps,
        completed=completed,
        completion_message=completion_message,
        current_step=await _current_step_out(session, engagement, next_index),
        insight=step_def.get("insight"),
        fields=fields,
    )


@router.patch("/intake/fields", response_model=IntakeEditOut)
async def edit_intake_fields(
    body: IntakeEditIn,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> IntakeEditOut:
    """Correct one or more already-answered intake fields (Task 5.11 —
    editable company profile). Deliberately does NOT touch
    engagement_steps' interview progress: this is a correction to answers
    already given, not a re-run of the scripted intake. Only a question
    the client has already reached (idx < progress_current) may be
    edited, so this can never skip ahead of the script or pre-fill a
    question not yet asked.

    Rate-limited per user (not per IP — D23 puts every booth attendee in
    one shared workspace, likely behind one NAT IP) so a resubmit can't be
    spammed against the LLM-backed pipeline it triggers downstream. The check
    runs AFTER validation and only when something actually changed: a rejected
    or no-op request must not burn the caller's slot, or a client who corrects
    a typo, gets a 400, and immediately retries is silently 429'd.
    """

    engagement = await engagement_svc.get_or_create_active(session, ctx.user, ctx.workspace_id)
    step1 = await engagement_svc.get_step(session, engagement.id, "interview")
    current_index = step1.progress_current or 0
    fields_before = await _load_fields(session, step1)

    # Resolve and validate everything first, writing nothing — so a 400 on the
    # second of two updates can't leave the first one half-applied, and so the
    # rate-limit slot below is only spent on a request that will really write.
    resolved: list[tuple[str, uuid.UUID, list[uuid.UUID], str]] = []
    for update in body.updates:
        idx = await intake_svc.index_of_field_db(session, engagement.intake_script_id, update.field)
        if idx is None:
            raise HTTPException(status_code=400, detail=f"Unknown field: {update.field}")
        if idx >= current_index:
            raise HTTPException(status_code=400, detail=f"'{update.field}' hasn't been asked yet")

        step_def, value, question_id, option_ids, _source = await _resolve_answer_value(
            session, engagement, idx,
            option_indices=update.indices(), free_text=update.free_text,
        )
        if fields_before.get(update.field) == value:
            continue  # no-op — no new row, no audit entry, nothing worth regenerating
        resolved.append((step_def["field"], question_id, option_ids, value))

    changed: list[str] = []
    if resolved:
        rate_limit_svc.check(f"intake_edit:{ctx.user.id}", limit=5, window_seconds=60)
        for field_key, question_id, option_ids, value in resolved:
            await _record_answer(
                session, step1, question_id=question_id, field_key=field_key,
                # source='edit' (not the chip/free_text the resolver returned)
                # — this row is a correction to an already-answered question,
                # not the original answer; distinguishing the two is exactly
                # what the old single-blob client_profiles.fields_ciphertext
                # could never record.
                option_ids=option_ids, free_text_value=None if option_ids else value, source="edit",
            )
            changed.append(field_key)

    if changed:
        await session.commit()
        for field in changed:
            await audit_svc.log(
                action="intake_edited",
                user_id=ctx.user.id,
                resource_type="workspace",
                resource_id=ctx.workspace_id,
                details={"field": field},
            )
    else:
        await session.rollback()

    fields = await _load_fields(session, step1)
    total_steps = await intake_svc.total_steps_db(session, engagement.intake_script_id)
    return IntakeEditOut(
        fields=fields,
        changed=changed,
        step=current_index,
        total_steps=total_steps,
        completed=step1.status == "done",
    )


async def _resolve_chat_plan(
    session: AsyncSession, ctx: ClientContext, plan_id: uuid.UUID | None
) -> Plan | None:
    """Which saved plan a POST /client/chat turn is about, or None.

    Shared by the two things a chat turn does with a plan: inject it as context
    so the agent can answer questions about it, and decide whether an edit
    request has anything to edit. Resolving once keeps those two from ever
    disagreeing about WHICH plan the client meant.

    An explicit plan_id is ownership-checked by plan_svc.get_plan (404 on
    another seat's plan, exactly like GET /client/plans/{id}); the implicit
    active-plan path deliberately degrades to None instead, since a dangling
    engagements.active_plan_id must not make the client unable to chat.
    """
    if plan_id is not None:
        return await plan_svc.get_plan(session, ctx.user, ctx.workspace_id, plan_id)
    engagement = await engagement_svc.get_or_create_active(session, ctx.user, ctx.workspace_id)
    return await plan_svc.get_active_plan(
        session, ctx.user, ctx.workspace_id, engagement.active_plan_id
    )


async def _plan_chat_context(session: AsyncSession, plan: Plan | None) -> str:
    """The plan block POST /client/chat injects, or "" when this seat has no
    plan yet (pre-plan chat is unchanged).

    A saved plan lives outside the message thread, so without this the agent
    answering "ทำไมงบเฟส 2 เท่านี้" has never seen the plan the client is
    pointing at — see app/services/plan.py's "Plan -> chat context" section.
    """
    if plan is None:
        return ""
    return await plan_svc.plan_context_for_plan(session, plan)


# ---------------------------------------------------------------------------
# Workspace journey -> chat context
# ---------------------------------------------------------------------------
#
# Steps 1-3 of the engagement produce artifacts that live OUTSIDE the message
# thread: the interview is intake_answers rows (services/client_intake.py runs
# it as a deterministic DB flow, not as LLM turns), the market scan is
# research_findings, the case match is case_matches. The client reads all
# three in their workspace, but chat_policy.load_history_messages() only ever
# reads `messages` — so a client who had just spent nine questions explaining
# their brand hit a chat that knew none of it, and "ทำไมถึงเลือกเคสนี้ให้"
# hit a model that had never seen the cards on the client's screen.
#
# Same hole plan.py's "Plan -> chat context" section closes for a saved plan,
# and the same fix: rebuild each artifact into a system block every turn,
# rather than trying to get it into the transcript.
#
# Every block is bounded. The comment on chat_policy._HISTORY_CHAR_BUDGET is
# the reason: past the local model's context window the server has no budget
# left to generate and returns an EMPTY reply, so context that grows with the
# client's typing (a pasted free-text answer, a long market scan) has to be
# cut here rather than silently costing the answer.


def _clip(text: str | None, limit: int) -> str:
    value = (text or "").strip()
    return value[:limit] + "…" if len(value) > limit else value


# Longest single intake answer the profile block copies. The interview is nine
# questions, so the block is bounded by construction — except for free-text
# answers, which are whatever the client pasted.
_INTAKE_CONTEXT_VALUE_CHARS = 400

# Market scan: how many findings, and how long each may be. A scan is ~6-10
# bullets; the cap is a ceiling on a bad run, not the normal case.
_RESEARCH_CONTEXT_FINDINGS = 10
_RESEARCH_CONTEXT_TEXT_CHARS = 300

# Case match: capped at rag_top_k (config.py), i.e. the cards the client is
# actually looking at. Summaries come from the scraped corpus and can run long,
# so they are clipped harder than the rationale น้องภูมิ wrote.
_CASES_CONTEXT_MATCHES = 5
_CASES_CONTEXT_SUMMARY_CHARS = 240
_CASES_CONTEXT_RATIONALE_CHARS = 300


async def _workspace_chat_context(session: AsyncSession, ctx: ClientContext) -> str:
    """Everything the client's journey has produced so far, as system context.

    One engagement lookup for all three blocks — a chat turn already pays for
    plan resolution, RAG and the policy decision, and this is exactly where
    three more `get_or_create_active` round-trips would otherwise creep in.

    Order is journey order (profile -> market scan -> cases), and client_chat()
    appends the plan block after these: a plan is answered against the profile
    it was drafted from, so the profile must not be what ends up furthest from
    the question.
    """
    engagement = await engagement_svc.get_or_create_active(session, ctx.user, ctx.workspace_id)
    steps = {
        name: await engagement_svc.get_step(session, engagement.id, name)
        for name in ("interview", "market", "cases")
    }
    blocks = [
        await _intake_chat_context(session, steps["interview"]),
        await _research_chat_context(session, steps["market"]),
        await _cases_chat_context(session, steps["cases"]),
    ]
    return "\n\n".join(filter(None, blocks))


async def _intake_chat_context(session: AsyncSession, step1: EngagementStep) -> str:
    """The seat's interview answers, rendered as a system-context block.

    Live answers only (`superseded_at IS NULL`), in script order, so a field
    corrected via PATCH /client/intake/fields reaches the model with the value
    the Profile tab shows. Included while the interview is still in progress
    too — half a profile is still nine questions' worth of things not to ask
    twice.
    """
    turns = await _intake_transcript(session, step1)
    if not turns:
        return ""

    lines = [
        "[CLIENT PROFILE — answers this client already gave in the intake interview]",
        "These are established facts about this client, collected by น้องภูมิ in "
        "this workspace. Use them when you answer. Never ask again for anything "
        "answered here; ask only about what is missing. Reply in Thai unless the "
        "client writes in another language.",
        "",
    ]
    # _intake_transcript emits (question, answer) pairs in script order.
    for question, answer in zip(turns[::2], turns[1::2]):
        lines.append(
            f"- {question.text.strip()} → {_clip(answer.text, _INTAKE_CONTEXT_VALUE_CHARS)}"
        )
    return "\n".join(lines)


async def _research_chat_context(session: AsyncSession, step2: EngagementStep) -> str:
    """The market scan the client has already read, as a system-context block.

    Finished runs only. A running one has no findings yet and a failed one has
    none at all — either way the client is not looking at numbers the chat
    would have to explain.

    Findings are reproduced verbatim, [n] markers included, because the source
    list is reproduced with them: a model that paraphrases a finding and keeps
    its marker has silently reattributed a claim to a source that does not make
    it. That is also why the header forbids adding findings — this block is the
    whole of what น้องภูมิ can evidence about this market.
    """
    run = await _latest_research_run(session, step2.id)
    if run is None or run.status != "done":
        return ""
    out = await _research_out(session, run)
    findings = out["findings"][:_RESEARCH_CONTEXT_FINDINGS]
    if not findings:
        return ""

    lines = [
        "[MARKET SCAN — findings น้องภูมิ already showed this client]",
        "น้องภูมิ ran this market scan for the client, and the client has read it "
        "in their workspace. Answer follow-up questions from these findings. "
        "Keep the [n] citation markers exactly as written, quote a finding "
        "rather than rephrasing what it claims, and never add a finding that is "
        "not listed here — say the scan does not cover it instead.",
        "",
    ]
    lines.extend(f"- {_clip(f['text'], _RESEARCH_CONTEXT_TEXT_CHARS)}" for f in findings)
    citations = out["citations"]
    if citations:
        lines.append("Sources:")
        lines.extend(f"[{c['index']}] {c['source']}" for c in citations)
    return "\n".join(lines)


async def _cases_chat_context(session: AsyncSession, step3: EngagementStep) -> str:
    """The matched case studies on the client's screen, as system context.

    `score` is handed over exactly as the card shows it (already rounded by
    _case_matches_for_run): a chat turn quoting a different figure than the
    card next to it reads as น้องภูมิ contradicting itself, not as rounding.

    The header pins where the ranking came from — a bge-m3 + tag-model score
    over the case corpus (services/case_match.py), not the chat model's
    judgement — so the chat explains a rank it must not re-derive.
    """
    run = await _latest_case_run(session, step3.id)
    if run is None or run.status != "done":
        return ""
    matches = (await _case_matches_for_run(session, run.id))["matches"][:_CASES_CONTEXT_MATCHES]
    if not matches:
        return ""

    lines = [
        "[MATCHED CASE STUDIES — the cards this client is looking at]",
        "น้องภูมิ matched these Brandbiz case studies to this client's profile, "
        "ranked best first. The score is a similarity number produced by the "
        "matching engine, not your judgement: quote it exactly, explain a match "
        "from the rationale and the fields below, and never re-rank the cards or "
        "offer a case that is not listed here.",
        "",
    ]
    for i, m in enumerate(matches, start=1):
        head = f"{i}. {m['title'] or m['filename']}"
        if m["client"]:
            head += f" — {m['client']}"
        head += f" (score {m['score']})"
        lines.append(head)
        if m["category"]:
            lines.append(f"   Category: {m['category']}")
        if m["matched_on"]:
            lines.append(f"   ตรงกับ: {', '.join(m['matched_on'])}")
        summary = _clip(m["summary"], _CASES_CONTEXT_SUMMARY_CHARS)
        if summary:
            lines.append(f"   Summary: {summary}")
        rationale = _clip(m["rationale"], _CASES_CONTEXT_RATIONALE_CHARS)
        if rationale:
            lines.append(f"   Why it matched: {rationale}")
    return "\n".join(lines)


async def _suggest_plan_edit(
    session: AsyncSession, ctx: ClientContext, plan: Plan | None, content: str
) -> bool:
    """Should this chat turn offer the "ปรับแผนให้เลย" chip?

    Three conditions, cheapest first: the turn reads as an edit request, there
    is a saved plan to edit, and the intake is finished. The last one is checked
    server-side rather than trusted from the frontend for the same reason
    POST /client/plan/draft checks it — a plan revised against a half-answered
    profile is a plan drafted from nothing.

    A True here only surfaces a chip. Nothing is revised until the client
    confirms and the frontend calls POST /client/plan/revise, so a false
    positive costs one ignorable chip and never a silent rewrite of a budget.
    """
    if plan is None or not plan_edit_intent.detect(content):
        return False
    engagement = await engagement_svc.get_or_create_active(session, ctx.user, ctx.workspace_id)
    step1 = await engagement_svc.get_step(session, engagement.id, "interview")
    return step1.status == "done"


@router.post("/chat")
async def client_chat(
    body: ClientChatIn,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    agent = await workspace_svc.get_workspace_agent(session, ctx.workspace_id)
    if agent is None:
        raise HTTPException(status_code=503, detail="This workspace has no assigned agent yet")

    plan = await _resolve_chat_plan(session, ctx, body.plan_id)
    plan_context = await _plan_chat_context(session, plan)
    workspace_context = await _workspace_chat_context(session, ctx)
    edit_suggested = await _suggest_plan_edit(session, ctx, plan, body.content)

    prepared = await prepare_chat(
        session=session,
        user=ctx.user,
        conversation_id=body.conversation_id,
        user_content=body.content,
        requested_model="auto",
        agent_id=agent.id,  # forced — never trust a client-supplied agent_id
        workspace_id=ctx.workspace_id,
        # Journey first, plan last: the plan block's money rules are then
        # the last thing the model reads before the history, and the plan
        # is read against the profile it was drafted from.
        extra_context="\n\n".join(filter(None, [workspace_context, plan_context])),
    )
    return StreamingResponse(
        run_chat_stream(
            session=session,
            user_id=ctx.user.id,
            user=ctx.user,
            resolved_conversation_id=prepared.resolved_conversation_id,
            user_content=body.content,
            model_code=prepared.model_code,
            history=prepared.history,
            downgrade_to_local=prepared.downgrade_to_local,
            reasons=prepared.reasons,
            image_model_code=prepared.image_model_code,
            n8n_route=prepared.n8n_route,
            rag_context=prepared.rag_context,
            citations=prepared.citations,
            system_prompt=prepared.system_prompt,
            tuning=prepared.tuning,
            # Surfaces as an SSE notice the frontend turns into a confirmation
            # chip. The plan id rides along so the confirm posts against the
            # plan this turn was actually resolved against, not whatever is
            # active by the time the client taps it.
            plan_edit_plan_id=plan.id if edit_suggested and plan is not None else None,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_RESEARCH_SYSTEM_PROMPT = (
    "You are a market research analyst for a Thai brand strategy agency. "
    "Search international and Thai-language sources as needed. "
    "Write your entire answer in Thai (ภาษาไทย), in natural business Thai that a Thai "
    "brand strategist would use with a client. "
    "Keep brand names, company names, report/publisher names and metric names in their "
    "original language. Keep the [n] citation markers exactly as produced. "
    "Use short markdown bullets. Do not add a preamble or a closing summary."
)


def _build_research_query(fields_th: Mapping[str, str]) -> str:
    """The market scan's USER turn — deliberately Thai end to end.

    The system prompt above already asks for Thai, but Perplexity's Sonar
    weights the user turn (and the sources its web search retrieves off that
    turn) far more heavily than a system message. An all-English user turn made
    it search English sources and answer in English regardless. So the language
    instruction is repeated here and the business context is rendered with Thai
    labels + the Thai chip labels the client actually clicked — same pattern as
    plan.py::_build_drafting_prompt, which is the one prompt in this repo that
    has reliably produced Thai.

    Pure (takes an already-loaded fields dict) so it is unit-testable without a
    DB — see tests/unit/test_research_prompt.py.
    """
    ordered = [step["field"] for step in intake_svc.INTAKE_SCRIPT]
    # Same reason as case_match.build_context_query: an engagement pinned to
    # an older script version answers slots the current script no longer has
    # (v1's goal / horizon / history), and dropping them would send a
    # thinner brief to the market scan than the client actually gave.
    ordered += sorted(k for k in fields_th if k not in set(ordered))
    context = "; ".join(
        f"{intake_svc.THAI_FIELD_LABELS.get(k, k)}: {fields_th[k]}"
        for k in ordered
        if k in fields_th
    )
    return (
        "ช่วยวิเคราะห์ตลาดและคู่แข่งของธุรกิจนี้ให้หน่อยครับ "
        "ขอข้อมูลที่เป็นรูปธรรม ทันสมัย และนำไปใช้ได้จริงในแผนที่จะนำเสนอลูกค้า\n"
        "ตอบเป็นภาษาไทยทั้งหมด เป็นภาษาธุรกิจที่นักวางกลยุทธ์แบรนด์ใช้คุยกับลูกค้า "
        "(ชื่อแบรนด์ ชื่อบริษัท ชื่อรายงาน/สำนักที่เผยแพร่ และชื่อตัวชี้วัด ให้คงภาษาเดิมไว้ "
        "และคงเครื่องหมายอ้างอิง [n] ไว้ตามเดิม)\n\n"
        f"ข้อมูลธุรกิจ: {context}"
    )


@router.post("/research")
async def run_research(
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """The "External market scan · IAG" step. IAG ≈ Perplexity (per
    DSME_ai.md's mapping) — routed through PolicyEngine.decide() at the
    Perplexity model code exactly like an internal user's chat would be.

    Prompted in Thai on BOTH turns (see _build_research_query) — the system
    message alone wasn't enough to stop Sonar answering in English.
    """
    user = ctx.user
    engagement = await engagement_svc.get_or_create_active(session, user, ctx.workspace_id)
    step1 = await engagement_svc.get_step(session, engagement.id, "interview")
    if step1.status != "done":
        raise HTTPException(status_code=400, detail="Complete the intake before running research")
    step2 = await engagement_svc.get_step(session, engagement.id, "market")

    query = _build_research_query(await _load_fields_th(session, step1))

    tier = detect_tier(query)
    estimated_tokens = max(1, len(query) // 4)
    decision = await PolicyEngine(session).decide(user, PERPLEXITY_MODEL_CODE, tier, estimated_tokens)
    if not decision.allowed or decision.downgrade_to_local:
        await audit_svc.log(
            action="model_blocked",
            user_id=user.id,
            resource_type="workspace",
            resource_id=ctx.workspace_id,
            details={
                "model_requested": PERPLEXITY_MODEL_CODE,
                "reasons": [r.value if hasattr(r, "value") else str(r) for r in decision.reasons],
            },
        )
        raise HTTPException(
            status_code=403, detail="Market research is not available for this workspace right now"
        )

    await engagement_svc.mark_step(session, step2, "running")

    ct, nonce, tag, kv = crypto.encrypt(query)
    run = ResearchRun(
        engagement_step_id=step2.id,
        query_ciphertext=ct, query_nonce=nonce, query_tag=tag, key_version=kv,
        status="running",
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    full_text = ""
    citations_raw: list[str] = []
    tokens_in = tokens_out = 0
    try:
        client = get_router().get(PERPLEXITY_MODEL_CODE)
        async for chunk in client.stream_chat([
            ChatMessage(role="system", content=_RESEARCH_SYSTEM_PROMPT),
            ChatMessage(role="user", content=query),
        ]):
            full_text += chunk.content
            if chunk.metadata and chunk.metadata.get("citations"):
                citations_raw = chunk.metadata["citations"]
            if chunk.prompt_tokens:
                tokens_in = chunk.prompt_tokens
            if chunk.completion_tokens:
                tokens_out = chunk.completion_tokens
    except Exception as exc:
        run.status = "failed"
        run.error_detail = str(exc)[:500]
        await session.commit()
        await engagement_svc.mark_step(session, step2, "failed", error_code="research_call_failed", error_detail=str(exc)[:500])
        raise HTTPException(
            status_code=502, detail="Market research is temporarily unavailable"
        ) from exc

    findings_text = [s.strip() for s in full_text.split("\n") if s.strip()]
    for i, text in enumerate(findings_text):
        session.add(ResearchFinding(research_run_id=run.id, ordinal=i, text=text))
    for i, url in enumerate(citations_raw):
        session.add(ResearchCitation(research_run_id=run.id, ordinal=i, url=url))

    run.model_used = PERPLEXITY_MODEL_CODE
    run.status = "done"
    run.tokens_input = tokens_in
    run.tokens_output = tokens_out
    run.completed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(run)

    cost = await _compute_cost(session, PERPLEXITY_MODEL_CODE, tokens_in, tokens_out)
    await quota_svc.consume(session, user, tokens_in, tokens_out, cost)

    await engagement_svc.mark_step(session, step2, "done")

    await audit_svc.log(
        action="research_run",
        user_id=user.id,
        resource_type="workspace",
        resource_id=ctx.workspace_id,
        details={"research_run_id": str(run.id), "citation_count": len(citations_raw)},
    )

    return await _research_out(session, run)


@router.post("/cases")
async def run_case_match(
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Score the client's profile against the case library attached to the
    workspace's agent — via app/services/case_match.match_cases().

    Each call is a NEW case_match_runs row with its own append-only
    case_matches rows (the old table deleted-and-reinserted this seat's
    rows every call, destroying match history). Readers always take the
    LATEST done run for this engagement's step, so a re-run still can't
    leak stale/duplicate cases into a drafted plan.

    Calls match_cases(strict=True): an embed-server outage must surface as
    a real failure here, not as "no case studies matched closely enough"
    (rag_search.retrieve()'s default strict=False degrades chat to a
    non-RAG answer, which is right for chat but would misreport an outage
    as "the library has nothing relevant" for this endpoint).
    """
    user = ctx.user
    engagement = await engagement_svc.get_or_create_active(session, user, ctx.workspace_id)
    step1 = await engagement_svc.get_step(session, engagement.id, "interview")
    if step1.status != "done":
        raise HTTPException(status_code=400, detail="Complete the intake before matching cases")
    step3 = await engagement_svc.get_step(session, engagement.id, "cases")

    agent = await workspace_svc.get_workspace_agent(session, ctx.workspace_id)
    agent_file_ids = await agent_svc.get_agent_file_ids(session, agent.id) if agent else None

    fields = await _load_fields(session, step1)
    query = case_match_svc.build_context_query(fields)
    await engagement_svc.mark_step(session, step3, "running")

    ct, nonce, tag, kv = crypto.encrypt(query)
    run = CaseMatchExecution(
        engagement_step_id=step3.id,
        query_ciphertext=ct, query_nonce=nonce, query_tag=tag, key_version=kv,
        status="running",
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    try:
        match_run = await case_match_svc.match_cases(
            session,
            user,
            fields,
            agent_file_ids=agent_file_ids,
            effective_workspace_id=ctx.workspace_id,
            query=query,
            strict=True,
        )
    except EmbeddingError as exc:
        run.status = "failed"
        run.error_detail = str(exc)[:500]
        await session.commit()
        await engagement_svc.mark_step(
            session, step3, "failed", error_code="embed_unreachable", error_detail=str(exc)[:500]
        )
        raise HTTPException(
            status_code=502, detail="Case matching is temporarily unavailable"
        ) from exc

    run.status = "done"
    run.match_count = len(match_run.results)
    run.completed_at = datetime.now(timezone.utc)
    session.add(run)
    await session.flush()

    rows: list[tuple[CaseMatch, str, uuid.UUID, CaseCard | None, str | None]] = []
    for r in match_run.results:
        case_study = (
            await session.execute(select(CaseStudy).where(CaseStudy.file_id == r.file_id))
        ).scalar_one_or_none()
        if case_study is None:
            # Newly ingested/never-cataloged file — catalog it now instead
            # of failing the whole match (app/services/case_card.py already
            # parsed it into `r.card`). workspace_id stays NULL: the corpus
            # is the shared library (ADR 0002), and stamping the first
            # matching client's tenant onto a catalog row every other tenant
            # reads would be wrong on its face.
            case_study = CaseStudy(
                workspace_id=None, file_id=r.file_id,
                title=r.card.title if r.card else None,
                client_name=r.card.client if r.card else None,
                category=r.card.category if r.card else None,
                source_url=r.card.source_url if r.card else None,
                image_url=r.card.image_url if r.card else None,
                summary=r.card.summary if r.card else None,
            )
            session.add(case_study)
            await session.flush()

        match = CaseMatch(
            case_match_run_id=run.id, case_study_id=case_study.id, rank=r.rank,
            score=r.score, rationale=r.rationale,
            score_breakdown=_breakdown_json(r),
        )
        session.add(match)
        rows.append((match, r.filename, r.file_id, r.card, case_study.image_url))
    await session.commit()

    await engagement_svc.mark_step(session, step3, "done")

    await audit_svc.log(
        action="case_matched",
        user_id=user.id,
        resource_type="workspace",
        resource_id=ctx.workspace_id,
        details={"match_count": len(rows), "case_match_run_id": str(run.id)},
    )

    if match_run.chunks_retrieved == 0:
        _logger.warning(
            "case match: zero chunks reachable for workspace %s (agent files=%s) — "
            "case library unseeded or not library-scoped? (ADR 0002)",
            ctx.workspace_id,
            None if agent_file_ids is None else len(agent_file_ids),
        )
    return _cases_out(rows, library_available=match_run.chunks_retrieved > 0)


# ---------------------------------------------------------------------------
# Plans (Phase 4)
# ---------------------------------------------------------------------------

class SavePlanIn(BaseModel):
    title: str
    core_idea: str
    analogous_case: str
    adapted_plan: list[dict]
    budget: dict
    provenance: dict
    conversation_id: uuid.UUID | None = None


class PlanVersionOut(BaseModel):
    version: int
    created_at: datetime


class PlanVersionBodyOut(BaseModel):
    version: int
    created_at: datetime
    title: str
    core_idea: str
    analogous_case: str
    adapted_plan: list[dict]
    budget: dict | None
    provenance: dict | None


class PlanRatingIn(BaseModel):
    score: int = Field(ge=1, le=10)
    comment: str | None = Field(default=None, max_length=2000)


class PlanRatingOut(BaseModel):
    score: int
    comment: str | None
    created_at: datetime


class PlanOut(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    version: int
    core_idea: str
    analogous_case: str
    adapted_plan: list[dict]
    budget: dict | None
    provenance: dict | None
    created_at: datetime
    agent_name: str | None = None
    versions: list[PlanVersionOut] = []
    rating: PlanRatingOut | None = None


async def _plan_out(session: AsyncSession, plan, *, agent_name: str | None = None, with_versions: bool = False, rating=None) -> PlanOut:
    version = await plan_svc.get_current_version(session, plan)
    body = plan_svc.decrypt_body(version)
    versions_out: list[PlanVersionOut] = []
    if with_versions:
        versions = await plan_svc.list_versions(session, plan.id)
        versions_out = [PlanVersionOut(version=v.version_no, created_at=v.created_at) for v in versions]
    return PlanOut(
        id=plan.id,
        title=version.title,
        status=plan.status,
        version=version.version_no,
        core_idea=body.get("core_idea", ""),
        analogous_case=body.get("analogous_case", ""),
        adapted_plan=body.get("adapted_plan", []),
        budget=await plan_svc.budget_out(session, version),
        provenance=await plan_svc.provenance_out(session, version),
        created_at=plan.created_at,
        agent_name=agent_name,
        versions=versions_out,
        rating=(
            PlanRatingOut(score=rating.score, comment=rating.comment, created_at=rating.created_at)
            if rating is not None else None
        ),
    )


class ClientPlanReviseIn(BaseModel):
    # What the client typed, verbatim — one line, not a prompt. Bounded because
    # it is pasted into the revision prompt alongside the whole plan and the
    # rate card, and the local model's context window is the real budget here.
    instruction: str = Field(min_length=1, max_length=2000)
    # Same resolution rule as ClientChatIn.plan_id: omitted → the engagement's
    # active plan.
    plan_id: uuid.UUID | None = None


@router.post("/plan/revise")
async def revise_plan_from_chat(
    body: ClientPlanReviseIn,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Apply a client's plain-language edit to their plan and commit it as the
    next version.

    Unlike POST /client/plan/draft this SAVES: the client already confirmed
    (the chip that routed them here), so a second Save step would be
    confirmation theatre. PlanVersion is append-only, so version history is the
    undo — and plan_svc.revise_plan never touches plan.status, meaning a
    chat-revised plan stays "draft · awaiting expert review" exactly like the
    original.

    The intake gate is the same one POST /client/plan/draft enforces, and for
    the same reason: it is checked here rather than trusted from the frontend.
    """
    engagement = await engagement_svc.get_or_create_active(session, ctx.user, ctx.workspace_id)
    step1 = await engagement_svc.get_step(session, engagement.id, "interview")
    if step1.status != "done":
        _logger.warning(
            "plan/revise: workspace %s user %s intake incomplete at step %d",
            ctx.workspace_id, ctx.user.id, step1.progress_current or 0,
        )
        raise HTTPException(status_code=400, detail="Complete the intake before editing a plan")

    plan = await _resolve_chat_plan(session, ctx, body.plan_id)
    if plan is None:
        # 409, not 404: nothing is missing at the URL the client asked for —
        # this seat simply has no saved plan yet, which the frontend recovers
        # from by offering "draft a plan" rather than showing an error.
        raise HTTPException(status_code=409, detail="Save a plan before editing it")

    return await plan_svc.revise_from_instruction(
        session, ctx.user, ctx.workspace_id, engagement, plan, body.instruction
    )


@router.post("/plan/draft")
async def draft_plan(
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Draft the 4-part plan but do not save it — the frontend shows this
    as a preview with a "Save as a plan" action (POST /client/plans)
    before it becomes a durable artifact."""
    engagement = await engagement_svc.get_or_create_active(session, ctx.user, ctx.workspace_id)
    step1 = await engagement_svc.get_step(session, engagement.id, "interview")
    if step1.status != "done":
        _logger.warning(
            "plan/draft: workspace %s user %s intake incomplete at step %d",
            ctx.workspace_id, ctx.user.id, step1.progress_current or 0,
        )
        raise HTTPException(status_code=400, detail="Complete the intake before drafting a plan")
    step4 = await engagement_svc.get_step(session, engagement.id, "plan")

    fields = await _load_fields(session, step1)
    if step4.status == "idle":
        await engagement_svc.mark_step(session, step4, "running")
    try:
        draft = await plan_svc.draft_plan(session, ctx.user, ctx.workspace_id, engagement, fields)
    except HTTPException:
        if step4.status != "done":
            await engagement_svc.mark_step(session, step4, "failed", error_code="draft_failed")
        raise
    return draft


@router.post("/plans", status_code=201, response_model=PlanOut)
async def save_plan(
    body: SavePlanIn,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlanOut:
    engagement = await engagement_svc.get_or_create_active(session, ctx.user, ctx.workspace_id)
    plan = await plan_svc.save_plan(session, ctx.user, ctx.workspace_id, engagement, body.model_dump())
    step4 = await engagement_svc.get_step(session, engagement.id, "plan")
    await engagement_svc.mark_step(session, step4, "done")
    agent = await workspace_svc.get_workspace_agent(session, ctx.workspace_id)
    return await _plan_out(session, plan, agent_name=agent.name if agent else None)


@router.put("/plans/{plan_id}", response_model=PlanOut)
async def revise_plan(
    plan_id: uuid.UUID,
    body: SavePlanIn,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlanOut:
    """Save a re-drafted plan over an existing one (Task 5.11)."""
    plan = await plan_svc.revise_plan(session, ctx.user, ctx.workspace_id, plan_id, body.model_dump())
    agent = await workspace_svc.get_workspace_agent(session, ctx.workspace_id)
    return await _plan_out(session, plan, agent_name=agent.name if agent else None)


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[PlanOut]:
    plans = await plan_svc.list_plans(session, ctx.user, ctx.workspace_id)
    agent = await workspace_svc.get_workspace_agent(session, ctx.workspace_id)
    agent_name = agent.name if agent else None
    return [await _plan_out(session, p, agent_name=agent_name) for p in plans]


@router.get("/plans/{plan_id}", response_model=PlanOut)
async def get_plan(
    plan_id: uuid.UUID,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlanOut:
    plan = await plan_svc.get_plan(session, ctx.user, ctx.workspace_id, plan_id)
    rating = await plan_rating_svc.get_rating(session, ctx.user, ctx.workspace_id, plan_id)
    agent = await workspace_svc.get_workspace_agent(session, ctx.workspace_id)
    return await _plan_out(session, plan, agent_name=agent.name if agent else None, with_versions=True, rating=rating)


@router.get("/plans/{plan_id}/versions/{version}", response_model=PlanVersionBodyOut)
async def get_plan_version(
    plan_id: uuid.UUID,
    version: int,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlanVersionBodyOut:
    """Task 5.12 — the version rail's "read an old version" affordance.
    Read-only: no audit action, no rate limit."""
    v = await plan_svc.get_version(session, ctx.user, ctx.workspace_id, plan_id, version)
    body = plan_svc.decrypt_version_body(v)
    return PlanVersionBodyOut(
        version=v.version_no,
        created_at=v.created_at,
        title=v.title,
        core_idea=body.get("core_idea", ""),
        analogous_case=body.get("analogous_case", ""),
        adapted_plan=body.get("adapted_plan", []),
        budget=await plan_svc.budget_out(session, v),
        provenance=await plan_svc.provenance_out(session, v),
    )


@router.post("/plans/{plan_id}/rating", response_model=PlanRatingOut)
async def rate_plan(
    plan_id: uuid.UUID,
    body: PlanRatingIn,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlanRatingOut:
    if ctx.is_preview:
        raise HTTPException(
            status_code=400,
            detail="You're previewing the demo workspace — ratings are disabled here so a "
            "walkthrough never shows up as real client feedback. This works normally for a "
            "real attendee who arrived via an invite link.",
        )
    rating = await plan_rating_svc.upsert_rating(
        session, ctx.user, ctx.workspace_id, plan_id, score=body.score, comment=body.comment
    )
    return PlanRatingOut(score=rating.score, comment=rating.comment, created_at=rating.created_at)


@router.post("/plans/{plan_id}/activate")
async def activate_plan(
    plan_id: uuid.UUID,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """The plan switcher's "make this the active one" action — server-side
    replacement for the old `bb:activePlan:*` localStorage key (Task 5.12).
    plan_svc.get_plan is the ownership check (404s on a plan this seat
    doesn't own) before engagements.active_plan_id is touched."""
    plan = await plan_svc.get_plan(session, ctx.user, ctx.workspace_id, plan_id)
    engagement = await engagement_svc.get_or_create_active(session, ctx.user, ctx.workspace_id)
    await engagement_svc.set_active_plan(session, engagement, plan.id)
    return {"active_plan_id": str(plan.id)}


@router.post("/plans/{plan_id}/share")
async def share_plan(
    plan_id: uuid.UUID,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Mint (or re-mint) a share token for a plan — GET /public/plans/{token}
    is the read-only page that resolves it."""
    raw = await plan_svc.create_share_token(session, ctx.user, ctx.workspace_id, plan_id)
    return {"token": raw, "share_path": f"/p/{raw}"}


# ---------------------------------------------------------------------------
# Lead capture (Phase 5) — "Talk to an expert"
# ---------------------------------------------------------------------------

class LeadIn(BaseModel):
    plan_id: uuid.UUID | None = None
    contact_name: str | None = None
    contact_phone_or_line: str | None = None
    best_time: str | None = None


@router.post("/leads", status_code=201)
async def submit_lead(
    body: LeadIn,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    if ctx.is_preview:
        raise HTTPException(
            status_code=400,
            detail="You're previewing the demo workspace — lead capture is disabled here so a "
            "walkthrough never creates a real lead. This works normally for a real attendee "
            "who arrived via an invite link.",
        )
    lead = await lead_svc.submit(
        session,
        ctx.user,
        plan_id=body.plan_id,
        contact_name=body.contact_name,
        contact_phone_or_line=body.contact_phone_or_line,
        best_time=body.best_time,
    )
    return {"id": str(lead.id), "status": lead.status, "delivered": lead.n8n_error is None}
