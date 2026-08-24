"""Unit tests for the LangGraph chat orchestrator."""
import asyncio
import base64
import json
import secrets
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.crypto as app_crypto
from app.agents.orchestrator import (
    ChatState,
    _ALERT_ACK,
    call_llm,
    call_n8n_node,
    emit_start,
    run_chat_collect_streamed,
    run_chat_stream,
)
from app.llm.base import ChatChunk
from app.llm.router import DEFAULT_MODEL_CODE

_TEST_KEY = base64.b64encode(secrets.token_bytes(32)).decode()


@pytest.fixture(autouse=True)
def setup_crypto_key(monkeypatch):
    """Ensure a valid 256-bit key is available for all orchestrator tests."""
    monkeypatch.setenv("ENCRYPTION_KEY", _TEST_KEY)
    monkeypatch.setenv("ENCRYPTION_KEY_VERSION", "1")
    app_crypto._key_store = None
    yield
    app_crypto._key_store = None


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def conv_id() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# emit_start tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_emit_start_puts_start_event_in_queue(user_id, conv_id):
    """emit_start puts a start event with conversation_id and model in the queue."""
    queue: asyncio.Queue = asyncio.Queue()

    state: ChatState = {
        "session": AsyncMock(),
        "user_id": user_id,
        "resolved_conversation_id": conv_id,
        "user_content": "hello",
        "model_code": DEFAULT_MODEL_CODE,
        "chunk_queue": queue,
        "downgrade_to_local": False,
        "reasons": [],
        "history": [],
    }
    await emit_start(state)

    assert not queue.empty()
    parsed = json.loads(queue.get_nowait())
    assert parsed["type"] == "start"
    assert parsed["conversation_id"] == str(conv_id)
    assert parsed["model"] == DEFAULT_MODEL_CODE


@pytest.mark.asyncio
async def test_emit_start_puts_downgrade_notice_when_flagged(user_id, conv_id):
    """When downgrade_to_local=True a notice event follows the start event."""
    queue: asyncio.Queue = asyncio.Queue()

    state: ChatState = {
        "session": AsyncMock(),
        "user_id": user_id,
        "resolved_conversation_id": conv_id,
        "user_content": "hello",
        "model_code": DEFAULT_MODEL_CODE,
        "chunk_queue": queue,
        "downgrade_to_local": True,
        "reasons": ["tier_blocks_external"],
        "history": [],
    }
    await emit_start(state)

    items = []
    while not queue.empty():
        items.append(json.loads(queue.get_nowait()))

    types = [i["type"] for i in items]
    assert "start" in types
    assert "notice" in types
    notice = next(i for i in items if i["type"] == "notice")
    assert notice["event"] == "downgrade_to_local"
    assert notice["reason"] == "tier_blocks_external"


# ---------------------------------------------------------------------------
# call_llm tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_call_llm_adds_two_encrypted_messages(mock_session, user_id, conv_id):
    """One user row and one assistant row are added to the DB session."""
    queue: asyncio.Queue = asyncio.Queue()

    async def fake_stream(messages, **opts):
        yield ChatChunk(content="Hi", prompt_tokens=5, completion_tokens=1, finish_reason="stop")

    mock_client = MagicMock()
    mock_client.stream_chat = fake_stream

    with patch("app.agents.orchestrator.get_router") as mock_router:
        mock_router.return_value.get.return_value = mock_client

        state: ChatState = {
            "session": mock_session,
            "user_id": user_id,
            "resolved_conversation_id": conv_id,
            "user_content": "hello",
            "model_code": DEFAULT_MODEL_CODE,
            "chunk_queue": queue,
            "downgrade_to_local": False,
            "reasons": [],
            "history": [],
        }
        result = await call_llm(state)

    assert mock_session.add.call_count == 2
    mock_session.commit.assert_called_once()
    assert result["full_response"] == "Hi"
    assert result["tokens_input"] == 5
    assert result["tokens_output"] == 1


