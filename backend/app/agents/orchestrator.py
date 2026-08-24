import asyncio
import json
import logging
import time
import uuid
from decimal import Decimal
from typing import Any, AsyncIterator, Awaitable, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crypto
from app.llm.base import ChatMessage
from app.llm.router import DEFAULT_MODEL_CODE, default_model_is_free, get_router
from app.llm.tuning import GenerationTuning
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.model_catalog import ModelCatalog
from app.models.user import User
from app.services import alert as alert_svc
from app.services import audit as audit_svc
from app.services import quota as quota_svc
from app.tools import image_gen as image_gen_tool

_logger = logging.getLogger(__name__)


class ChatState(TypedDict, total=False):
    # Caller-supplied inputs
    session: Any            # AsyncSession — not JSON-serializable; ok without checkpointer
    user_id: uuid.UUID
    user: User              # Full User object — required for quota consumption
    user_content: str
    model_code: str
    chunk_queue: Any        # asyncio.Queue[str | None]
    downgrade_to_local: bool
    reasons: list[str]
    # Pre-loaded by chat_policy.prepare_chat (avoids double-decrypt)
    resolved_conversation_id: uuid.UUID
    history: list[dict]     # {"role": ..., "content": ...} plaintext dicts
    # Stamped onto both persisted Message rows (messages.engagement_step_id,
    # migration 0050). None for ordinary chat — including a client's
    # free-form turns, which is exactly what GET /client/bootstrap replays.
    # Set only by machine-driven turns that happen to share the engagement's
    # conversation (services/plan.py::draft_plan sends an ~8k-char prompt and
    # gets raw JSON back), so the transcript replay can leave them out.
    engagement_step_id: uuid.UUID | None
    # Set by run_chat_stream when chat_policy authorised an image request.
    # Presence (non-None) tells _route_after_start to go to generate_image_node.
    image_model_code: str | None
    # Set by run_chat_stream when chat_policy detected a server-down/contact-admin
    # intent AND N8N_WEBHOOK_URL is configured.  Routes emit_start → call_n8n
    # → call_llm instead of the default emit_start → call_llm path.
    n8n_route: bool
    # RAG context block (plaintext; injected as system message in call_llm)
    rag_context: str
    # Citation metadata for the SSE "sources" event
    citations: list[dict]
    # Set by run_chat_stream when routers/client.py judged this turn to be a
    # request to CHANGE the client's plan. Emitted as a notice so the frontend
    # can offer a confirmation chip; nothing is revised until the client taps it
    # and the frontend calls POST /client/plan/revise. The orchestrator never
    # acts on it — it only carries it.
    plan_edit_plan_id: uuid.UUID | None
    # Agent system prompt (prepended before RAG context as a "system" message)
    system_prompt: str
    # Per-turn response mode / reasoning level / temperature (G-A1/G-A2).
    # See app.llm.tuning.GenerationTuning — the single seam through which
    # per-turn knobs reach a vendor adapter (§7.2: adapters translate, the
    # orchestrator never branches on provider).
    tuning: GenerationTuning
    # Set by call_n8n_node — the acknowledgment prepended to the persisted
    # assistant message so history matches exactly what the user saw.
    alert_ack: str
    # Set by call_llm
    full_response: str
    tokens_input: int | None
    tokens_output: int | None
    latency_ms: int | None


