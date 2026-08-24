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
from app.llm.base import LLMProviderError
from app.models.client_intake import CaseMatch, CaseMatchExecution, CaseStudy, ResearchFinding, ResearchRun
from app.models.engagement import Engagement
from app.models.file import File
from app.models.plan import Plan, PlanBudgetLine, PlanSource, PlanVersion
from app.models.rate_card import RateCardItem
from app.models.user import User
from app.services import audit as audit_svc
from app.services import engagement as engagement_svc
from app.services import rate_card as rate_card_svc
from app.services import solution_trigger as trigger_svc
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


# Drafting is a machine call, not a chat turn, and the workspace agent's own
# instructions are written for the chat ("พูดจาสุภาพ เป็นกันเอง ถามทีละคำถาม" — be
# friendly, ask one question at a time). Handed a client profile with a thin or
# messy free-text answer, an agent following those instructions does exactly
# what it was told: it greets the client and asks follow-up questions instead of
# emitting JSON, and the endpoint 502s on unparseable output. This block is
# appended AFTER the agent's instructions so the task framing is the last thing
# the model reads; the agent's own voice still shapes the Thai copy.
_DRAFTING_OVERRIDE = (
    "[TASK MODE — this request is not a chat turn]\n"
    "You are being called by software, and your reply is parsed as JSON by a "
    "program, not read by a person. Do not greet anyone, do not ask any "
    "question, and do not explain yourself. Output the JSON object and nothing "
    "else. If a client-profile field is missing, vague or looks like nonsense, "
    "ignore that field and draft from the rest — never stop to ask about it."
)


# The drafting prompt's opening sentence, split out because it is the only
# handle scripts/backfill_plan_draft_messages.py has on rows written before
# draft_plan() started stamping engagement_step_id — message content is
# encrypted, so a legacy draft turn can only be recognised by decrypting it
# and matching this literal. Keep the two in sync.
DRAFTING_PROMPT_OPENING = (
    "Draft a 4-part brand strategy plan for this client, in the exact JSON shape below."
)


