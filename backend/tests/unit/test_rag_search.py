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

import pytest

from app.llm.embeddings import EmbeddingError
from app.models.user import User
from app.tools import rag_search as rag_search_module
from app.tools.rag_search import _scope_filter, retrieve


def _make_user(workspace_id: uuid.UUID | None = None) -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.workspace_id = workspace_id  # None = internal user — D21/D22
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


class TestWorkspaceVisibility:
    """D21/D22 — the org branch of _scope_filter must also be gated by
    workspace_id, for both internal and client-seat users. This is the
    safety floor for Client Workspaces sharing this instance with internal
    staff: without it, any signed-in client seat could retrieve every
    internal org file (and vice versa)."""

    def test_org_branch_is_workspace_gated(self):
        """The org branch must reference files.workspace_id, not just
        files.scope — regression guard for the D21/D22 tenant leak."""
        user = _make_user()

        clause = _scope_filter(user, None)

        sql = str(clause)
        assert "files.workspace_id" in sql

    def test_internal_and_client_users_both_produce_workspace_gated_clauses(self):
        """Both an internal user (workspace_id=None) and a client seat
        (workspace_id=<uuid>) must compile a workspace-gated org clause —
        i.e. the predicate is never silently dropped for either tenant class."""
        internal_user = _make_user(workspace_id=None)
        client_user = _make_user(workspace_id=uuid.uuid4())

        internal_sql = str(_scope_filter(internal_user, None))
        client_sql = str(_scope_filter(client_user, None))

        assert "files.workspace_id" in internal_sql
        assert "files.workspace_id" in client_sql


class TestLibraryScope:
    """ADR 0002 — the shared case corpus (files.scope = 'library') is a
    third disjunct of R4, readable by every tenant and independent of the
    D23 flag. Regression guard for the bug where every LINE-minted client
    workspace (its own tenant, D24) retrieved zero case chunks because the
    corpus was org-scoped to the demo workspace."""

    def test_library_disjunct_present_for_client_seat(self):
        client_user = _make_user(workspace_id=uuid.uuid4())

        sql = str(_scope_filter(client_user, None).compile(compile_kwargs={"literal_binds": True}))

        assert "files.scope = 'library'" in sql

    def test_library_disjunct_is_not_workspace_gated(self):
        """The library branch must stand alone — ANDing it with the tenant
        predicate would reintroduce the exact invisibility being fixed."""
        clause = _scope_filter(_make_user(workspace_id=uuid.uuid4()), None)
        # Top level is OR(personal, org, library); the library leaf must be a
        # bare comparison, not an AND wrapping a workspace_id predicate.
        leaves = [str(c.compile(compile_kwargs={"literal_binds": True})) for c in clause.clauses]
        library_leaves = [s for s in leaves if "'library'" in s]
        assert len(library_leaves) == 1
        assert "workspace_id" not in library_leaves[0]
        assert "AND" not in library_leaves[0]

    def test_file_ids_narrowing_still_admits_library_files(self):
        """Agent attachments AND the R4 filter (see TestScopeFilter); the
        library disjunct must survive that AND so attached corpus files stay
        retrievable."""
        sql = str(_scope_filter(_make_user(workspace_id=uuid.uuid4()), [uuid.uuid4()]).compile(compile_kwargs={"literal_binds": True}))

        assert "files.id IN" in sql
        assert "files.scope = 'library'" in sql


class TestEffectiveWorkspaceOverride:
    """Regression guard for B1 (preview mode returns zero case matches):
    a staff previewer has user.workspace_id IS NULL, so the org branch must
    be able to key off an explicit effective_workspace_id instead — see
    app/services/workspace.py::workspace_visibility_filter_by_workspace_id.
    """

    def test_none_override_is_unchanged_behaviour(self):
        """Every existing caller passes no override; the compiled clause
        must be identical to the pre-override behaviour."""
        user = _make_user(workspace_id=None)

        without_param = str(_scope_filter(user, None))
        with_none = str(_scope_filter(user, None, effective_workspace_id=None))

        assert without_param == with_none

    def test_override_replaces_users_own_workspace_as_tenant_key(self):
        """A staff previewer (user.workspace_id=None) with an explicit
        effective_workspace_id must compile a clause keyed to that
        workspace, not to the user's own (absent) tenant."""
        staff = _make_user(workspace_id=None)
        demo_ws = uuid.uuid4()

        own_clause = str(_scope_filter(staff, None))
        overridden_clause = str(_scope_filter(staff, None, effective_workspace_id=demo_ws))

        # Both reference files.workspace_id, but bind different parameters —
        # the override must not just reproduce the user's own-tenant clause.
        assert "files.workspace_id" in overridden_clause
        assert own_clause != overridden_clause or demo_ws is None


class TestRetrieveEvalKnobs:
    """max_distance / strict exist only for the offline eval harness — both
    must be no-ops for every production call site, which never sets them."""

    async def test_empty_query_short_circuits_before_strict_matters(self):
        # retrieve() returns [] on blank query before ever touching the
        # embedder, so strict=True must not raise here.
        user = _make_user()
        result = await retrieve(session=MagicMock(), user=user, query="   ", strict=True)
        assert result == []


class TestRetrieveStrictEmbedFailure:
    """Regression guard for case matching (app/routers/client.py's
    run_case_match): an embed-server outage must surface as EmbeddingError
    when strict=True, not degrade to an empty result. The default
    strict=False degradation (see TestRetrieveEvalKnobs above) is correct
    for chat, which falls back to a non-RAG answer — but silently returning
    [] for case matching is indistinguishable from "no case studies matched
    closely enough", which is a different, false, statement."""

    class _FailingEmbedder:
        async def embed_one(self, text: str) -> list[float]:
            raise EmbeddingError("embedding server unreachable")

    def _patch_failing_embedder(self, monkeypatch):
        monkeypatch.setattr(rag_search_module, "get_embedder", lambda: self._FailingEmbedder())

    async def test_strict_true_reraises_embedding_error(self, monkeypatch):
        self._patch_failing_embedder(monkeypatch)
        user = _make_user()

        with pytest.raises(EmbeddingError):
            await retrieve(session=MagicMock(), user=user, query="grab thailand app", strict=True)

    async def test_strict_false_degrades_to_empty_list(self, monkeypatch):
        self._patch_failing_embedder(monkeypatch)
        user = _make_user()

        result = await retrieve(session=MagicMock(), user=user, query="grab thailand app", strict=False)
        assert result == []