async def emit_start(state: ChatState) -> dict:
    """Emit the SSE start event, optional downgrade notice, and optional sources."""
    queue: asyncio.Queue = state["chunk_queue"]
    model_code: str = state["model_code"]
    resolved_id: uuid.UUID = state["resolved_conversation_id"]
    tuning: GenerationTuning = state.get("tuning") or GenerationTuning()

    await queue.put(json.dumps({
        "type": "start",
        "conversation_id": str(resolved_id),
        "model": model_code,
    }))

    if state.get("downgrade_to_local"):
        reasons: list[str] = state.get("reasons", [])
        await queue.put(json.dumps({
            "type": "notice",
            "event": "downgrade_to_local",
            "model": model_code,
            "reason": reasons[0] if reasons else "tier_blocks_external",
        }))

    result: dict = {}

    # G-A2: if the resolved model can't honor the requested reasoning depth,
    # say so before content starts (§7.4) and strip it — a silently-ignored
    # Thinking toggle is the same "dumber on Mondays" trap as a hidden
    # downgrade (PLAN.md §8 Gotcha 10).
    if tuning.effective_reasoning() is not None:
        try:
            client = get_router().get(model_code)
        except KeyError:
            client = None
        if client is not None and not client.supports_reasoning:
            await queue.put(json.dumps({
                "type": "notice",
                "event": "reasoning_unavailable",
                "model": model_code,
                "requested": tuning.effective_reasoning().value,
            }))
            result["tuning"] = tuning.without_reasoning()

    # Emit retrieved citations so the frontend can show source chips before
    # the LLM starts streaming content.
    citations: list[dict] = state.get("citations", [])
    if citations:
        await queue.put(json.dumps({
            "type": "sources",
            "sources": citations,
        }))

    # Offer the plan-edit confirmation before content starts, for the same
    # reason citations go first: the chip is about the turn as a whole, and a
    # client who has finished reading the answer has already moved on.
    plan_edit_plan_id = state.get("plan_edit_plan_id")
    if plan_edit_plan_id is not None:
        await queue.put(json.dumps({
            "type": "notice",
            "event": "plan_edit_suggested",
            "plan_id": str(plan_edit_plan_id),
        }))

    return result


async def _compute_cost(
    session: AsyncSession,
    model_code: str,
    tokens_input: int,
    tokens_output: int,
) -> Decimal:
    """Return cost in USD based on ModelCatalog rates; returns 0 if rates unknown."""
    row = (await session.execute(
        select(
            ModelCatalog.cost_per_1k_input_tokens,
            ModelCatalog.cost_per_1k_output_tokens,
        ).where(ModelCatalog.code == model_code)
    )).one_or_none()
    if row is None or row.cost_per_1k_input_tokens is None:
        return Decimal("0")
    cost_in = row.cost_per_1k_input_tokens * Decimal(tokens_input) / 1000
    cost_out = (row.cost_per_1k_output_tokens or Decimal("0")) * Decimal(tokens_output) / 1000
    return cost_in + cost_out


