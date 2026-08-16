"""
app/services/plan.py

Draft + persist Plans (Phase 5 §4, D21/D22; restructured by the "Client
Workspace — Database Redesign" plan) — the 4-part plan promoted out of
chat into a standalone, versioned artifact (see app/models/plan.py for why
it lives outside messages.content_*, and for the head/version split).

draft_plan() asks the workspace's agent for narrative sections PLUS rate-
card item codes — never a price. The price is computed by
app/services/rate_card.py::price(), never the model; a hallucinated budget
in front of a real prospect is worse than no budget (see PLAN.md Phase 5).

draft_plan() now resolves the research run and case matches it draws on
via the engagement's own step 2/3 records (engagement_step_id), not a bare
(workspace_id, user_id) filter — the old filter didn't scope by
conversation_id even though every other reader did, so a seat with more
than one conversation could get a plan drafted from a DIFFERENT
conversation's research/cases than the one the client was actually
looking at. An engagement now has exactly one conversation, so this
divergence can't happen anymore.

Money/provenance are stored as normalized rows (PlanBudgetLine,
PlanSource) — see app/models/plan.py — but this module still hands back
and accepts the same dict shapes the frontend/API contract already used
(`{"lines": [...], "subtotal": "0.00", ...}` /
`{"rate_card_codes": [...], "case_files": [...], ...}`), so
app/routers/client.py and the frontend types are unaffected by the
storage change.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import uuid
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crypto
from app.agents.orchestrator import run_chat_collect
from app.models.client_intake import CaseMatch, CaseMatchExecution, CaseStudy, ResearchFinding, ResearchRun
from app.models.engagement import Engagement
from app.models.file import File
from app.models.plan import Plan, PlanBudgetLine, PlanSource, PlanVersion
from app.models.rate_card import RateCardItem
from app.models.user import User
from app.services import audit as audit_svc
from app.services import engagement as engagement_svc
from app.services import rate_card as rate_card_svc
from app.services import workspace as workspace_svc
from app.services.chat_policy import prepare_chat

_logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict:
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        raise ValueError("no JSON object found in model output")
    return json.loads(match.group(0))


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


async def _available_rate_card(session: AsyncSession, workspace_id: uuid.UUID) -> list[RateCardItem]:
    result = await session.execute(
        select(RateCardItem).where(
            RateCardItem.active.is_(True),
            or_(RateCardItem.workspace_id == workspace_id, RateCardItem.workspace_id.is_(None)),
        )
    )
    return list(result.scalars().all())


async def _latest_done_research(session: AsyncSession, engagement_id: uuid.UUID) -> ResearchRun | None:
    step = await engagement_svc.get_step(session, engagement_id, "market")
    result = await session.execute(
        select(ResearchRun)
        .where(ResearchRun.engagement_step_id == step.id, ResearchRun.status == "done")
        .order_by(ResearchRun.created_at.desc())
    )
    return result.scalars().first()


async def _research_finding_texts(session: AsyncSession, research_run_id: uuid.UUID) -> list[str]:
    result = await session.execute(
        select(ResearchFinding.text)
        .where(ResearchFinding.research_run_id == research_run_id)
        .order_by(ResearchFinding.ordinal)
    )
    return list(result.scalars().all())


class _CaseRow:
    __slots__ = ("file_id", "filename", "score", "rationale")

    def __init__(self, file_id, filename, score, rationale):
        self.file_id = file_id
        self.filename = filename
        self.score = score
        self.rationale = rationale


async def _latest_case_matches(session: AsyncSession, engagement_id: uuid.UUID, limit: int = 3) -> list[_CaseRow]:
    step = await engagement_svc.get_step(session, engagement_id, "cases")
    run_id = (
        await session.execute(
            select(CaseMatchExecution.id)
            .where(CaseMatchExecution.engagement_step_id == step.id, CaseMatchExecution.status == "done")
            .order_by(CaseMatchExecution.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if run_id is None:
        return []
    rows = (
        await session.execute(
            select(CaseMatch.score, CaseMatch.rationale, CaseStudy.file_id, File.filename)
            .join(CaseStudy, CaseStudy.id == CaseMatch.case_study_id)
            .join(File, File.id == CaseStudy.file_id)
            .where(CaseMatch.case_match_run_id == run_id)
            .order_by(CaseMatch.rank)
            .limit(limit)
        )
    ).all()
    return [_CaseRow(file_id=r.file_id, filename=r.filename, score=r.score, rationale=r.rationale) for r in rows]


def _build_drafting_prompt(fields: dict, research_lines: list[str], cases: list[_CaseRow], rate_items: list[RateCardItem]) -> str:
    context_lines = [f"{k}: {v}" for k, v in fields.items()]
    case_lines = [f"{c.filename} (match {round(c.score, 2)}): {c.rationale}" for c in cases]
    rate_lines = [f"{r.code} — {r.label} ({r.unit or 'unit'}, {r.currency} {r.unit_price})" for r in rate_items]

    return (
        "Draft a 4-part brand strategy plan for this client, in the exact JSON shape below. "
        "Respond with ONLY the JSON object, no prose outside it. "
        "Write every string VALUE in Thai (ภาษาไทย), in natural business Thai for a "
        "client-facing proposal. Keep the JSON keys in English exactly as shown, and keep "
        "every rate-card code exactly as given — do not translate or alter codes. Brand, "
        "company and case-study names stay in their original language.\n\n"
        "Client context:\n" + "\n".join(context_lines) + "\n\n"
        "Market research findings:\n" + ("\n".join(research_lines) or "(none)") + "\n\n"
        "Closest matching Brandbiz case studies:\n" + ("\n".join(case_lines) or "(none)") + "\n\n"
        "Available rate-card items — use ONLY these codes in budget_items; never invent a "
        "code, never state a price yourself, the price is computed separately:\n"
        + "\n".join(rate_lines) + "\n\n"
        "JSON shape:\n"
        "{\n"
        '  "title": "short plan title",\n'
        '  "core_idea": "1-2 sentences",\n'
        '  "analogous_case": "1-2 sentences referencing the closest case study",\n'
        '  "adapted_plan": [{"period": "สัปดาห์ 1-2", "text": "..."}, ...],\n'
        '  "budget_items": [{"code": "<a code from the list above>", "qty": 1}, ...]\n'
        "}"
    )


async def draft_plan(
    session: AsyncSession,
    user: User,
    workspace_id: uuid.UUID,
    engagement: Engagement,
    fields: dict,
) -> dict:
    """Returns {"title","core_idea","analogous_case","adapted_plan","budget","provenance","conversation_id"}.

    workspace_id is passed explicitly rather than read off user.workspace_id
    — a staff member previewing the funnel (app/deps.py::ClientContext)
    has workspace_id=None on their own row but drafts against the demo
    workspace, so the two can legitimately differ."""
    agent = await workspace_svc.get_workspace_agent(session, workspace_id)
    if agent is None:
        _logger.warning("draft_plan: workspace %s has no assigned agent", workspace_id)
        raise HTTPException(status_code=503, detail="This workspace has no assigned agent yet")

    rate_items = await _available_rate_card(session, workspace_id)
    if not rate_items:
        _logger.warning("draft_plan: workspace %s has no active rate card items", workspace_id)
        raise HTTPException(status_code=503, detail="No rate card is configured for this workspace yet")

    research = await _latest_done_research(session, engagement.id)
    research_lines = await _research_finding_texts(session, research.id) if research else []
    case_rows = await _latest_case_matches(session, engagement.id, limit=3)

    prompt = _build_drafting_prompt(fields, research_lines, case_rows, rate_items)

    prepared = await prepare_chat(
        session=session,
        user=user,
        conversation_id=engagement.conversation_id,
        user_content=prompt,
        requested_model="auto",
        agent_id=agent.id,
        workspace_id=workspace_id,
    )
    result = await run_chat_collect(
        session=session,
        user_id=user.id,
        user=user,
        resolved_conversation_id=prepared.resolved_conversation_id,
        user_content=prompt,
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
    )

    try:
        parsed = _extract_json(result["output"])
    except (ValueError, json.JSONDecodeError) as exc:
        # Never log the model output or the prompt here — both embed decrypted
        # client profile fields and research findings (PLAN.md §7.1). Log the
        # shape only.
        output = result.get("output") or ""
        _logger.warning(
            "draft_plan: model output not parseable as JSON (workspace=%s, output_len=%d, has_brace=%s)",
            workspace_id,
            len(output),
            "{" in output,
        )
        raise HTTPException(
            status_code=502, detail="น้องภูมิ could not draft a plan just now — please try again."
        ) from exc

    budget_items = parsed.get("budget_items") or []
    budget = await rate_card_svc.price(session, workspace_id, budget_items)

    # Research citations, reassembled into the old {"index","source"} shape
    # (research_citations is now a real table — see app/models/client_intake.py).
    research_sources: list[dict] = []
    if research is not None:
        from app.models.client_intake import ResearchCitation

        rows = (
            await session.execute(
                select(ResearchCitation).where(ResearchCitation.research_run_id == research.id).order_by(ResearchCitation.ordinal)
            )
        ).scalars().all()
        research_sources = [{"index": i + 1, "source": c.url} for i, c in enumerate(rows)]

    provenance = {
        "rate_card_codes": [li["code"] for li in budget["lines"]],
        "case_files": [
            {"file_id": str(c.file_id), "filename": c.filename, "score": c.score} for c in case_rows
        ],
        "research_run_id": str(research.id) if research else None,
        "research_sources": research_sources,
    }

    return {
        "title": (parsed.get("title") or "Brand strategy plan")[:500],
        "core_idea": parsed.get("core_idea") or "",
        "analogous_case": parsed.get("analogous_case") or "",
        "adapted_plan": parsed.get("adapted_plan") or [],
        "budget": budget,
        "provenance": provenance,
        "conversation_id": str(prepared.resolved_conversation_id),
    }


async def _persist_version(
    session: AsyncSession,
    plan: Plan,
    user: User,
    workspace_id: uuid.UUID,
    version_no: int,
    draft: dict,
) -> PlanVersion:
    """Write one PlanVersion plus its exploded PlanBudgetLine/PlanSource
    rows, from the same dict shapes draft_plan()/the frontend already
    produce — see this module's docstring for why the dict contract is
    kept even though storage is now normalized."""
    body = {
        "core_idea": draft["core_idea"],
        "analogous_case": draft["analogous_case"],
        "adapted_plan": draft["adapted_plan"],
    }
    ct, nonce, tag, kv = crypto.encrypt(json.dumps(body))
    budget = draft.get("budget") or {}
    provenance = draft.get("provenance") or {}

    version = PlanVersion(
        plan_id=plan.id,
        version_no=version_no,
        title=draft["title"],
        body_ciphertext=ct, body_nonce=nonce, body_tag=tag, key_version=kv,
        subtotal_amount=_dec(budget.get("subtotal")),
        contingency_amount=_dec(budget.get("contingency")),
        total_amount=_dec(budget.get("total")),
        currency=budget.get("currency"),
        created_by=user.id,
    )
    session.add(version)
    await session.flush()

    ordinal = 0
    for line in budget.get("lines") or []:
        code = str(line.get("code", "")).strip()
        rc_row = (
            await session.execute(
                select(RateCardItem.id)
                .where(
                    RateCardItem.code == code,
                    or_(RateCardItem.workspace_id == workspace_id, RateCardItem.workspace_id.is_(None)),
                )
                .order_by(RateCardItem.workspace_id.is_(None))
                .limit(1)
            )
        ).scalar_one_or_none()
        session.add(PlanBudgetLine(
            plan_version_id=version.id, ordinal=ordinal, rate_card_item_id=rc_row, code=code,
            label=line.get("label"), section=line.get("section"), unit=line.get("unit"),
            qty=_dec(line.get("qty")) or Decimal("1"), unit_price=_dec(line.get("unit_price")),
            amount=_dec(line.get("amount")), currency=budget.get("currency"), needs_expert=False,
        ))
        ordinal += 1
    for item in budget.get("needs_expert") or []:
        session.add(PlanBudgetLine(
            plan_version_id=version.id, ordinal=ordinal, code=str(item.get("code", "")).strip(),
            qty=_dec(item.get("qty")) or Decimal("1"), needs_expert=True,
        ))
        ordinal += 1

    ordinal = 0
    for code in provenance.get("rate_card_codes") or []:
        session.add(PlanSource(plan_version_id=version.id, ordinal=ordinal, kind="rate_card", label_snapshot=code))
        ordinal += 1
    for case in provenance.get("case_files") or []:
        session.add(PlanSource(
            plan_version_id=version.id, ordinal=ordinal, kind="case_study",
            ref_id=uuid.UUID(case["file_id"]) if case.get("file_id") else None,
            label_snapshot=case.get("filename"), score_snapshot=case.get("score"),
        ))
        ordinal += 1
    research_run_id = provenance.get("research_run_id")
    ref_id = uuid.UUID(research_run_id) if research_run_id else None
    for src in provenance.get("research_sources") or []:
        session.add(PlanSource(
            plan_version_id=version.id, ordinal=ordinal, kind="research_citation", ref_id=ref_id,
            label_snapshot=src.get("source") if isinstance(src, dict) else str(src),
        ))
        ordinal += 1

    return version


async def save_plan(
    session: AsyncSession, user: User, workspace_id: uuid.UUID, engagement: Engagement, draft: dict
) -> Plan:
    plan = Plan(
        workspace_id=workspace_id,
        user_id=user.id,
        engagement_id=engagement.id,
        conversation_id=engagement.conversation_id,
        status="draft",
    )
    session.add(plan)
    await session.flush()

    version = await _persist_version(session, plan, user, workspace_id, 1, draft)
    plan.current_version_id = version.id
    engagement.active_plan_id = plan.id
    await session.commit()
    await session.refresh(plan)

    await audit_svc.log(
        action="plan_created",
        user_id=user.id,
        resource_type="plan",
        resource_id=plan.id,
        details={"workspace_id": str(workspace_id), "title": version.title},
    )
    return plan


async def revise_plan(
    session: AsyncSession, user: User, workspace_id: uuid.UUID, plan_id: uuid.UUID, draft: dict
) -> Plan:
    """Update an existing Plan with a re-drafted body (a client edited
    their intake profile and resubmitted — see
    app/routers/client.py::PUT /client/plans/{plan_id}). Appends a new
    PlanVersion and repoints Plan.current_version_id; never touches
    plan.status — "draft · awaiting expert review" is a liability
    control, not decoration, and a revision must stay a draft exactly like
    the original, never silently promoted to expert_review/final."""
    plan = await get_plan(session, user, workspace_id, plan_id)

    latest_version_no = (
        await session.execute(
            select(PlanVersion.version_no).where(PlanVersion.plan_id == plan.id).order_by(PlanVersion.version_no.desc()).limit(1)
        )
    ).scalar_one()
    next_version_no = latest_version_no + 1

    version = await _persist_version(session, plan, user, workspace_id, next_version_no, draft)
    plan.current_version_id = version.id
    await session.commit()
    await session.refresh(plan)

    await audit_svc.log(
        action="plan_updated",
        user_id=user.id,
        resource_type="plan",
        resource_id=plan.id,
        details={"workspace_id": str(workspace_id), "version": next_version_no},
    )
    return plan


def decrypt_body(version: PlanVersion) -> dict:
    raw = crypto.decrypt(version.body_ciphertext, version.body_nonce, version.body_tag, version.key_version)
    return json.loads(raw)


async def budget_out(session: AsyncSession, version: PlanVersion) -> dict | None:
    """Reassembles the {"lines": [...], "needs_expert": [...], "subtotal",
    "contingency", "total", "currency"} shape the frontend/API contract
    already used, from the normalized PlanBudgetLine rows."""
    rows = (
        await session.execute(
            select(PlanBudgetLine).where(PlanBudgetLine.plan_version_id == version.id).order_by(PlanBudgetLine.ordinal)
        )
    ).scalars().all()
    if not rows and version.subtotal_amount is None:
        return None
    lines = [
        {
            "code": r.code, "label": r.label, "section": r.section, "unit": r.unit,
            "qty": str(r.qty), "unit_price": str(r.unit_price) if r.unit_price is not None else None,
            "amount": str(r.amount) if r.amount is not None else None,
        }
        for r in rows if not r.needs_expert
    ]
    needs_expert = [{"code": r.code, "qty": str(r.qty)} for r in rows if r.needs_expert]
    return {
        "lines": lines,
        "needs_expert": needs_expert,
        "subtotal": str(version.subtotal_amount) if version.subtotal_amount is not None else "0.00",
        "contingency": str(version.contingency_amount) if version.contingency_amount is not None else "0.00",
        "total": str(version.total_amount) if version.total_amount is not None else "0.00",
        "currency": version.currency or "THB",
    }


async def provenance_out(session: AsyncSession, version: PlanVersion) -> dict | None:
    """Reassembles the old {"rate_card_codes", "case_files",
    "research_run_id", "research_sources"} shape from PlanSource rows.
    Returns None for a version with no source rows at all (pre-0049 plan
    versions never had provenance recorded — see 0056's migration
    docstring) so the frontend's existing "wasn't recorded for this
    version" copy keeps working unchanged."""
    rows = (
        await session.execute(
            select(PlanSource).where(PlanSource.plan_version_id == version.id).order_by(PlanSource.ordinal)
        )
    ).scalars().all()
    if not rows:
        return None
    rate_card_codes = [r.label_snapshot for r in rows if r.kind == "rate_card"]
    case_files = [
        {"file_id": str(r.ref_id) if r.ref_id else None, "filename": r.label_snapshot, "score": r.score_snapshot}
        for r in rows if r.kind == "case_study"
    ]
    citation_rows = [r for r in rows if r.kind == "research_citation"]
    research_run_id = str(citation_rows[0].ref_id) if citation_rows and citation_rows[0].ref_id else None
    research_sources = [{"source": r.label_snapshot} for r in citation_rows]
    return {
        "rate_card_codes": rate_card_codes,
        "case_files": case_files,
        "research_run_id": research_run_id,
        "research_sources": research_sources,
    }


