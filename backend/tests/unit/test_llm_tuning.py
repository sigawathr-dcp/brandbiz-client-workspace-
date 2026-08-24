"""Unit tests for the G-A1/G-A2 typed tuning seam.

Covers:
- app.llm.tuning.GenerationTuning: mode/reasoning_level resolution rules.
- orchestrator.call_llm: tuning reaches LLMClient.stream_chat via the typed
  `tuning=` kwarg, not a stray dict of options — the regression that no
  existing test caught before this (every prior fake's signature was
  `(messages, **_)` and swallowed everything).
- orchestrator.emit_start: reasoning_unavailable notice + tuning stripped
  when the resolved model can't honor it; a one-shot reasoning_started
  notice from call_llm when a chunk carries metadata={"thinking": True}.
"""
from __future__ import annotations

import asyncio
import base64
import json
import secrets
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.crypto as app_crypto
from app.agents.orchestrator import ChatState, call_llm, emit_start
from app.llm.base import ChatChunk
from app.llm.router import DEFAULT_MODEL_CODE
from app.llm.tuning import GenerationTuning, ReasoningLevel, ResponseMode

_TEST_KEY = base64.b64encode(secrets.token_bytes(32)).decode()


@pytest.fixture(autouse=True)
def setup_crypto_key(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", _TEST_KEY)
    monkeypatch.setenv("ENCRYPTION_KEY_VERSION", "1")
    app_crypto._key_store = None
    yield
    app_crypto._key_store = None


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
# GenerationTuning resolution rules
# ---------------------------------------------------------------------------

class TestGenerationTuning:
    def test_instant_never_reasons_even_with_explicit_level(self):
        tuning = GenerationTuning(mode=ResponseMode.INSTANT, reasoning_level=ReasoningLevel.MAX)
        assert tuning.effective_reasoning() is None

    def test_thinking_defaults_to_medium(self):
        assert GenerationTuning(mode=ResponseMode.THINKING).effective_reasoning() is ReasoningLevel.MEDIUM

    def test_pro_defaults_to_high(self):
        assert GenerationTuning(mode=ResponseMode.PRO).effective_reasoning() is ReasoningLevel.HIGH

    def test_explicit_reasoning_level_overrides_mode_default(self):
        tuning = GenerationTuning(mode=ResponseMode.THINKING, reasoning_level=ReasoningLevel.LOW)
        assert tuning.effective_reasoning() is ReasoningLevel.LOW

    def test_without_reasoning_disables_regardless_of_mode(self):
        tuning = GenerationTuning(mode=ResponseMode.PRO, reasoning_level=ReasoningLevel.MAX)
        stripped = tuning.without_reasoning()
        assert stripped.effective_reasoning() is None
        # Original is untouched — frozen dataclass, no in-place mutation.
        assert tuning.effective_reasoning() is ReasoningLevel.MAX

    def test_default_tuning_is_instant_with_no_temperature(self):
        tuning = GenerationTuning()
        assert tuning.mode is ResponseMode.INSTANT
        assert tuning.temperature is None
        assert tuning.effective_reasoning() is None


# ---------------------------------------------------------------------------
# call_llm: tuning reaches stream_chat via the typed seam, not a stray dict
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_call_llm_passes_tuning_object_to_stream_chat(mock_session, user_id, conv_id):
    """The exact GenerationTuning built in chat_policy must reach the adapter
    unchanged, and no stray dict-splat keys accompany it — this is what
    would have caught the Google GenerateContentConfig hard-fail class of
    bug (its typed config rejects unknown keys)."""
    queue: asyncio.Queue = asyncio.Queue()
    captured: dict = {}

    async def recording_stream(messages, *, tuning=None, **opts):
        captured["tuning"] = tuning
        captured["opts"] = opts
        yield ChatChunk(content="ok", prompt_tokens=1, completion_tokens=1, finish_reason="stop")

    mock_client = MagicMock()
    mock_client.stream_chat = recording_stream

    tuning = GenerationTuning(mode=ResponseMode.THINKING, temperature=0.7)

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
            "tuning": tuning,
        }
        await call_llm(state)

    assert captured["tuning"] is tuning
    assert captured["tuning"].temperature == 0.7
    assert captured["tuning"].mode is ResponseMode.THINKING
    assert captured["opts"] == {}


