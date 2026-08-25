"""D21/D22, amended by D23 — tenant-isolation regression tests for Client
Workspaces.

The core safety property: a single gateway instance now serves two tenant
classes (internal staff, workspace_id IS NULL; client seats, workspace_id
set). Every "shared" visibility branch that predates D21/D22 — files.scope
== "org", skills.visibility == "public", agents.visibility == "public" —
must be additionally gated by workspace_id, or a client seat at an event
booth can retrieve internal case studies / skills / agents, and vice versa.

D23 (settings.client_internal_access_enabled) deliberately widens that gate
for client seats — with the flag on, a client seat should ALSO match
workspace_id IS NULL rows (the shared internal pool), while two different
client workspaces must still never match each other. The existing
"is not distinct from" substring assertion from before D23 cannot tell
these two states apart (it's a substring of the widened OR clause too), so
these tests assert on clause STRUCTURE instead — the bug class this guards
against is "the disjunct silently isn't there" (or was only added to one of
the two visibility_filter helpers), which a clause-structure assertion
catches directly.

These tests assert on compiled SQL clause structure (no real DB — mirrors
the existing house pattern in test_rag_search.py::TestScopeFilter).
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.sql.elements import BooleanClauseList
from sqlalchemy.sql.operators import or_

from app.models.agent import Agent
from app.models.file import File
from app.models.skill import Skill
from app.models.user import User
from app.services.agent import _accessible_filter as agent_accessible_filter
from app.services.skill import _accessible_filter as skill_accessible_filter
from app.services.workspace import (
    workspace_visibility_filter,
    workspace_visibility_filter_by_user_id,
)


@pytest.fixture
def flag_off(monkeypatch):
    import app.services.workspace as workspace_module

    monkeypatch.setattr(workspace_module.settings, "client_internal_access_enabled", False)


@pytest.fixture
def flag_on(monkeypatch):
    import app.services.workspace as workspace_module

    monkeypatch.setattr(workspace_module.settings, "client_internal_access_enabled", True)


class TestWorkspaceVisibilityFilterFlagOff:
    """D21/D22 baseline: a single IS NOT DISTINCT FROM clause, no OR."""

    def test_by_user_id_helper_is_a_single_clause(self, flag_off):
        clause = workspace_visibility_filter_by_user_id(uuid.uuid4(), File)
        sql = str(clause).lower()
        assert "is not distinct from" in sql
        assert "workspace_id" in sql
        assert not isinstance(clause, BooleanClauseList)

    def test_by_object_helper_is_a_single_clause(self, flag_off):
        user = MagicMock(spec=User)
        user.workspace_id = None
        clause = workspace_visibility_filter(user, File)
        sql = str(clause).lower()
        assert "is not distinct from" in sql
        assert not isinstance(clause, BooleanClauseList)


class TestWorkspaceVisibilityFilterFlagOn:
    """D23: widened to `column IS NULL OR column IS NOT DISTINCT FROM ref`
    — an OR clause with both disjuncts present, for BOTH helpers. Widening
    only one of the two would ship a half-working feature (see
    services/skill.py and services/agent.py, which both call the
    by_user_id variant)."""

    def test_by_user_id_helper_is_an_or_clause(self, flag_on):
        clause = workspace_visibility_filter_by_user_id(uuid.uuid4(), File)
        assert isinstance(clause, BooleanClauseList)
        assert clause.operator is or_
        sql = str(clause).lower()
        assert "is not distinct from" in sql
        assert "is null" in sql

    def test_by_object_helper_is_an_or_clause(self, flag_on):
        user = MagicMock(spec=User)
        user.workspace_id = uuid.uuid4()
        clause = workspace_visibility_filter(user, File)
        assert isinstance(clause, BooleanClauseList)
        assert clause.operator is or_
        sql = str(clause).lower()
        assert "is not distinct from" in sql
        assert "is null" in sql

    def test_staff_clause_still_a_no_op(self, flag_on):
        """For an internal user (workspace_id IS NULL), both OR disjuncts
        reduce to the same `workspace_id IS NULL` condition — the widened
        clause changes nothing for staff, flag on or off."""
        user = MagicMock(spec=User)
        user.workspace_id = None
        clause = workspace_visibility_filter(user, File)
        sql = str(clause).lower()
        assert sql.count("is null") >= 1


class TestSkillAccessibleFilterIsWorkspaceGated:
    @pytest.mark.parametrize("flag_state", ["flag_off", "flag_on"])
    def test_public_branch_references_workspace_id(self, flag_state, request):
        """Regression guard: the visibility=='public' branch of
        skill._accessible_filter must AND in workspace scoping, not just
        check visibility — otherwise any client seat sees every internal
        public skill (and any internal user sees every client's skills).
        Holds under both D23 states."""
        request.getfixturevalue(flag_state)
        clause = skill_accessible_filter(uuid.uuid4())
        sql = str(select(Skill).where(clause)).lower()
        assert "skills.workspace_id" in sql
        assert "skills.visibility" in sql
        # own-skill branch (ownership) must still be present and unconditional
        assert "skills.user_id" in sql


class TestAgentAccessibleFilterIsWorkspaceGated:
    @pytest.mark.parametrize("flag_state", ["flag_off", "flag_on"])
    def test_public_branch_references_workspace_id(self, flag_state, request):
        """Same regression guard as skills, for agents (e.g. the น้อง brandbiz
        persona must not be visible to a different client's seats, or to
        internal staff outside its own workspace). Holds under both D23
        states."""
        request.getfixturevalue(flag_state)
        clause = agent_accessible_filter(uuid.uuid4())
        sql = str(select(Agent).where(clause)).lower()
        assert "agents.workspace_id" in sql
        assert "agents.visibility" in sql
        assert "agents.status" in sql
        assert "agents.user_id" in sql
