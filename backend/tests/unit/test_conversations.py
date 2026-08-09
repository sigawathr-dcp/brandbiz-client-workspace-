"""Unit tests for GET /conversations (Search chats - title filtering).

Tests cover:
  - escape_like escapes %, _ and backslash
  - default call has no title filter and binds LIMIT 50
  - q applies an escaped ILIKE on title while keeping user_id scoping
  - blank q is ignored

`limit` bounds (ge=1, le=200) are enforced by FastAPI Query validation at the
HTTP layer, so they are not exercised by these direct-call unit tests.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


def _make_session():
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result
    return session


def _compiled(stmt) -> str:
    # Generic (dialect-less) compilation renders ILIKE as lower() LIKE lower(),
    # so assertions check for "like" rather than "ilike".
    return str(stmt.compile()).lower()


def test_escape_like():
    from app.routers.conversations import escape_like

    assert escape_like("50%_a\\b") == "50\\%\\_a\\\\b"
    assert escape_like("plain") == "plain"


@pytest.mark.asyncio
async def test_list_conversations_default_no_filter():
    from app.routers.conversations import list_conversations

    user = _make_user()
    session = _make_session()

    out = await list_conversations(user=user, session=session)

    assert out == []
    stmt = session.execute.call_args[0][0]
    compiled = _compiled(stmt)
    assert "like" not in compiled
    assert "limit" in compiled
    assert stmt.compile().params["param_1"] == 50


@pytest.mark.asyncio
async def test_list_conversations_q_applies_ilike_with_escaping():
    from app.routers.conversations import list_conversations

    user = _make_user()
    session = _make_session()

    await list_conversations(user=user, session=session, q="50%_done")

    stmt = session.execute.call_args[0][0]
    compiled = _compiled(stmt)
    assert "like" in compiled

    params = stmt.compile().params
    assert "%50\\%\\_done%" in params.values()
    assert user.id in params.values()  # user scoping preserved


@pytest.mark.asyncio
async def test_list_conversations_blank_q_ignored():
    from app.routers.conversations import list_conversations

    user = _make_user()
    session = _make_session()

    await list_conversations(user=user, session=session, q="   ")

    stmt = session.execute.call_args[0][0]
    assert "like" not in _compiled(stmt)