@pytest.mark.asyncio
async def test_call_llm_defaults_to_plain_tuning_when_state_omits_it(mock_session, user_id, conv_id):
    """A caller that doesn't set state['tuning'] still gets a valid
    GenerationTuning(), not a crash — matches the old `temperature=None`
    default behavior for every pre-G-A1 call site not yet threading tuning."""
    queue: asyncio.Queue = asyncio.Queue()
    captured: dict = {}

    async def recording_stream(messages, *, tuning=None, **opts):
        captured["tuning"] = tuning
        yield ChatChunk(content="ok", finish_reason="stop")

    mock_client = MagicMock()
    mock_client.stream_chat = recording_stream

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
            # "tuning" deliberately omitted
        }
        await call_llm(state)

    assert captured["tuning"] == GenerationTuning()


@pytest.mark.asyncio
async def test_message_sent_audit_includes_mode_and_reasoning(mock_session, user_id, conv_id):
    queue: asyncio.Queue = asyncio.Queue()

    async def fake_stream(messages, *, tuning=None, **opts):
        yield ChatChunk(content="ok", finish_reason="stop")

    mock_client = MagicMock()
    mock_client.stream_chat = fake_stream

    with patch("app.agents.orchestrator.get_router") as mock_router, \
         patch("app.agents.orchestrator.audit_svc.log", new_callable=AsyncMock) as audit_log:
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
            "tuning": GenerationTuning(mode=ResponseMode.PRO),
        }
        await call_llm(state)

    sent_calls = [c.kwargs for c in audit_log.call_args_list if c.kwargs.get("action") == "message_sent"]
    assert len(sent_calls) == 1
    assert sent_calls[0]["details"]["mode"] == "pro"
    assert sent_calls[0]["details"]["reasoning"] == "high"


# ---------------------------------------------------------------------------
# emit_start: reasoning_unavailable notice + tuning stripped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_emit_start_notices_and_strips_unsupported_reasoning(user_id, conv_id):
    queue: asyncio.Queue = asyncio.Queue()
    mock_client = MagicMock()
    mock_client.supports_reasoning = False

    with patch("app.agents.orchestrator.get_router") as mock_router:
        mock_router.return_value.get.return_value = mock_client

        state: ChatState = {
            "session": AsyncMock(),
            "user_id": user_id,
            "resolved_conversation_id": conv_id,
            "user_content": "hello",
            "model_code": "perplexity-sonar",
            "chunk_queue": queue,
            "downgrade_to_local": False,
            "reasons": [],
            "history": [],
            "tuning": GenerationTuning(mode=ResponseMode.THINKING),
        }
        result = await emit_start(state)

    items = []
    while not queue.empty():
        items.append(json.loads(queue.get_nowait()))
    notice = next(i for i in items if i["type"] == "notice" and i["event"] == "reasoning_unavailable")
    assert notice["model"] == "perplexity-sonar"
    assert notice["requested"] == "medium"

    assert "tuning" in result
    assert result["tuning"].effective_reasoning() is None


@pytest.mark.asyncio
async def test_emit_start_no_notice_when_model_supports_reasoning(user_id, conv_id):
    queue: asyncio.Queue = asyncio.Queue()
    mock_client = MagicMock()
    mock_client.supports_reasoning = True

    with patch("app.agents.orchestrator.get_router") as mock_router:
        mock_router.return_value.get.return_value = mock_client

        state: ChatState = {
            "session": AsyncMock(),
            "user_id": user_id,
            "resolved_conversation_id": conv_id,
            "user_content": "hello",
            "model_code": "claude-sonnet-4",
            "chunk_queue": queue,
            "downgrade_to_local": False,
            "reasons": [],
            "history": [],
            "tuning": GenerationTuning(mode=ResponseMode.THINKING),
        }
        result = await emit_start(state)

    items = []
    while not queue.empty():
        items.append(json.loads(queue.get_nowait()))
    assert not any(i["type"] == "notice" and i["event"] == "reasoning_unavailable" for i in items)
    assert "tuning" not in result