@pytest.mark.asyncio
async def test_call_llm_content_is_encrypted_not_plaintext(mock_session, user_id, conv_id):
    """The Message objects added to the session contain ciphertext, not plaintext."""
    queue: asyncio.Queue = asyncio.Queue()

    async def fake_stream(messages, **opts):
        yield ChatChunk(content="Secret answer", finish_reason="stop")

    mock_client = MagicMock()
    mock_client.stream_chat = fake_stream

    with patch("app.agents.orchestrator.get_router") as mock_router:
        mock_router.return_value.get.return_value = mock_client

        state: ChatState = {
            "session": mock_session,
            "user_id": user_id,
            "resolved_conversation_id": conv_id,
            "user_content": "secret question",
            "model_code": DEFAULT_MODEL_CODE,
            "chunk_queue": queue,
            "downgrade_to_local": False,
            "reasons": [],
            "history": [],
        }
        await call_llm(state)

    added_messages = [call.args[0] for call in mock_session.add.call_args_list]
    for msg in added_messages:
        assert isinstance(msg.content_ciphertext, bytes)
        assert msg.content_ciphertext != b"secret question"
        assert msg.content_ciphertext != b"Secret answer"
        plaintext = app_crypto.decrypt(
            msg.content_ciphertext, msg.content_nonce, msg.content_tag, msg.key_version
        )
        assert plaintext in ("secret question", "Secret answer")


@pytest.mark.asyncio
async def test_call_llm_puts_chunks_and_done_in_queue(mock_session, user_id, conv_id):
    """Content chunks and a final done event are put in the queue, then a sentinel."""
    queue: asyncio.Queue = asyncio.Queue()

    async def fake_stream(messages, **opts):
        yield ChatChunk(content="Hello")
        yield ChatChunk(content=" world", finish_reason="stop", prompt_tokens=5, completion_tokens=2)

    mock_client = MagicMock()
    mock_client.stream_chat = fake_stream

    with patch("app.agents.orchestrator.get_router") as mock_router:
        mock_router.return_value.get.return_value = mock_client

        state: ChatState = {
            "session": mock_session,
            "user_id": user_id,
            "resolved_conversation_id": conv_id,
            "user_content": "test",
            "model_code": DEFAULT_MODEL_CODE,
            "chunk_queue": queue,
            "downgrade_to_local": False,
            "reasons": [],
            "history": [],
        }
        await call_llm(state)

    items = []
    while not queue.empty():
        item = queue.get_nowait()
        if item is None:
            break
        items.append(json.loads(item))

    content_chunks = [i for i in items if i["type"] == "content"]
    assert len(content_chunks) == 2
    assert content_chunks[0]["delta"] == "Hello"
    assert content_chunks[1]["delta"] == " world"

    done = [i for i in items if i["type"] == "done"]
    assert len(done) == 1
    assert done[0]["tokens_input"] == 5
    assert done[0]["tokens_output"] == 2


# ---------------------------------------------------------------------------
# run_chat_stream tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_chat_stream_yields_formatted_sse(mock_session, user_id, conv_id):
    """run_chat_stream wraps queue events as SSE lines (data: ...\\n\\n)."""

    async def fake_graph_safe(state: ChatState) -> None:
        q = state["chunk_queue"]
        await q.put(f'{{"type":"start","conversation_id":"{conv_id}","model":"{DEFAULT_MODEL_CODE}"}}')
        await q.put('{"type":"content","delta":"Hi"}')
        await q.put('{"type":"done","tokens_input":5,"tokens_output":1}')
        await q.put(None)

    with patch("app.agents.orchestrator._run_graph_safe", fake_graph_safe):
        events = []
        async for line in run_chat_stream(
            session=mock_session,
            user_id=user_id,
            user=MagicMock(),
            resolved_conversation_id=conv_id,
            user_content="hello",
            model_code=DEFAULT_MODEL_CODE,
            history=[],
        ):
            events.append(line)

    assert len(events) == 3
    assert all(e.startswith("data: ") and e.endswith("\n\n") for e in events)

    parsed = [json.loads(e[6:]) for e in events]
    assert parsed[0]["type"] == "start"
    assert parsed[1]["type"] == "content"
    assert parsed[1]["delta"] == "Hi"
    assert parsed[2]["type"] == "done"


