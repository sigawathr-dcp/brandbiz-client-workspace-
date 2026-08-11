"""
app/services/chat_policy.py

Pre-stream helper that runs classification + policy decision BEFORE the
StreamingResponse is started. This is the only place where an HTTP 403 can
still be raised (once streaming starts, status is committed to 200).

Flow:
    1. Load + decrypt conversation history (§7.6 requires full payload).
    2. Classify history + new message to detect the data tier.
    3. Resolve "auto" → local model code (D16: always start local unless explicit).
    4. PolicyEngine.decide() → the single gate for all LLM routing (§7.2).
    5a. Deny → write audit row, commit, raise HTTPException(403).
    5b. Downgrade → write tier_blocked audit row, commit, continue.
    6. Return PreparedChat so the router can start the stream with already-
       loaded history (avoids double-decrypt in the orchestrator).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from fastapi import HTTPException
from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app import crypto
from app.config import settings
from app.llm.router import LOCAL_MODEL_CODE
from app.llm.tuning import GenerationTuning, ReasoningLevel, ResponseMode
from app.models.classification import DataTier
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.services import alert
from app.services import audit as audit_svc
from app.services.classifier import detect_tier
from app.services.policy_engine import DenyReason, PolicyEngine
from app.services import agent as agent_svc
from app.services import skill as skill_svc
from app.services.skill_selector import extract_forced_slug, select_skills
from app.tools.image_gen import IMAGE_MODEL_CODE, authorize_image, image_authorized, is_image_request
from app.tools.intent import classify_intent
from app.tools import rag_search


@dataclass
class PreparedChat:
    resolved_conversation_id: uuid.UUID
    history: list[dict]
    model_code: str
    downgrade_to_local: bool = False
    reasons: list[str] = field(default_factory=list)
    # Set when the request is an authorized image-generation request.
    # Presence (non-None) tells the orchestrator to route to generate_image_node.
    image_model_code: str | None = None
    # Set when the user's message contains a server-down / contact-admin keyword
    # AND N8N_WEBHOOK_URL is configured. Tells the orchestrator to route
    # through call_n8n_node (which fires the alert and emits the ack) before call_llm.
    n8n_route: bool = False
    # RAG: context block injected as a system message in call_llm.
    rag_context: str = ""
    # Citation metadata emitted as SSE "sources" event.
    citations: list[dict] = field(default_factory=list)
    # Agent system prompt (injected before RAG context in call_llm).
    system_prompt: str = ""
    # Per-turn response mode / reasoning level / temperature (G-A1/G-A2).
    tuning: GenerationTuning = field(default_factory=GenerationTuning)


async def load_history_messages(
    session: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
) -> tuple[uuid.UUID, list[dict]]:
    """Resolve (or create) the conversation and return decrypted message history."""
    if conversation_id is None:
        conv = Conversation(user_id=user_id)
        session.add(conv)
        await session.flush()
        resolved_id = conv.id
    else:
        result = await session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        resolved_id = conversation_id

    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == resolved_id)
        .order_by(Message.created_at)
        .limit(20)
    )
    rows = result.scalars().all()

    history: list[dict] = []
    for row in rows:
        plaintext = crypto.decrypt_message(
            row.content_ciphertext,
            row.content_nonce,
            row.content_tag,
            row.key_version,
        )
        history.append({"role": row.role, "content": plaintext})

    return resolved_id, history


async def prepare_chat(
    session: AsyncSession,
    user: User,
    conversation_id: uuid.UUID | None,
    user_content: str,
    requested_model: str,
    agent_id: uuid.UUID | None = None,
    explicit_skills: list[str] | None = None,
    workspace_id: uuid.UUID | None = None,
    mode: ResponseMode | None = None,
    reasoning_level: ReasoningLevel | None = None,
) -> PreparedChat:
    """
    Load history, classify, run policy decision, audit, and either raise 403
    or return a PreparedChat ready to hand into run_chat_stream.

    workspace_id: pass this when the caller has already authorized `agent_id`
    against an explicit workspace (app/routers/client.py, for both real
    client seats and staff previewing a demo workspace) rather than relying
    on the requesting user's own user.workspace_id — see
    agent_svc.get_agent_for_workspace for why the two can differ.

    mode / reasoning_level: explicit per-request overrides (G-A1/G-A2). When
    mode is None, it defaults to THINKING for an agent with
    capabilities.think_longer=True, else INSTANT — an explicit request value
    always wins, mirroring how agent.model already overrides "auto".
    """
    is_new = conversation_id is None
    resolved_id, history = await load_history_messages(session, user.id, conversation_id)

    # ---- Load agent if provided ----
    agent = None
    agent_system_prompt: str = ""
    agent_temperature: float | None = None
    agent_file_ids: list[uuid.UUID] = []
    if agent_id is not None:
        if workspace_id is not None:
            agent = await agent_svc.get_agent_for_workspace(session, agent_id, workspace_id)
        else:
            agent = await agent_svc.get_agent(session, agent_id, user.id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        if agent.instructions:
            agent_system_prompt = agent.instructions
        agent_temperature = agent_svc.creativity_to_temperature(agent.creativity_level)
        agent_file_ids = await agent_svc.get_agent_file_ids(session, agent_id)
        # Agent's configured model overrides "auto"
        if requested_model == "auto":
            requested_model = agent.model

    # Agent capability flags (used by intent routing below and image auth later).
    # Computed once here so the "auto" web-search routing decision can see them.
    caps = (agent.capabilities or {}) if agent else {}
    image_gen_enabled = caps.get("image_gen", True) if agent else True
    web_search_enabled = caps.get("web_search", True) if agent else True

    # G-A1: an agent's think_longer flag sets the per-agent default mode; an
    # explicit request mode always wins. Permissions live in PolicyEngine,
    # not this JSONB blob — think_longer=False must not block a user who
    # explicitly asks for Thinking.
    if mode is None:
        mode = ResponseMode.THINKING if caps.get("think_longer") else ResponseMode.INSTANT

    # ---- Skills: forced (/slug) + pinned (agent) + auto-matched (local LLM) ----
    # Instructions are creator-authored config (plaintext, like Agent.instructions),
    # so §7.1 encryption does not apply. Selection never touches an external model,
    # so it adds no policy/quota concern — the main call is still gated below.
    forced_slug, _ = extract_forced_slug(user_content)
    forced_slugs = [forced_slug] if forced_slug else []
    if explicit_skills:
        forced_slugs.extend(s for s in explicit_skills if s not in forced_slugs)

    pinned_skill_ids: list[uuid.UUID] = []
    if agent_id is not None:
        pinned_skill_ids = await skill_svc.get_agent_skill_ids(session, agent_id)

    skill_candidates = await skill_svc.get_enabled_skills(session, user.id)
    selected_skills = await select_skills(
        user_content, skill_candidates, forced_slugs, pinned_skill_ids
    )
    skill_block = skill_svc.build_skill_system_block(selected_skills)
    if skill_block:
        agent_system_prompt = "\n\n".join(filter(None, [agent_system_prompt, skill_block]))
        await audit_svc.log(
            action="skill_invoked",
            user_id=user.id,
            details={
                "skills": [s.name for s in selected_skills],
                "forced": forced_slugs,
                "pinned": [str(i) for i in pinned_skill_ids],
            },
        )

    # Auto-title new conversations from the first message (truncated to 60 chars)
    if is_new:
        title = user_content[:60].strip() or None
        updates: dict = {"title": title}
        if agent_id is not None:
            updates["agent_id"] = agent_id
        await session.execute(
            sa_update(Conversation)
            .where(Conversation.id == resolved_id)
            .values(**updates)
        )

    # ---- RAG retrieval (R3: before classify so retrieved text raises tier if needed) ----
    # When an agent has knowledge files, scope retrieval to those files only.
    rag_chunks = await rag_search.retrieve(
        session, user, user_content,
        file_ids=agent_file_ids if agent_file_ids else None,
    )
    rag_ctx = rag_search.build_context_block(rag_chunks)
    rag_cites = rag_search.citations(rag_chunks)

    if rag_chunks:
        await audit_svc.log(
            action="rag_query",
            user_id=user.id,
            details={"chunks_returned": len(rag_chunks), "top_score": rag_chunks[0].score},
        )

    # §7.6: classify full payload (all history + new message + retrieved context).
    # Including rag_ctx ensures that if a retrieved chunk contains confidential data
    # the entire request is treated at the higher tier (R3).
    payload_parts = [f'{m["role"]}: {m["content"]}' for m in history]
    payload_parts.append(f"user: {user_content}")
    if rag_ctx:
        payload_parts.append(f"retrieved_context: {rag_ctx}")
    tier: DataTier = detect_tier("\n".join(payload_parts))

    # Log PII detection whenever tier-3+ data is present (regardless of routing outcome)
    if tier.rank >= DataTier.TIER_3_CONFIDENTIAL.rank:
        await audit_svc.log(
            action="pii_detected",
            user_id=user.id,
            details={"tier": tier.value},
        )

    # "auto" routes by intent: local LLM classifies the message first; falls back
    # to regex if the model is unavailable. PolicyEngine still gates the chosen
    # model (tier/quota/permission) and will silently downgrade to local if denied.
    # When web_search is disabled on the agent, intent routing must not select
    # the Perplexity model (web search is implicit in that model).
    if requested_model == "auto":
        from app.llm.router import PERPLEXITY_MODEL_CODE  # avoid circular at module level
        intent_model = await classify_intent(user_content) or LOCAL_MODEL_CODE
        if not web_search_enabled and intent_model == PERPLEXITY_MODEL_CODE:
            intent_model = LOCAL_MODEL_CODE
        requested = intent_model
    else:
        requested = requested_model

    estimated_input_tokens = len("\n".join(payload_parts)) // 4  # heuristic; unused while quota stubbed

    decision = await PolicyEngine(session).decide(user, requested, tier, estimated_input_tokens)

    def _r(reason: object) -> str:
        return reason.value if hasattr(reason, "value") else str(reason)

    if not decision.allowed:
        deny_reasons = [_r(r) for r in decision.reasons]
        if DenyReason.TIER_4_REQUIRES_L5 in decision.reasons:
            audit_action = "tier_blocked"
        elif DenyReason.QUOTA_EXCEEDED in decision.reasons or DenyReason.WORKSPACE_BUDGET_EXCEEDED in decision.reasons:
            audit_action = "quota_exceeded"
        else:
            audit_action = "model_blocked"
        await audit_svc.log(
            action=audit_action,
            user_id=user.id,
            details={
                "model_requested": requested,
                "reasons": deny_reasons,
                "tier": tier.value,
            },
        )
        await session.commit()
        raise HTTPException(
            status_code=403,
            detail={
                "error": "policy_denied",
                "reasons": deny_reasons,
                "tier": tier.value,
            },
        )

    if decision.downgrade_to_local:
        await audit_svc.log(
            action="tier_blocked",
            user_id=user.id,
            details={
                "model_requested": requested,
                "model_used": decision.model_code,
                "reasons": [_r(r) for r in decision.reasons],
                "tier": tier.value,
            },
        )

    # ---- Image authorization (§7.2: PolicyEngine must gate every external call) ----
    # Only reached when the text-model decision was allowed (not a hard deny above).
    # authorize_image() calls PolicyEngine.decide() for gemini-3.1-flash-image using the SAME
    # data tier so Tier-3/4 content is blocked even for otherwise-permitted users.
    # When an agent is active, only detect image requests if the agent has image_gen enabled.
    # (image_gen_enabled / web_search_enabled / caps are computed early above.)

    image_model_code: str | None = None
    if image_gen_enabled and is_image_request(user_content):
        img_decision = await authorize_image(session, user, tier)
        if not image_authorized(img_decision):
            img_reasons = [_r(r) for r in img_decision.reasons]
            if DenyReason.ROLE_NOT_ALLOWED.value in img_reasons:
                denial_msg = (
                    "You are not authorized to generate images. "
                    "This feature is available to L5-level users and above, "
                    "or members of the Marketing department."
                )
            elif DenyReason.TIER_BLOCKS_EXTERNAL.value in img_reasons or DenyReason.TIER_4_REQUIRES_L5.value in img_reasons:
                denial_msg = (
                    "Image generation is not available because the conversation "
                    "contains confidential or restricted data."
                )
            else:
                denial_msg = "You are not authorized to generate images."
            await audit_svc.log(
                action="model_blocked",
                user_id=user.id,
                details={
                    "model_requested": IMAGE_MODEL_CODE,
                    "reasons": img_reasons,
                    "tier": tier.value,
                },
            )
            await session.commit()
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "image_generation_unauthorized",
                    "reasons": img_reasons,
                    "message": denial_msg,
                },
            )
        image_model_code = IMAGE_MODEL_CODE

    # ---- n8n alert routing ----
    # Route server-down / contact-admin prompts through the n8n node before
    # the LLM if the feature is enabled. Image requests take precedence (if
    # image_model_code is set, image_gen_node handles the full turn already).
    n8n_route: bool = (
        bool(settings.n8n_webhook_url)
        and image_model_code is None
        and alert.matches_alert(user_content)
    )

    # Commit before handing off to the streaming orchestrator. The Conversation
    # row was only flush()ed above; call_llm inserts Messages that FK-reference
    # it, so the row must be durable before the StreamingResponse starts.
    await session.commit()

    return PreparedChat(
        resolved_conversation_id=resolved_id,
        history=history,
        model_code=decision.model_code,
        downgrade_to_local=decision.downgrade_to_local,
        reasons=[_r(r) for r in decision.reasons],
        image_model_code=image_model_code,
        n8n_route=n8n_route,
        rag_context=rag_ctx,
        citations=rag_cites,
        system_prompt=agent_system_prompt,
        tuning=GenerationTuning(
            mode=mode,
            reasoning_level=reasoning_level,
            temperature=agent_temperature,
        ),
    )