async def call_llm(state: ChatState) -> dict:
    session: AsyncSession = state["session"]
    resolved_conv_id: uuid.UUID = state["resolved_conversation_id"]
    user_content: str = state["user_content"]
    model_code: str = state["model_code"]
    history: list[dict] = state.get("history", [])
    queue: asyncio.Queue = state["chunk_queue"]
    user: User | None = state.get("user")

    # Build system messages in order: agent instructions → RAG context.
    # Agent system prompt (if any) is injected first so it frames how the LLM
    # should interpret the retrieved knowledge and conversation history.
    system_prompt: str = state.get("system_prompt", "")
    rag_context: str = state.get("rag_context", "")
    tuning: GenerationTuning = state.get("tuning") or GenerationTuning()

    llm_messages: list[ChatMessage] = []
    if system_prompt:
        llm_messages.append(ChatMessage(role="system", content=system_prompt))
    if rag_context:
        llm_messages.append(ChatMessage(role="system", content=rag_context))
    llm_messages.extend(
        ChatMessage(role=msg["role"], content=msg["content"])
        for msg in history
    )
    llm_messages.append(ChatMessage(role="user", content=user_content))

    client = get_router().get(model_code)

    full_response = ""
    tokens_input: int | None = None
    tokens_output: int | None = None
    t0 = time.monotonic()

    # §7.5: wrap stream so mid-stream failures charge partial usage
    stream_exc: Exception | None = None
    thinking_notified = False

    try:
        async for chunk in client.stream_chat(llm_messages, tuning=tuning):
            if chunk.content:
                full_response += chunk.content
                await queue.put(json.dumps({"type": "content", "delta": chunk.content}))
            elif chunk.metadata and chunk.metadata.get("thinking") and not thinking_notified:
                # One-shot "the model is reasoning" signal — the adapter may
                # emit many empty thinking deltas; only the first is useful.
                thinking_notified = True
                await queue.put(json.dumps({
                    "type": "notice",
                    "event": "reasoning_started",
                    "model": model_code,
                }))
            if chunk.prompt_tokens is not None:
                tokens_input = chunk.prompt_tokens
            if chunk.completion_tokens is not None:
                tokens_output = chunk.completion_tokens
    except Exception as exc:
        stream_exc = exc

    latency_ms = int((time.monotonic() - t0) * 1000)

    # Persist user message — encrypted at the app boundary (Section 7.1)
    step_id: uuid.UUID | None = state.get("engagement_step_id")
    ct, nonce, tag, kv = crypto.encrypt(user_content)
    session.add(Message(
        conversation_id=resolved_conv_id,
        role="user",
        engagement_step_id=step_id,
        content_ciphertext=ct,
        content_nonce=nonce,
        content_tag=tag,
        key_version=kv,
        model_used=model_code,
        tokens_input=tokens_input,
    ))

    # Persist assistant message — encrypted.
    # When call_n8n_node ran first it already emitted the ack as an SSE content
    # delta. Prepend the ack here so the stored history row matches exactly what
    # the user saw (ack text + LLM answer), keeping conversation history coherent.
    alert_ack: str = state.get("alert_ack", "")
    persisted_assistant = (alert_ack + full_response) if alert_ack else (full_response or "")
    ct2, nonce2, tag2, kv2 = crypto.encrypt(persisted_assistant)
    session.add(Message(
        conversation_id=resolved_conv_id,
        role="assistant",
        engagement_step_id=step_id,
        content_ciphertext=ct2,
        content_nonce=nonce2,
        content_tag=tag2,
        key_version=kv2,
        model_used=model_code,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        latency_ms=latency_ms,
    ))
    await session.commit()

    user_id: uuid.UUID = state["user_id"]
    effective_reasoning = tuning.effective_reasoning()
    await audit_svc.log(
        action="message_sent",
        user_id=user_id,
        details={
            "conversation_id": str(resolved_conv_id),
            "model_used": model_code,
            "mode": tuning.mode.value,
            "reasoning": effective_reasoning.value if effective_reasoning else None,
        },
    )
    await audit_svc.log(
        action="message_received",
        user_id=user_id,
        details={
            "conversation_id": str(resolved_conv_id),
            "model_used": model_code,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "latency_ms": latency_ms,
        },
    )

    # §7.5: commit actual token usage. D25: the default model is hosted
    # (OpenAI) and therefore charged too; only an on-prem default is free.
    if user is not None and not (model_code == DEFAULT_MODEL_CODE and default_model_is_free()):
        t_in = tokens_input or 0
        t_out = tokens_output or 0
        if t_in > 0 or t_out > 0:
            cost = await _compute_cost(session, model_code, t_in, t_out)
            await quota_svc.consume(session, user, t_in, t_out, cost)

    # Re-raise stream exception after persisting partial usage (§7.5)
    if stream_exc is not None:
        raise stream_exc

    await queue.put(json.dumps({
        "type": "done",
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
    }))
    await queue.put(None)  # sentinel — signals run_chat_stream to stop

    return {
        "full_response": full_response,
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "latency_ms": latency_ms,
    }