# ---------------------------------------------------------------------------
# run_chat_collect_streamed tests (Task 3.12 -- live progress for background tasks)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_chat_collect_streamed_calls_on_event_per_item_and_returns_final(
    mock_session, user_id, conv_id
):
    """on_event fires once per queue item, in order, and the function still
    returns the same shape as run_chat_collect (full output + token counts)."""

    async def fake_graph_safe(state: ChatState) -> None:
        q = state["chunk_queue"]
        await q.put(f'{{"type":"start","conversation_id":"{conv_id}","model":"hermes-agent"}}')
        await q.put('{"type":"content","delta":"Hello"}')
        await q.put('{"type":"content","delta":" world"}')
        await q.put('{"type":"done","tokens_input":12,"tokens_output":34}')
        await q.put(None)

    received: list[dict] = []

    async def on_event(data: dict) -> None:
        received.append(data)

    with patch("app.agents.orchestrator._run_graph_safe", fake_graph_safe):
        result = await run_chat_collect_streamed(
            session=mock_session,
            user_id=user_id,
            user=MagicMock(),
            resolved_conversation_id=conv_id,
            user_content="hello",
            model_code="hermes-agent",
            history=[],
            on_event=on_event,
        )

    assert [e["type"] for e in received] == ["start", "content", "content", "done"]
    assert result == {
        "output": "Hello world",
        "model_used": "hermes-agent",
        "tokens_input": 12,
        "tokens_output": 34,
        "latency_ms": None,
    }


@pytest.mark.asyncio
async def test_run_chat_collect_streamed_works_without_on_event(mock_session, user_id, conv_id):
    """on_event is optional -- callers that don't need progress just get the result."""

    async def fake_graph_safe(state: ChatState) -> None:
        q = state["chunk_queue"]
        await q.put('{"type":"content","delta":"Hi"}')
        await q.put('{"type":"done","tokens_input":1,"tokens_output":1}')
        await q.put(None)

    with patch("app.agents.orchestrator._run_graph_safe", fake_graph_safe):
        result = await run_chat_collect_streamed(
            session=mock_session,
            user_id=user_id,
            user=MagicMock(),
            resolved_conversation_id=conv_id,
            user_content="hello",
            model_code="hermes-agent",
            history=[],
        )

    assert result["output"] == "Hi"


@pytest.mark.asyncio
async def test_run_chat_collect_streamed_raises_on_error_with_no_output(mock_session, user_id, conv_id):
    """An error event with no partial content raises, matching run_chat_collect."""

    async def fake_graph_safe(state: ChatState) -> None:
        q = state["chunk_queue"]
        await q.put('{"type":"error","message":"hermes unreachable: timeout"}')
        await q.put(None)

    with patch("app.agents.orchestrator._run_graph_safe", fake_graph_safe):
        with pytest.raises(RuntimeError, match="hermes unreachable"):
            await run_chat_collect_streamed(
                session=mock_session,
                user_id=user_id,
                user=MagicMock(),
                resolved_conversation_id=conv_id,
                user_content="hello",
                model_code="hermes-agent",
                history=[],
            )


# ---------------------------------------------------------------------------
# Quota consumption tests (local vs external)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_external_call_consumes_quota(mock_session, user_id, conv_id):
    """External model code triggers quota_svc.consume() after stream ends."""
    queue: asyncio.Queue = asyncio.Queue()
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.role = "L3"

    async def fake_stream(messages, **opts):
        yield ChatChunk(content="Hi", prompt_tokens=10, completion_tokens=5, finish_reason="stop")

    mock_client = MagicMock()
    mock_client.stream_chat = fake_stream

    with patch("app.agents.orchestrator.get_router") as mock_router, \
         patch("app.agents.orchestrator.quota_svc") as mock_quota_svc, \
         patch("app.agents.orchestrator._compute_cost", return_value=Decimal("0.01")):
        mock_router.return_value.get.return_value = mock_client
        mock_quota_svc.consume = AsyncMock(return_value=MagicMock())

        state: ChatState = {
            "session": mock_session,
            "user": mock_user,
            "user_id": user_id,
            "resolved_conversation_id": conv_id,
            "user_content": "hello",
            "model_code": "claude-sonnet-4",   # external — NOT DEFAULT_MODEL_CODE
            "chunk_queue": queue,
            "downgrade_to_local": False,
            "reasons": [],
            "history": [],
        }
        await call_llm(state)

    mock_quota_svc.consume.assert_called_once()
    args = mock_quota_svc.consume.call_args
    assert args.kwargs.get("tokens_input", args.args[2] if len(args.args) > 2 else None) == 10 or \
           10 in args.args or args.kwargs.get("tokens_input") == 10


