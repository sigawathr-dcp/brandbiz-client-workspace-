"""Regression guard for the case-matching "0 matches" vs "embed server is
down" ambiguity.

Bug: POST /client/cases called match_cases()/rag_search.retrieve() with
the default strict=False, so an embed-server outage was swallowed into an
empty result list — identical, from the frontend's point of view, to a
real "no case studies matched closely enough" run. Fix: run_case_match()
(app/routers/client.py) now passes strict=True, so an EmbeddingError
propagates out of match_cases() instead of being absorbed.

match_cases() embeds the query before ever touching `session` (see
rag_search.retrieve()'s ordering: embed first, SQL second), so a mocked
session that is never awaited is a faithful stand-in here — this test
never needs a real DB.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.llm.embeddings import EmbeddingError
from app.models.user import User
from app.services import case_match as case_match_svc
from app.tools import rag_search as rag_search_module


class _FailingEmbedder:
    async def embed_one(self, text: str) -> list[float]:
        raise EmbeddingError("embedding server unreachable")


def _make_user() -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.workspace_id = uuid.uuid4()
    return user


async def test_match_cases_strict_true_reraises_embedding_error(monkeypatch):
    monkeypatch.setattr(rag_search_module, "get_embedder", lambda: _FailingEmbedder())
    session = AsyncMock()
    user = _make_user()

    with pytest.raises(EmbeddingError):
        await case_match_svc.match_cases(
            session,
            user,
            fields={"industry": "Food & beverage / café"},
            agent_file_ids=None,
            effective_workspace_id=uuid.uuid4(),
            strict=True,
        )

    # The outage must be caught before any DB round trip — a mocked
    # session that silently returned MagicMocks for a real query would
    # mask the very bug this test guards against.
    session.execute.assert_not_called()


async def test_match_cases_default_strict_false_degrades_to_zero_results(monkeypatch):
    # Documents the deliberately different default for other callers
    # (e.g. chat's RAG context) that must degrade rather than fail.
    monkeypatch.setattr(rag_search_module, "get_embedder", lambda: _FailingEmbedder())
    session = AsyncMock()
    user = _make_user()

    run = await case_match_svc.match_cases(
        session,
        user,
        fields={"industry": "Food & beverage / café"},
        agent_file_ids=None,
        effective_workspace_id=uuid.uuid4(),
    )

    assert run.results == []
    assert run.chunks_retrieved == 0