@pytest.mark.asyncio
async def test_emit_start_no_notice_when_mode_is_instant(user_id, conv_id):
    """No reasoning requested at all -> no capability probe, no notice."""
    queue: asyncio.Queue = asyncio.Queue()
    mock_client = MagicMock()
    mock_client.supports_reasoning = False

    with patch("app.agents.orchestrator.get_router") as mock_router:
        mock_router.return_value.get.return_value = mock_client

        state: ChatState = {
            "session": AsyncMock(),
            "user_id": user_id,
            "resolved_conversation_id": conv_id,
            "user_content": "hello",
            "model_code": "perplexity-sonar",
            "chunk_queue": queue,
            "downgrade_to_local": False,
            "reasons": [],
            "history": [],
            "tuning": GenerationTuning(),  # INSTANT
        }
        result = await emit_start(state)

    items = []
    while not queue.empty():
        items.append(json.loads(queue.get_nowait()))
    assert not any(i["type"] == "notice" for i in items)
    assert "tuning" not in result


@pytest.mark.asyncio
async def test_emit_start_unregistered_model_does_not_crash(user_id, conv_id):
    """get_router().get() raising KeyError (client not registered) must not
    stop emit_start from finishing the turn — call_llm surfaces that failure
    on its own via the existing error-event path."""
    queue: asyncio.Queue = asyncio.Queue()

    with patch("app.agents.orchestrator.get_router") as mock_router:
        mock_router.return_value.get.side_effect = KeyError("no client")

        state: ChatState = {
            "session": AsyncMock(),
            "user_id": user_id,
            "resolved_conversation_id": conv_id,
            "user_content": "hello",
            "model_code": "unregistered-model",
            "chunk_queue": queue,
            "downgrade_to_local": False,
            "reasons": [],
            "history": [],
            "tuning": GenerationTuning(mode=ResponseMode.THINKING),
        }
        result = await emit_start(state)  # must not raise

    assert "tuning" not in result


# ---------------------------------------------------------------------------
# call_llm: one-shot reasoning_started notice
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_call_llm_emits_reasoning_started_once_on_first_thinking_chunk(mock_session, user_id, conv_id):
    queue: asyncio.Queue = asyncio.Queue()

    async def fake_stream(messages, *, tuning=None, **opts):
        yield ChatChunk(content="", metadata={"thinking": True})
        yield ChatChunk(content="", metadata={"thinking": True})  # must not re-notify
        yield ChatChunk(content="Answer", finish_reason="stop", prompt_tokens=5, completion_tokens=3)

    mock_client = MagicMock()
    mock_client.stream_chat = fake_stream

    with patch("app.agents.orchestrator.get_router") as mock_router:
        mock_router.return_value.get.return_value = mock_client

        state: ChatState = {
            "session": mock_session,
            "user_id": user_id,
            "resolved_conversation_id": conv_id,
            "user_content": "hello",
            "model_code": "claude-sonnet-4",
            "chunk_queue": queue,
            "downgrade_to_local": False,
            "reasons": [],
            "history": [],
            "tuning": GenerationTuning(mode=ResponseMode.THINKING),
        }
        await call_llm(state)

    items = []
    while not queue.empty():
        item = queue.get_nowait()
        if item is None:
            break
        items.append(json.loads(item))

    started = [i for i in items if i["type"] == "notice" and i["event"] == "reasoning_started"]
    assert len(started) == 1

    content = [i for i in items if i["type"] == "content"]
    assert len(content) == 1
    assert content[0]["delta"] == "Answer"


@pytest.mark.asyncio
async def test_call_llm_no_reasoning_started_without_thinking_chunks(mock_session, user_id, conv_id):
    queue: asyncio.Queue = asyncio.Queue()

    async def fake_stream(messages, *, tuning=None, **opts):
        yield ChatChunk(content="Answer", finish_reason="stop")

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
            "tuning": GenerationTuning(),
        }
        await call_llm(state)

    items = []
    while not queue.empty():
        item = queue.get_nowait()
        if item is None:
            break
        items.append(json.loads(item))

    assert not any(i["type"] == "notice" and i["event"] == "reasoning_started" for i in items)