async def list_plans(session: AsyncSession, user: User, workspace_id: uuid.UUID) -> list[Plan]:
    result = await session.execute(
        select(Plan)
        .where(Plan.workspace_id == workspace_id, Plan.user_id == user.id)
        .order_by(Plan.created_at.desc())
    )
    return list(result.scalars().all())


async def get_plan(session: AsyncSession, user: User, workspace_id: uuid.UUID, plan_id: uuid.UUID) -> Plan:
    plan = (await session.execute(
        select(Plan).where(
            Plan.id == plan_id, Plan.workspace_id == workspace_id, Plan.user_id == user.id
        )
    )).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


async def get_current_version(session: AsyncSession, plan: Plan) -> PlanVersion:
    if plan.current_version_id is not None:
        version = (
            await session.execute(select(PlanVersion).where(PlanVersion.id == plan.current_version_id))
        ).scalar_one_or_none()
        if version is not None:
            return version
    # Defensive fallback — current_version_id should always be set by
    # save_plan/revise_plan, but never trust a NULLable FK blindly.
    version = (
        await session.execute(
            select(PlanVersion).where(PlanVersion.plan_id == plan.id).order_by(PlanVersion.version_no.desc()).limit(1)
        )
    ).scalars().first()
    if version is None:
        raise HTTPException(status_code=500, detail="Plan has no versions")
    return version


