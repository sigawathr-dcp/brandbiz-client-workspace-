"""Regression test for the personal/org knowledge-base scope leak.

Bug: when an AI Agent's attached knowledge files were passed to
rag_search.retrieve() as ``file_ids``, the personal/org access rule (R4)
was skipped entirely — any file ID in the list was retrievable regardless
of ownership or scope. A personal file attached to a public agent could
then be read by any user chatting with that agent.

Fix: file_ids narrows the corpus, it must never replace the R4 scope
filter — the two are ANDed together in rag_search._scope_filter().
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.models.user import User
from app.tools.rag_search import _scope_filter


def _make_user() -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    return user


class TestScopeFilter:
    def test_file_ids_still_enforce_personal_org_scope(self):
        """Regression: passing file_ids (agent knowledge) must still AND in
        the personal/org access rule, not bypass it."""
        user = _make_user()
        someone_elses_personal_file = uuid.uuid4()

        clause = _scope_filter(user, [someone_elses_personal_file])

        sql = str(clause)
        assert "files.id IN" in sql
        assert "files.user_id" in sql
        assert "files.scope" in sql

    def test_no_file_ids_uses_plain_access_filter(self):
        """Unchanged behaviour: without file_ids, the plain personal/org
        access filter applies and no id restriction is added."""
        user = _make_user()

        clause = _scope_filter(user, None)

        sql = str(clause)
        assert "files.id IN" not in sql
        assert "files.user_id" in sql
        assert "files.scope" in sql