def _build_drafting_prompt(fields: dict, research_lines: list[str], cases: list[_CaseRow], rate_items: list[RateCardItem]) -> str:
    context_lines = [f"{k}: {v}" for k, v in fields.items()]
    # Solution triggers are decided in code, not by the model
    # (app/services/solution_trigger.py). They are appended AFTER the case
    # studies and rate card rather than mixed into "Client context" above,
    # because they are conclusions about what the plan must contain, not more
    # facts to weigh — a client-context line reading like the others would
    # invite the model to trade it off against the rest.
    directives = [t.directive for t in trigger_svc.evaluate(fields)]
    case_lines = [f"{c.filename} (match {round(c.score, 2)}): {c.rationale}" for c in cases]
    rate_lines = [f"{r.code} — {r.label} ({r.unit or 'unit'}, {r.currency} {r.unit_price})" for r in rate_items]

    return (
        DRAFTING_PROMPT_OPENING + " "
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
        + (
            "Requirements this plan MUST satisfy, derived from the client's own answers "
            "by rule. Address each explicitly in adapted_plan, and reflect it in "
            "budget_items where it implies work:\n" + "\n".join(directives) + "\n\n"
            if directives else ""
        )
        + "JSON shape:\n"
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

    # Both persisted rows get stamped with the 'plan' step so the transcript
    # replay in GET /client/bootstrap can skip them: the client never typed
    # this ~8k-char prompt and never read the raw JSON that comes back — they
    # saw a plan card. Replaying them verbatim would put the drafting
    # machinery into the chat thread. See app/models/message.py::
    # Message.engagement_step_id.
    plan_step = await engagement_svc.get_step(session, engagement.id, "plan")

    prepared = await prepare_chat(
        session=session,
        user=user,
        conversation_id=engagement.conversation_id,
        user_content=prompt,
        requested_model="auto",
        agent_id=agent.id,
        workspace_id=workspace_id,
    )
    # Deliberately NOT prepared.history. _build_drafting_prompt() already
    # carries everything the draft needs (intake fields, research findings,
    # case matches, rate card), so the transcript adds nothing — and it is the
    # one input that grows without bound. Every draft persists its own ~8k-char
    # prompt plus the raw JSON reply into this conversation (call_llm), so after
    # a few drafts the last-20-messages window alone filled the local model's
    # context window and the model had no budget left to answer: it returned an
    # empty string, which surfaced as "could not draft a plan just now".
    # prepare_chat() still sees the full history — tier classification and the
    # PolicyEngine decision must stay conservative (§7.6) — only the generation
    # call is trimmed.
    try:
        result = await run_chat_collect(
            session=session,
            user_id=user.id,
            user=user,
            resolved_conversation_id=prepared.resolved_conversation_id,
            user_content=prompt,
            model_code=prepared.model_code,
            history=[],
            downgrade_to_local=prepared.downgrade_to_local,
            reasons=prepared.reasons,
            image_model_code=prepared.image_model_code,
            n8n_route=prepared.n8n_route,
            rag_context=prepared.rag_context,
            citations=prepared.citations,
            system_prompt="\n\n".join(
                filter(None, [prepared.system_prompt, _DRAFTING_OVERRIDE])
            ),
            tuning=prepared.tuning,
            engagement_step_id=plan_step.id,
        )
    except LLMProviderError as exc:
        # Provider-side failure (unreachable server, timeout, prompt larger than
        # the context window). The message is operator-facing and safe to log —
        # adapters never echo the prompt back into it (§7.1).
        _logger.warning("draft_plan: provider failed (workspace=%s): %s", workspace_id, exc)
        raise HTTPException(
            status_code=502, detail="น้องภูมิ could not draft a plan just now — please try again."
        ) from exc

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


# ---------------------------------------------------------------------------
# Revision by instruction (chat-driven plan edits)
# ---------------------------------------------------------------------------
#
# A client asking "ตัดเฟส 4 ออก แล้วเพิ่มงบ content" in the chat box cannot be
# served by letting the model rewrite the plan card as prose: the price of every
# budget line comes from rate_card.price() and never from the model (see this
# module's docstring). So an edit is a RE-DRAFT under an instruction — the model
# gets the current plan in the exact JSON shape it must return, plus the rate
# card, and the server re-prices whatever codes come back.
#
# The revision is committed straight to the next PlanVersion rather than handed
# back as an unsaved draft. The client already confirmed once (the chip that
# routed them here), and a second Save step on top of that confirmation buys
# nothing — version history is the undo.

_REVISION_PROMPT_OPENING = (
    "Revise the brand strategy plan below according to the client's instruction, "
    "in the exact JSON shape given."
)


def _budget_items_of(budget: dict | None) -> list[dict]:
    """The {code, qty} pairs that produced `budget` — the only budget vocabulary
    the model is allowed to speak, on the way in as on the way out."""
    if not budget:
        return []
    items = [
        {"code": li.get("code"), "qty": li.get("qty")}
        for li in (budget.get("lines") or [])
    ]
    items += [
        {"code": li.get("code"), "qty": li.get("qty")}
        for li in (budget.get("needs_expert") or [])
    ]
    return [i for i in items if i["code"]]


def _build_revision_prompt(
    *,
    title: str,
    body: dict,
    budget: dict | None,
    rate_items: list[RateCardItem],
    instruction: str,
) -> str:
    """The current plan, the rate card, and what the client asked to change.

    The current plan is rendered in the SAME JSON shape the reply must use, so
    "change only what was asked" is a copy operation for the model rather than a
    reconstruction — the cheapest defence there is against a revision quietly
    rewording sections nobody touched.
    """
    current = {
        "title": title,
        "core_idea": body.get("core_idea") or "",
        "analogous_case": body.get("analogous_case") or "",
        "adapted_plan": body.get("adapted_plan") or [],
        "budget_items": _budget_items_of(budget),
    }
    rate_lines = [
        f"{r.code} — {r.label} ({r.unit or 'unit'}, {r.currency} {r.unit_price})"
        for r in rate_items
    ]

    return (
        _REVISION_PROMPT_OPENING + " "
        "Respond with ONLY the JSON object, no prose outside it. "
        "Change ONLY what the instruction asks for. Every field the instruction "
        "does not mention must come back byte-identical to the current plan — do "
        "not reword, re-order, re-translate or improve it. "
        "Write every string VALUE in Thai (ภาษาไทย), in natural business Thai for a "
        "client-facing proposal. Keep the JSON keys in English exactly as shown, and "
        "keep every rate-card code exactly as given — do not translate or alter "
        "codes.\n\n"
        "Current plan:\n" + json.dumps(current, ensure_ascii=False, indent=2) + "\n\n"
        "The client's instruction:\n" + instruction.strip() + "\n\n"
        "Available rate-card items — use ONLY these codes in budget_items; never "
        "invent a code, never state a price yourself, the price is computed "
        "separately:\n" + "\n".join(rate_lines) + "\n\n"
        "Reply with the FULL revised plan in this JSON shape (not a patch, not a "
        "diff — every field, including the ones you did not change):\n"
        "{\n"
        '  "title": "short plan title",\n'
        '  "core_idea": "1-2 sentences",\n'
        '  "analogous_case": "1-2 sentences referencing the closest case study",\n'
        '  "adapted_plan": [{"period": "สัปดาห์ 1-2", "text": "..."}, ...],\n'
        '  "budget_items": [{"code": "<a code from the list above>", "qty": 1}, ...]\n'
        "}"
    )


def _budget_index(budget: dict | None) -> dict[str, dict]:
    """code -> {qty, label, amount}, across both priced and needs_expert lines."""
    index: dict[str, dict] = {}
    for li in (budget or {}).get("lines") or []:
        code = str(li.get("code") or "")
        if code:
            index[code] = {"qty": li.get("qty"), "label": li.get("label"), "amount": li.get("amount")}
    for li in (budget or {}).get("needs_expert") or []:
        code = str(li.get("code") or "")
        if code:
            index[code] = {"qty": li.get("qty"), "label": None, "amount": None}
    return index


def diff_versions(
    *,
    base_title: str,
    base_body: dict,
    base_budget: dict | None,
    new_title: str,
    new_body: dict,
    new_budget: dict | None,
) -> dict:
    """What a revision actually changed, computed server-side.

    The failure mode of re-drafting under an instruction is DRIFT: asked to cut
    phase 4, the model also rewords core_idea. Prose can hide that; a diff
    cannot, which is why the card shows this rather than just the new plan.

    Money is separated from narrative on purpose — a reworded sentence is
    cosmetic, a changed budget line is not.
    """
    fields: list[str] = []
    if (base_title or "") != (new_title or ""):
        fields.append("title")
    for key in ("core_idea", "analogous_case"):
        if (base_body.get(key) or "") != (new_body.get(key) or ""):
            fields.append(key)
    if (base_body.get("adapted_plan") or []) != (new_body.get("adapted_plan") or []):
        fields.append("adapted_plan")

    before, after = _budget_index(base_budget), _budget_index(new_budget)
    added = [
        {"code": c, "label": after[c]["label"], "amount": after[c]["amount"]}
        for c in after
        if c not in before
    ]
    removed = [
        {"code": c, "label": before[c]["label"], "amount": before[c]["amount"]}
        for c in before
        if c not in after
    ]
    qty_changed = [
        {"code": c, "label": after[c]["label"], "from": before[c]["qty"], "to": after[c]["qty"]}
        for c in after
        if c in before and str(before[c]["qty"]) != str(after[c]["qty"])
    ]

    return {
        "fields": fields,
        "budget": {
            "added": added,
            "removed": removed,
            "qty_changed": qty_changed,
            "total_before": (base_budget or {}).get("total"),
            "total_after": (new_budget or {}).get("total"),
        },
    }


async def revise_from_instruction(
    session: AsyncSession,
    user: User,
    workspace_id: uuid.UUID,
    engagement: Engagement,
    plan: Plan,
    instruction: str,
) -> dict:
    """Re-draft `plan` under `instruction` and COMMIT it as the next version.

    Returns the same dict shape draft_plan() does, plus "id", "version",
    "revision_note" and "diff". `plan` must already be ownership-checked
    (get_plan / get_active_plan).
    """
    agent = await workspace_svc.get_workspace_agent(session, workspace_id)
    if agent is None:
        _logger.warning("revise_from_instruction: workspace %s has no assigned agent", workspace_id)
        raise HTTPException(status_code=503, detail="This workspace has no assigned agent yet")

    rate_items = await _available_rate_card(session, workspace_id)
    if not rate_items:
        _logger.warning(
            "revise_from_instruction: workspace %s has no active rate card items", workspace_id
        )
        raise HTTPException(status_code=503, detail="No rate card is configured for this workspace yet")

    base_version = await get_current_version(session, plan)
    base_body = decrypt_body(base_version)
    base_budget = await budget_out(session, base_version)
    base_provenance = await provenance_out(session, base_version) or {}

    prompt = _build_revision_prompt(
        title=base_version.title,
        body=base_body,
        budget=base_budget,
        rate_items=rate_items,
        instruction=instruction,
    )

    # Same stamping rule as draft_plan(): the client typed a one-line
    # instruction, not this prompt, and never read the JSON that comes back.
    # Leaving either unstamped puts them in the free-form chat window, where the
    # model treats the JSON as an example to imitate — see
    # services/chat_policy.py::load_history_messages.
    plan_step = await engagement_svc.get_step(session, engagement.id, "plan")

    prepared = await prepare_chat(
        session=session,
        user=user,
        conversation_id=engagement.conversation_id,
        user_content=prompt,
        requested_model="auto",
        agent_id=agent.id,
        workspace_id=workspace_id,
    )
    try:
        result = await run_chat_collect(
            session=session,
            user_id=user.id,
            user=user,
            resolved_conversation_id=prepared.resolved_conversation_id,
            user_content=prompt,
            model_code=prepared.model_code,
            # history=[] for the same reason draft_plan() does it: the prompt
            # already carries the whole plan, and the transcript is the one
            # input that grows without bound.
            history=[],
            downgrade_to_local=prepared.downgrade_to_local,
            reasons=prepared.reasons,
            image_model_code=prepared.image_model_code,
            n8n_route=prepared.n8n_route,
            rag_context=prepared.rag_context,
            citations=prepared.citations,
            system_prompt="\n\n".join(
                filter(None, [prepared.system_prompt, _DRAFTING_OVERRIDE])
            ),
            tuning=prepared.tuning,
            engagement_step_id=plan_step.id,
        )
    except LLMProviderError as exc:
        _logger.warning(
            "revise_from_instruction: provider failed (workspace=%s): %s", workspace_id, exc
        )
        raise HTTPException(
            status_code=502,
            detail="น้องภูมิ could not revise the plan just now — please try again.",
        ) from exc

    try:
        parsed = _extract_json(result["output"])
    except (ValueError, json.JSONDecodeError) as exc:
        # Never log the model output or the prompt — both embed decrypted client
        # profile fields and the plan body (§7.1). Shape only.
        output = result.get("output") or ""
        _logger.warning(
            "revise_from_instruction: model output not parseable as JSON "
            "(workspace=%s, output_len=%d, has_brace=%s)",
            workspace_id,
            len(output),
            "{" in output,
        )
        raise HTTPException(
            status_code=502,
            detail="น้องภูมิ could not revise the plan just now — please try again.",
        ) from exc

    budget = await rate_card_svc.price(session, workspace_id, parsed.get("budget_items") or [])

    # Provenance is carried forward, not re-resolved: a revision draws on the
    # same research run and case studies the original drew on, and re-running
    # the lookups would silently re-point the plan at whatever happens to be
    # latest now. Only the rate-card codes are recomputed, since those ARE what
    # changed.
    provenance = {
        **base_provenance,
        "rate_card_codes": [li["code"] for li in budget["lines"]],
    }

    draft = {
        "title": (parsed.get("title") or base_version.title)[:500],
        "core_idea": parsed.get("core_idea") or "",
        "analogous_case": parsed.get("analogous_case") or "",
        "adapted_plan": parsed.get("adapted_plan") or [],
        "budget": budget,
        "provenance": provenance,
        # Stored inside the encrypted version body (§7.1) so the card and the
        # version history can show what the client asked for on each bump.
        "revision_note": instruction.strip(),
    }

    diff = diff_versions(
        base_title=base_version.title,
        base_body=base_body,
        base_budget=base_budget,
        new_title=draft["title"],
        new_body=draft,
        new_budget=budget,
    )

    revised = await revise_plan(session, user, workspace_id, plan.id, draft)
    new_version = await get_current_version(session, revised)

    return {
        "id": str(revised.id),
        "title": new_version.title,
        "core_idea": draft["core_idea"],
        "analogous_case": draft["analogous_case"],
        "adapted_plan": draft["adapted_plan"],
        "budget": await budget_out(session, new_version) or budget,
        "provenance": await provenance_out(session, new_version) or provenance,
        "version": new_version.version_no,
        "revision_note": draft["revision_note"],
        "diff": diff,
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
    # Only revisions carry one — what the client asked for, in their own words,
    # so the version history can say WHY v3 differs from v2. It lives inside the
    # encrypted body because it is verbatim client message content (§7.1), which
    # is also why it must never reach an audit_log details blob.
    if draft.get("revision_note"):
        body["revision_note"] = draft["revision_note"]
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


# ---------------------------------------------------------------------------
# Plan -> chat context
# ---------------------------------------------------------------------------
#
# A saved plan is an artifact OUTSIDE the message thread (see app/models/
# plan.py) — the client never "received" it as an assistant turn, so a
# follow-up like "ทำไมเฟส 2 ถึงราคาเท่านี้" hit a model that had no idea what
# plan the client was looking at. The only trace in the conversation is
# draft_plan()'s own prompt + raw JSON reply, which is (a) the DRAFT, not
# whatever was saved/revised afterwards, and (b) the first thing to fall out
# of the history window. So the CURRENT version of the plan is rebuilt into a
# system block on every client chat turn instead — see
# app/routers/client.py::client_chat.


def build_plan_context(
    *,
    title: str,
    version_no: int,
    body: dict,
    budget: dict | None,
    provenance: dict | None,
) -> str:
    """Render one saved plan version as a system-context block.

    Pure (takes already-decrypted/already-reassembled dicts — the same
    shapes _plan_out() hands the frontend), so it is unit-testable without a
    DB; the loading half is plan_context_for_plan() below.

    The money rules in the header are not decoration: prices come from
    rate_card.price(), never from the model (see this module's docstring), so
    a chat turn must quote the stored figures rather than re-derive them.
    """
    lines: list[str] = [
        "[CURRENT PLAN — the client is looking at this plan in their workspace]",
        f'This is the plan saved for this client: "{title}" (version {version_no}).',
        "Answer questions about it using the facts in this block. Quote every "
        "number exactly as written here — never invent, re-price or re-scope a "
        "budget line. If the client asks to change the scope or the price, say a "
        "Brandbiz expert will confirm it. Reply in Thai unless the client writes "
        "in another language.",
        "",
    ]

    core_idea = (body.get("core_idea") or "").strip()
    if core_idea:
        lines.append(f"Core idea: {core_idea}")
    analogous = (body.get("analogous_case") or "").strip()
    if analogous:
        lines.append(f"Analogous case: {analogous}")

    phases = body.get("adapted_plan") or []
    if phases:
        lines.append("Plan:")
        for phase in phases:
            if not isinstance(phase, dict):
                continue
            period = (phase.get("period") or "").strip()
            text = (phase.get("text") or "").strip()
            lines.append(f"- {period}: {text}" if period else f"- {text}")

    if budget:
        currency = budget.get("currency") or "THB"
        lines.append(f"Budget ({currency}):")
        for li in budget.get("lines") or []:
            label = li.get("label") or li.get("code")
            unit = f", {li['unit']}" if li.get("unit") else ""
            section = f" [{li['section']}]" if li.get("section") else ""
            amount = li.get("amount")
            lines.append(
                f"- {li.get('code')} — {label}{section} (qty {li.get('qty')}{unit}"
                f" @ {li.get('unit_price')}) = {amount}"
            )
        for li in budget.get("needs_expert") or []:
            lines.append(f"- {li.get('code')} (qty {li.get('qty')}) — needs an expert quote, no price yet")
        lines.append(
            f"Subtotal {budget.get('subtotal')} · contingency {budget.get('contingency')} · "
            f"total {budget.get('total')} {currency}"
        )

    if provenance:
        case_names = [c.get("filename") for c in (provenance.get("case_files") or []) if c.get("filename")]
        source_count = len(provenance.get("research_sources") or [])
        if case_names:
            lines.append("Based on case studies: " + ", ".join(case_names))
        if source_count:
            lines.append(f"Based on {source_count} market-research source(s) from this client's scan.")

    return "\n".join(lines)


async def plan_context_for_plan(session: AsyncSession, plan: Plan) -> str:
    """Load `plan`'s current version and render it via build_plan_context().

    Takes an already-authorized Plan (get_plan() is the ownership check) so
    this can never widen access on its own.
    """
    version = await get_current_version(session, plan)
    return build_plan_context(
        title=version.title,
        version_no=version.version_no,
        body=decrypt_body(version),
        budget=await budget_out(session, version),
        provenance=await provenance_out(session, version),
    )


async def get_active_plan(
    session: AsyncSession, user: User, workspace_id: uuid.UUID, plan_id: uuid.UUID | None
) -> Plan | None:
    """Non-raising counterpart to get_plan() for engagements.active_plan_id.

    A dangling/foreign active_plan_id must not 404 a chat turn the way an
    explicitly requested plan_id should — the client asked to talk, not to
    open that plan.
    """
    if plan_id is None:
        return None
    return (await session.execute(
        select(Plan).where(
            Plan.id == plan_id, Plan.workspace_id == workspace_id, Plan.user_id == user.id
        )
    )).scalar_one_or_none()


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