@pytest.mark.parametrize("default_is_free, expect_consume", [(True, False), (False, True)])
@pytest.mark.asyncio
async def test_default_model_billing_follows_provider(
    mock_session, user_id, conv_id, default_is_free, expect_consume
):
    """D25: an on-prem default is free; a hosted (OpenAI) default consumes quota."""
    queue: asyncio.Queue = asyncio.Queue()
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.role = "L3"

    async def fake_stream(messages, **opts):
        yield ChatChunk(content="Hi", prompt_tokens=10, completion_tokens=5, finish_reason="stop")

    mock_client = MagicMock()
    mock_client.stream_chat = fake_stream

    with patch("app.agents.orchestrator.get_router") as mock_router, \
         patch("app.agents.orchestrator.quota_svc") as mock_quota_svc, \
         patch("app.agents.orchestrator.default_model_is_free", return_value=default_is_free), \
         patch("app.agents.orchestrator._compute_cost", new_callable=AsyncMock, return_value=0):
        mock_router.return_value.get.return_value = mock_client
        mock_quota_svc.consume = AsyncMock()

        state: ChatState = {
            "session": mock_session,
            "user": mock_user,
            "user_id": user_id,
            "resolved_conversation_id": conv_id,
            "user_content": "hello",
            "model_code": DEFAULT_MODEL_CODE,
            "chunk_queue": queue,
            "downgrade_to_local": False,
            "reasons": [],
            "history": [],
        }
        await call_llm(state)

    if expect_consume:
        mock_quota_svc.consume.assert_called_once()
    else:
        mock_quota_svc.consume.assert_not_called()


# ---------------------------------------------------------------------------
# call_n8n_node tests
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_user(user_id):
    user = MagicMock()
    user.id = user_id
    user.google_email = "user@example.com"
    return user


@pytest.mark.asyncio
async def test_call_n8n_node_emits_ack_and_fires_webhook(mock_session, user_id, conv_id, mock_user):
    """call_n8n_node emits the ack content delta and calls alert_svc.maybe_alert."""
    queue: asyncio.Queue = asyncio.Queue()
    state: ChatState = {
        "session": mock_session,
        "user_id": user_id,
        "user": mock_user,
        "resolved_conversation_id": conv_id,
        "user_content": "the server is down",
        "model_code": DEFAULT_MODEL_CODE,
        "chunk_queue": queue,
        "n8n_route": True,
    }

    with patch("app.agents.orchestrator.alert_svc") as mock_alert_svc:
        mock_alert_svc.maybe_alert = AsyncMock()
        result = await call_n8n_node(state)

    # Ack content delta was emitted
    assert not queue.empty()
    item = json.loads(queue.get_nowait())
    assert item["type"] == "content"
    assert "LINE alert" in item["delta"]

    # maybe_alert was called with the right args
    mock_alert_svc.maybe_alert.assert_awaited_once()
    call_kwargs = mock_alert_svc.maybe_alert.call_args
    assert call_kwargs.args[0] == "the server is down"
    assert call_kwargs.kwargs["user_email"] == "user@example.com"
    assert call_kwargs.kwargs["conversation_id"] == conv_id

    # Returns alert_ack so call_llm can prepend it to the stored assistant message
    assert result == {"alert_ack": _ALERT_ACK}

    # Does NOT emit "done" or the sentinel — call_llm owns those
    assert queue.empty()