async def generate_image_node(state: ChatState) -> dict:
    """Orchestrator node for image generation.

    Only reachable when chat_policy.prepare_chat has already authorised the
    request via PolicyEngine.decide() — no additional permission check needed here.
    """
    session: AsyncSession = state["session"]
    user_content: str = state["user_content"]
    user_id: uuid.UUID = state["user_id"]
    resolved_conv_id: uuid.UUID = state["resolved_conversation_id"]
    queue: asyncio.Queue = state["chunk_queue"]
    image_model_code: str = state.get("image_model_code") or image_gen_tool.IMAGE_MODEL_CODE

    await audit_svc.log(
        action="image_requested",
        user_id=user_id,
        details={"prompt_length": len(user_content)},
    )

    try:
        image_bytes, mime_type = await image_gen_tool.generate_image_bytes(user_content)
    except Exception as exc:
        await queue.put(json.dumps({"type": "error", "message": str(exc)}))
        await queue.put(None)
        return {}

    data_url = image_gen_tool.bytes_to_data_url(image_bytes, mime_type)
    # Store as a markdown image so the conversation history renders correctly on reload.
    assistant_text = f"![Generated image]({data_url})"

    # Persist both messages encrypted (§7.1)
    step_id: uuid.UUID | None = state.get("engagement_step_id")
    ct, nonce, tag, kv = crypto.encrypt(user_content)
    session.add(Message(
        conversation_id=resolved_conv_id,
        role="user",
        engagement_step_id=step_id,
        content_ciphertext=ct,
        content_nonce=nonce,
        content_tag=tag,
        key_version=kv,
        model_used=image_model_code,
    ))
    ct2, nonce2, tag2, kv2 = crypto.encrypt(assistant_text)
    session.add(Message(
        conversation_id=resolved_conv_id,
        role="assistant",
        engagement_step_id=step_id,
        content_ciphertext=ct2,
        content_nonce=nonce2,
        content_tag=tag2,
        key_version=kv2,
        model_used=image_model_code,
        tokens_input=0,
        tokens_output=0,
    ))
    await session.commit()

    await audit_svc.log(
        action="image_generated",
        user_id=user_id,
        details={"bytes": len(image_bytes)},
    )

    await queue.put(json.dumps({"type": "image", "url": data_url}))
    await queue.put(json.dumps({"type": "done", "tokens_input": 0, "tokens_output": 0}))
    await queue.put(None)
    return {}


# Acknowledgment shown to the user when the n8n admin-alert routing fires.
# Emitted as the first SSE content delta so it appears before the LLM starts streaming.
_ALERT_ACK = (
    "✅ I've notified the admin team about the server issue. "
    "They'll get a LINE alert shortly.\n\n"
)


