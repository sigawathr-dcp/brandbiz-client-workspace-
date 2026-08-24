"""Unit tests for prepare_chat(extra_context=...) and the history window.

extra_context is how a caller injects state the message thread never carried
— today the client workspace's current plan (app/services/plan.py::
build_plan_context, wired in app/routers/client.py::client_chat). Two things
must hold, and only one of them is about the prompt:

  1. it reaches the LLM as system context (PreparedChat.system_prompt);
  2. it joins the §7.6 classification payload, so injected client data raises
     the data tier and PolicyEngine gates the call on it — that is the whole
     reason this is a prepare_chat parameter and not a string the router
     staples on afterwards.

The history-window test pins the fix for a window that read the FIRST 20
messages instead of the last 20 — past message 20 a conversation stopped
moving, which is fatal for a workspace whose opening turns are the intake
script and draft_plan()'s prompt + raw JSON reply.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.classifier as classifier_module
from app.llm.router import LOCAL_MODEL_CODE
from app.services.chat_policy import (
    _HISTORY_LIMIT,
    _trim_to_char_budget,
    load_history_messages,
    prepare_chat,
)
from app.services.classifier import _compile_rules
from app.models.user import User


@pytest.fixture(autouse=True)
def seed_classifier():
    """Thai national ID → TIER_3, same rule test_chat_policy.py uses."""
    classifier_module._RULES = _compile_rules([
        SimpleNamespace(
            name="Thai National ID",
            pattern_type="regex",
            pattern=r"\d-\d{4}-\d{5}-\d{2}-\d",
            detected_tier="TIER_3_CONFIDENTIAL",
        )
    ])
    yield
    classifier_module._RULES = []


@pytest.fixture(autouse=True)
def no_skills(monkeypatch):
    monkeypatch.setattr(
        "app.services.chat_policy.skill_svc.get_enabled_skills", AsyncMock(return_value=[])
    )


def _make_user() -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.role = "L3"
    user.workspace_id = None
    return user


def _session(model_code: str = "claude-sonnet-4") -> AsyncMock:
    """New conversation (no Conversation SELECT), empty history, and an
    active external model for every later lookup.

    Positional side_effect lists are brittle here — prepare_chat's execute
    count varies with the branch taken (the new-conversation auto-title
    UPDATE, PolicyEngine's model lookup) — so the first two calls answer the
    history SELECTs (the chat window and the unfiltered §7.6 one, see
    chat_policy.load_history_messages) and everything after them answers as a
    model lookup.
    """
    msg_result = MagicMock()
    msg_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))

    model_result = MagicMock()
    model_result.scalar_one_or_none.return_value = MagicMock(is_active=True, code=model_code)

    calls = {"n": 0}

    def _execute(*_args, **_kwargs):
        calls["n"] += 1
        return msg_result if calls["n"] <= 2 else model_result

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)
    session.add = MagicMock()
    return session


async def test_extra_context_reaches_the_system_prompt():
    plan_block = "[CURRENT PLAN]\nTitle: แผนกลยุทธ์แบรนด์ 2026\nTotal: 154000.00 THB"

    prepared = await prepare_chat(
        session=_session(),
        user=_make_user(),
        conversation_id=None,
        user_content="ทำไมงบเฟส 2 ถึงเท่านี้",
        requested_model=LOCAL_MODEL_CODE,
        extra_context=plan_block,
    )

    assert plan_block in prepared.system_prompt


async def test_extra_context_is_classified_and_can_downgrade_the_turn():
    """A plan block carrying TIER_3 data must downgrade the model exactly as
    the same text typed into the composer would. If injected context skipped
    classification, this call would stay on the external model."""
    prepared = await prepare_chat(
        session=_session("claude-sonnet-4"),
        user=_make_user(),
        conversation_id=None,
        user_content="สรุปแผนให้หน่อย",  # clean message — the plan block is the only TIER_3 source
        requested_model="claude-sonnet-4",
        extra_context="[CURRENT PLAN]\nContact ID 1-2345-67890-12-1",
    )

    assert prepared.downgrade_to_local is True
    assert prepared.model_code == LOCAL_MODEL_CODE


async def test_no_extra_context_leaves_the_system_prompt_untouched():
    prepared = await prepare_chat(
        session=_session(),
        user=_make_user(),
        conversation_id=None,
        user_content="สวัสดีครับ",
        requested_model=LOCAL_MODEL_CODE,
    )

    assert prepared.system_prompt == ""


async def test_history_window_keeps_the_last_messages_in_order():
    """The window must be the tail of the conversation, still oldest-first."""
    conv_id, user_id = uuid.uuid4(), uuid.uuid4()
    # 30 messages; the DB returns them newest-first (ORDER BY created_at DESC
    # LIMIT 20), i.e. rows 29..10.
    rows = [
        SimpleNamespace(
            role="user" if i % 2 == 0 else "assistant",
            content_ciphertext=b"", content_nonce=b"", content_tag=b"", key_version=1,
            _n=i,
        )
        for i in range(29, 9, -1)
    ]
    msg_result = MagicMock()
    msg_result.scalars.return_value = MagicMock(all=MagicMock(return_value=rows))
    conv_result = MagicMock()
    conv_result.scalar_one_or_none.return_value = MagicMock(id=conv_id)

    session = AsyncMock()
    # Conversation lookup, then the two history windows.
    session.execute = AsyncMock(side_effect=[conv_result, msg_result, msg_result])

    with patch("app.services.chat_policy.crypto.decrypt_message", side_effect=lambda *a, **k: "x"):
        resolved, history, _classification = await load_history_messages(
            session, user_id, conv_id
        )

    assert resolved == conv_id
    assert len(history) == _HISTORY_LIMIT
    # Oldest-first after the reverse: the DESC query's last row leads.
    assert [m["role"] for m in history] == [
        "user" if n % 2 == 0 else "assistant" for n in range(10, 30)
    ]


# ---------------------------------------------------------------------------
# Machine turns: shown to the tier scan, never to the model
# ---------------------------------------------------------------------------

def _step_filtered(stmt) -> bool:
    """True when `stmt` carries the engagement_step_id IS NULL predicate."""
    return "engagement_step_id IS NULL" in str(stmt)


async def test_generation_window_excludes_step_stamped_turns():
    """The window the model sees must ask for free-form turns only.

    services/plan.py::draft_plan writes its ~8k-char drafting prompt and the
    RAW JSON reply into the engagement's conversation, stamped with the 'plan'
    step. Leaving those in the LLM window made the last assistant turn the
    model saw a plan JSON blob, so asking for a plan in the chat box got a
    JSON blob back in the chat stream — with model-invented budget numbers
    that never went through rate_card.price().
    """
    conv_id, user_id = uuid.uuid4(), uuid.uuid4()

    chat_rows = [
        SimpleNamespace(
            role="user", content_ciphertext=b"chat",
            content_nonce=b"", content_tag=b"", key_version=1,
        )
    ]
    # Newest-first, as ORDER BY created_at DESC returns them: the machine turn
    # is the most recent one, which is exactly the case that used to poison the
    # model's window.
    all_rows = [
        SimpleNamespace(
            role="assistant", content_ciphertext=b"machine",
            content_nonce=b"", content_tag=b"", key_version=1,
        )
    ] + chat_rows

    def _result(rows):
        r = MagicMock()
        r.scalars.return_value = MagicMock(all=MagicMock(return_value=rows))
        return r

    conv_result = MagicMock()
    conv_result.scalar_one_or_none.return_value = MagicMock(id=conv_id)

    seen: list[bool] = []

    def _execute(stmt, *_a, **_k):
        if len(seen) == 0 and "conversations" in str(stmt).lower():
            return conv_result
        seen.append(_step_filtered(stmt))
        return _result(chat_rows if seen[-1] else all_rows)

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)

    with patch(
        "app.services.chat_policy.crypto.decrypt_message",
        side_effect=lambda ct, *a, **k: ct.decode(),
    ):
        _resolved, history, classification = await load_history_messages(
            session, user_id, conv_id
        )

    # Exactly one of the two windows filters on the step stamp...
    assert seen == [True, False]
    # ...and it is the one handed to the model.
    assert [m["content"] for m in history] == ["chat"]
    # The tier scan still sees the machine turn — what the model is not shown
    # can still not have been examined (§7.6).
    assert [m["content"] for m in classification] == ["chat", "machine"]


# ---------------------------------------------------------------------------
# History char budget — a message COUNT is not a bound on prompt size
# ---------------------------------------------------------------------------

def test_char_budget_drops_oldest_until_the_window_fits():
    """The client workspace writes machine-generated turns (draft_plan()'s ~8k
    prompt, its raw JSON reply) into the same thread, so 20 messages can be 70k+
    characters — past the local model's context window, at which point it has no
    budget left to answer and returns an empty reply."""
    history = [{"role": "user", "content": "x" * 10_000} for _ in range(5)]
    history[-1]["content"] = "the latest turn"

    trimmed = _trim_to_char_budget(history, budget=24_000)

    assert len(trimmed) == 3  # 10k + 10k + 15 chars fits; a 4th would not
    assert trimmed[-1]["content"] == "the latest turn"


def test_char_budget_leaves_a_short_conversation_alone():
    history = [{"role": "user", "content": "สวัสดี"}, {"role": "assistant", "content": "ครับ"}]
    assert _trim_to_char_budget(history, budget=24_000) == history


def test_char_budget_never_returns_an_empty_window():
    """One message longer than the whole budget is kept — an empty history
    would leave the model nothing to answer from."""
    history = [{"role": "user", "content": "x" * 50_000}]
    assert _trim_to_char_budget(history, budget=24_000) == history