@pytest.mark.asyncio
async def test_call_n8n_node_swallows_webhook_error(mock_session, user_id, conv_id, mock_user):
    """An n8n outage must not propagate — call_n8n_node never raises."""
    queue: asyncio.Queue = asyncio.Queue()
    state: ChatState = {
        "session": mock_session,
        "user_id": user_id,
        "user": mock_user,
        "resolved_conversation_id": conv_id,
        "user_content": "the server is down",
        "model_code": DEFAULT_MODEL_CODE,
        "chunk_queue": queue,
        "n8n_route": True,
    }

    with patch("app.agents.orchestrator.alert_svc") as mock_alert_svc:
        mock_alert_svc.maybe_alert = AsyncMock(side_effect=RuntimeError("n8n unreachable"))
        # Should complete without raising
        result = await call_n8n_node(state)

    # Ack was still emitted (before the webhook call)
    assert not queue.empty()
    item = json.loads(queue.get_nowait())
    assert item["type"] == "content"

    # Returns the ack dict despite the error
    assert result == {"alert_ack": _ALERT_ACK}


@pytest.mark.asyncio
async def test_call_llm_prepends_alert_ack_in_persisted_message(mock_session, user_id, conv_id):
    """When alert_ack is set in state, call_llm stores ack+response in the DB row."""
    queue: asyncio.Queue = asyncio.Queue()

    async def fake_stream(messages, **opts):
        yield ChatChunk(content="LLM answer", finish_reason="stop")

    mock_client = MagicMock()
    mock_client.stream_chat = fake_stream

    ack = _ALERT_ACK

    with patch("app.agents.orchestrator.get_router") as mock_router:
        mock_router.return_value.get.return_value = mock_client

        state: ChatState = {
            "session": mock_session,
            "user_id": user_id,
            "resolved_conversation_id": conv_id,
            "user_content": "server is down",
            "model_code": DEFAULT_MODEL_CODE,
            "chunk_queue": queue,
            "downgrade_to_local": False,
            "reasons": [],
            "history": [],
            "alert_ack": ack,
        }
        await call_llm(state)

    # Inspect the persisted assistant message (second add() call)
    added = [call.args[0] for call in mock_session.add.call_args_list]
    assistant_msg = added[1]  # user row is [0], assistant is [1]
    decrypted = app_crypto.decrypt(
        assistant_msg.content_ciphertext,
        assistant_msg.content_nonce,
        assistant_msg.content_tag,
        assistant_msg.key_version,
    )
    # Stored text must include both the ack and the LLM answer
    assert decrypted.startswith(ack)
    assert "LLM answer" in decrypted


@pytest.mark.asyncio
async def test_run_chat_stream_with_n8n_route_emits_ack_before_llm_content(mock_session, user_id, conv_id):
    """When n8n_route=True the SSE stream contains the ack content delta before LLM chunks."""

    async def fake_graph_safe(state: ChatState) -> None:
        q = state["chunk_queue"]
        await q.put(f'{{"type":"start","conversation_id":"{conv_id}","model":"{DEFAULT_MODEL_CODE}"}}')
        await q.put(json.dumps({"type": "content", "delta": _ALERT_ACK}))
        await q.put('{"type":"content","delta":"LLM answer"}')
        await q.put('{"type":"done","tokens_input":5,"tokens_output":3}')
        await q.put(None)

    with patch("app.agents.orchestrator._run_graph_safe", fake_graph_safe):
        events = []
        async for line in run_chat_stream(
            session=mock_session,
            user_id=user_id,
            user=MagicMock(),
            resolved_conversation_id=conv_id,
            user_content="the server is down",
            model_code=DEFAULT_MODEL_CODE,
            history=[],
            n8n_route=True,
        ):
            events.append(json.loads(line.removeprefix("data: ").strip()))

    content_events = [e for e in events if e["type"] == "content"]
    assert len(content_events) == 2
    assert "LINE alert" in content_events[0]["delta"]   # ack first
    assert content_events[1]["delta"] == "LLM answer"   # LLM answer follows