async def call_n8n_node(state: ChatState) -> dict:
    """Orchestrator node that fires the n8n admin-alert webhook before the LLM answers.

    Only reachable when chat_policy.prepare_chat detected a server-down / contact-admin
    intent AND N8N_WEBHOOK_URL is configured.

    Steps:
    1. Emit the fixed acknowledgment as an SSE content delta so the user sees it
       immediately, before the LLM starts streaming.
    2. Await alert_svc.maybe_alert() to POST the n8n webhook (throttled, never-raises).
    3. Write an n8n_triggered audit row.
    4. Return {"alert_ack": _ALERT_ACK} so call_llm can prepend it to the persisted
       assistant message — history must match what the user saw (ack + LLM answer).
    5. Do NOT emit "done" or the None sentinel — call_llm owns those terminal events.
    """
    queue: asyncio.Queue = state["chunk_queue"]
    user_content: str = state["user_content"]
    user_id: uuid.UUID = state["user_id"]
    user: User | None = state.get("user")
    resolved_conv_id: uuid.UUID = state["resolved_conversation_id"]

    # Emit ack immediately — the user sees this before the LLM starts streaming.
    await queue.put(json.dumps({"type": "content", "delta": _ALERT_ACK}))

    # Fire the n8n webhook. Errors are swallowed so an n8n outage never blocks
    # the subsequent LLM call.
    try:
        await alert_svc.maybe_alert(
            user_content,
            source="chat_routed",
            user_email=user.google_email if user else "unknown",
            conversation_id=resolved_conv_id,
        )
        await audit_svc.log(
            action="n8n_triggered",
            user_id=user_id,
            details={
                "source": "call_n8n_node",
                "conversation_id": str(resolved_conv_id),
            },
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning("call_n8n_node: n8n webhook call failed: %s", exc)

    return {"alert_ack": _ALERT_ACK}


def _route_after_start(state: ChatState) -> str:
    """Route based on what chat_policy pre-authorised / detected.

    - image_model_code set → generate_image (terminal; call_llm is skipped).
    - n8n_route set → call_n8n (non-terminal; falls through to call_llm).
    - default → call_llm directly.

    Both flags are set in prepare_chat before the StreamingResponse starts, so
    their authorization / detection is already done — route unconditionally.
    """
    if state.get("image_model_code"):
        return "generate_image"
    if state.get("n8n_route"):
        return "call_n8n"
    return "call_llm"


def _build_graph() -> Any:
    builder: StateGraph = StateGraph(ChatState)
    builder.add_node("emit_start", emit_start)
    builder.add_node("call_llm", call_llm)
    builder.add_node("generate_image", generate_image_node)
    builder.add_node("call_n8n", call_n8n_node)
    builder.add_edge(START, "emit_start")
    builder.add_conditional_edges(
        "emit_start",
        _route_after_start,
        {
            "call_llm": "call_llm",
            "generate_image": "generate_image",
            "call_n8n": "call_n8n",
        },
    )
    builder.add_edge("call_llm", END)
    builder.add_edge("generate_image", END)
    # call_n8n is non-terminal: fires the alert then hands off to call_llm.
    builder.add_edge("call_n8n", "call_llm")
    return builder.compile()


_chat_graph = _build_graph()


async def _run_graph_safe(state: ChatState) -> None:
    """Run the chat graph, funnelling any exception as an SSE error event."""
    queue: asyncio.Queue = state["chunk_queue"]
    try:
        await _chat_graph.ainvoke(state)
    except Exception as exc:
        await queue.put(json.dumps({"type": "error", "message": str(exc)}))
        await queue.put(None)


async def run_chat_collect(
    session: AsyncSession,
    user_id: uuid.UUID,
    user: User,
    resolved_conversation_id: uuid.UUID,
    user_content: str,
    model_code: str,
    history: list[dict],
    downgrade_to_local: bool = False,
    reasons: list[str] | None = None,
    image_model_code: str | None = None,
    n8n_route: bool = False,
    rag_context: str = "",
    citations: list[dict] | None = None,
    system_prompt: str = "",
    tuning: GenerationTuning | None = None,
    engagement_step_id: uuid.UUID | None = None,
) -> dict:
    """Non-streaming variant of run_chat_stream — drives the same LangGraph and
    returns the full response as a plain dict.

    Used by external callers (e.g. n8n via POST /automations/agent) that cannot
    consume SSE.  All governance (audit, quota, encryption) runs inside call_llm
    identically to the streaming path — no duplication.

    Returns:
        {
            "output":        str,        # full assistant reply
            "model_used":    str,        # resolved model code
            "tokens_input":  int | None,
            "tokens_output": int | None,
            "latency_ms":    int | None,
        }
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    state: ChatState = {
        "session": session,
        "user_id": user_id,
        "user": user,
        "resolved_conversation_id": resolved_conversation_id,
        "user_content": user_content,
        "model_code": model_code,
        "history": history,
        "chunk_queue": queue,
        "downgrade_to_local": downgrade_to_local,
        "reasons": reasons or [],
        "image_model_code": image_model_code,
        "n8n_route": n8n_route,
        "rag_context": rag_context,
        "citations": citations or [],
        "system_prompt": system_prompt,
        "tuning": tuning or GenerationTuning(),
        "engagement_step_id": engagement_step_id,
    }
    await _chat_graph.ainvoke(state)

    # Drain the queue to collect the full response and token counts.
    # ainvoke() returns only after every node completes, so all queue.put()
    # calls inside call_llm / generate_image_node are already done — draining
    # synchronously (get_nowait) is safe and avoids relying on LangGraph state
    # propagation, which varies across versions.
    full_response = ""
    tokens_input: int | None = None
    tokens_output: int | None = None
    image_url: str | None = None
    error_message: str | None = None

    while True:
        try:
            item = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if item is None:  # sentinel — end of stream
            break
        data: dict = json.loads(item)
        kind = data.get("type")
        if kind == "content":
            full_response += data.get("delta", "")
        elif kind == "done":
            tokens_input = data.get("tokens_input")
            tokens_output = data.get("tokens_output")
        elif kind == "image":
            # generate_image_node emits the data URL here. The streaming path
            # renders it client-side; non-streaming callers (n8n) get it as the
            # markdown image the assistant message is stored as (§ orchestrator).
            image_url = data.get("url")
        elif kind == "error":
            # An error event means a node failed (e.g. image gen with no API key).
            # The streaming path surfaces this as an SSE error; non-streaming
            # callers must not silently receive an empty output — capture it so
            # the endpoint can raise instead of returning output="".
            error_message = data.get("message")
        # "start" / "notice" events carry no payload for non-streaming callers

    if error_message is not None and not full_response and image_url is None:
        # Surface the underlying failure to the caller instead of an empty reply.
        raise RuntimeError(error_message)

    if image_url is not None and not full_response:
        full_response = f"![Generated image]({image_url})"

    return {
        "output": full_response,
        "model_used": model_code,
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "latency_ms": None,
    }


async def run_chat_collect_streamed(
    session: AsyncSession,
    user_id: uuid.UUID,
    user: User,
    resolved_conversation_id: uuid.UUID,
    user_content: str,
    model_code: str,
    history: list[dict],
    on_event: Callable[[dict], Awaitable[None]] | None = None,
    downgrade_to_local: bool = False,
    reasons: list[str] | None = None,
    image_model_code: str | None = None,
    n8n_route: bool = False,
    rag_context: str = "",
    citations: list[dict] | None = None,
    system_prompt: str = "",
    tuning: GenerationTuning | None = None,
) -> dict:
    """Streaming variant of run_chat_collect for callers that want incremental
    progress instead of only the final result -- used by background agent
    tasks (Task 3.12) so the Tasks page can show a live activity log while
    Hermes is still working.

    Drives the same LangGraph via the same create-task-and-drain-the-queue
    pattern as run_chat_stream (including its 30-minute hard cap), but calls
    on_event(dict) per queue item instead of yielding SSE lines, and returns
    the same shape as run_chat_collect. All governance (audit, quota,
    encryption) still runs inside call_llm identically to both other
    entrypoints -- no duplication.

    The richness of on_event payloads is whatever call_llm/emit_start put on
    the queue -- today that's "start"/"notice"/"sources"/"content"/"done"/
    "error", i.e. streamed text plus a few status markers, not per-tool-call
    structure (Hermes's OpenAI-compatible stream doesn't expose that).
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    state: ChatState = {
        "session": session,
        "user_id": user_id,
        "user": user,
        "resolved_conversation_id": resolved_conversation_id,
        "user_content": user_content,
        "model_code": model_code,
        "history": history,
        "chunk_queue": queue,
        "downgrade_to_local": downgrade_to_local,
        "reasons": reasons or [],
        "image_model_code": image_model_code,
        "n8n_route": n8n_route,
        "rag_context": rag_context,
        "citations": citations or [],
        "system_prompt": system_prompt,
        "tuning": tuning or GenerationTuning(),
    }
    graph_task = asyncio.create_task(_run_graph_safe(state))

    full_response = ""
    tokens_input: int | None = None
    tokens_output: int | None = None
    image_url: str | None = None
    error_message: str | None = None

    # Background tasks run unattended and Hermes's own tool loop can run long;
    # reuse the same hard cap as the interactive stream so a stuck graph can't
    # wedge the worker forever.
    deadline = asyncio.get_event_loop().time() + 1800
    try:
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                error_message = "LLM response timeout"
                break
            try:
                item: str | None = await asyncio.wait_for(
                    queue.get(), timeout=min(25.0, remaining)
                )
            except asyncio.TimeoutError:
                continue
            if item is None:
                break
            data: dict = json.loads(item)
            if on_event is not None:
                await on_event(data)
            kind = data.get("type")
            if kind == "content":
                full_response += data.get("delta", "")
            elif kind == "done":
                tokens_input = data.get("tokens_input")
                tokens_output = data.get("tokens_output")
            elif kind == "image":
                image_url = data.get("url")
            elif kind == "error":
                error_message = data.get("message")
    finally:
        if not graph_task.done():
            graph_task.cancel()
        try:
            await graph_task
        except (asyncio.CancelledError, Exception):
            pass

    if error_message is not None and not full_response and image_url is None:
        raise RuntimeError(error_message)

    if image_url is not None and not full_response:
        full_response = f"![Generated image]({image_url})"

    return {
        "output": full_response,
        "model_used": model_code,
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "latency_ms": None,
    }


async def run_chat_stream(
    session: AsyncSession,
    user_id: uuid.UUID,
    user: User,
    resolved_conversation_id: uuid.UUID,
    user_content: str,
    model_code: str,
    history: list[dict],
    downgrade_to_local: bool = False,
    reasons: list[str] | None = None,
    image_model_code: str | None = None,
    n8n_route: bool = False,
    rag_context: str = "",
    citations: list[dict] | None = None,
    system_prompt: str = "",
    tuning: GenerationTuning | None = None,
    plan_edit_plan_id: uuid.UUID | None = None,
) -> AsyncIterator[str]:
    """Async generator that drives the LangGraph and yields SSE-formatted lines.

    History, model_code, image_model_code, rag_context, and citations come
    pre-resolved by chat_policy.prepare_chat so we never double-decrypt and
    PolicyEngine.decide() is the only model selector — including for image gen.
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    state: ChatState = {
        "session": session,
        "user_id": user_id,
        "user": user,
        "resolved_conversation_id": resolved_conversation_id,
        "user_content": user_content,
        "model_code": model_code,
        "history": history,
        "chunk_queue": queue,
        "downgrade_to_local": downgrade_to_local,
        "reasons": reasons or [],
        "image_model_code": image_model_code,
        "n8n_route": n8n_route,
        "rag_context": rag_context,
        "citations": citations or [],
        "system_prompt": system_prompt,
        "tuning": tuning or GenerationTuning(),
        "plan_edit_plan_id": plan_edit_plan_id,
    }
    graph_task = asyncio.create_task(_run_graph_safe(state))
    deadline = asyncio.get_event_loop().time() + 1800  # 30-minute hard cap
    try:
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                yield 'data: {"type":"error","message":"LLM response timeout"}\n\n'
                break
            try:
                # Short window so we can send SSE keepalives and prevent
                # proxies / browsers from dropping an idle connection mid-stream.
                item: str | None = await asyncio.wait_for(
                    queue.get(), timeout=min(25.0, remaining)
                )
            except asyncio.TimeoutError:
                # No token in the last 25 s — send an SSE comment to keep
                # the connection alive and loop back to wait again.
                yield ": keepalive\n\n"
                continue
            if item is None:
                break
            yield f"data: {item}\n\n"
    finally:
        if not graph_task.done():
            graph_task.cancel()
        try:
            await graph_task
        except (asyncio.CancelledError, Exception):
            pass