async def list_versions(session: AsyncSession, plan_id: uuid.UUID) -> list[PlanVersion]:
    """Backs the plan document's Versions panel."""
    result = await session.execute(
        select(PlanVersion).where(PlanVersion.plan_id == plan_id).order_by(PlanVersion.version_no.asc())
    )
    return list(result.scalars().all())


async def get_version(
    session: AsyncSession, user: User, workspace_id: uuid.UUID, plan_id: uuid.UUID, version_no: int
) -> PlanVersion:
    """Backs GET /client/plans/{plan_id}/versions/{version} — the version
    rail's "read an old version" affordance (PLAN.md Task 5.12).
    get_plan() is the ownership/404 check (list_versions() deliberately has
    none, see its docstring). UNIQUE(plan_id, version_no) now makes this a
    genuine lookup, not a "pick the newest match" workaround."""
    await get_plan(session, user, workspace_id, plan_id)
    v = (await session.execute(
        select(PlanVersion).where(PlanVersion.plan_id == plan_id, PlanVersion.version_no == version_no)
    )).scalar_one_or_none()
    if v is None:
        raise HTTPException(status_code=404, detail="Plan version not found")
    return v


def decrypt_version_body(v: PlanVersion) -> dict:
    raw = crypto.decrypt(v.body_ciphertext, v.body_nonce, v.body_tag, v.key_version)
    return json.loads(raw)


async def create_share_token(
    session: AsyncSession, user: User, workspace_id: uuid.UUID, plan_id: uuid.UUID
) -> str:
    """Phase 6 (Export/share) — defined here since it's tightly coupled to
    Plan, wired into a router once the share-link page exists."""
    plan = await get_plan(session, user, workspace_id, plan_id)
    raw = "plan_" + secrets.token_urlsafe(24)
    plan.share_token_hash = hashlib.sha256(raw.encode()).hexdigest()
    await session.commit()
    await audit_svc.log(
        action="plan_shared", user_id=user.id, resource_type="plan", resource_id=plan.id,
    )
    return raw


async def get_plan_by_share_token(session: AsyncSession, raw_token: str) -> Plan:
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    plan = (await session.execute(
        select(Plan).where(Plan.share_token_hash == token_hash)
    )).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="This plan link is not valid")
    return plan
