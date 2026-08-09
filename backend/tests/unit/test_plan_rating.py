"""Unit tests for plan_rating.py and the PlanRatingIn schema.

Real cross-tenant isolation and actual DB upsert-replace behavior are
covered by the Postgres integration suite
(tests/integration/test_client_isolation.py::TestPlanRatingIsolation) —
these tests exercise the two things that don't need a live database:
score-bound validation at the API boundary, and the upsert-vs-append
branch logic in plan_rating.upsert_rating() against a mocked session.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.services import plan_rating as plan_rating_svc


class TestPlanRatingInBounds:
    def test_score_out_of_range_high_rejected(self):
        from app.routers.client import PlanRatingIn

        with pytest.raises(ValidationError):
            PlanRatingIn(score=11)

    def test_score_out_of_range_low_rejected(self):
        from app.routers.client import PlanRatingIn

        with pytest.raises(ValidationError):
            PlanRatingIn(score=0)

    def test_score_in_range_accepted(self):
        from app.routers.client import PlanRatingIn

        body = PlanRatingIn(score=7)
        assert body.score == 7
        assert body.comment is None

    def test_comment_over_max_length_rejected(self):
        from app.routers.client import PlanRatingIn

        with pytest.raises(ValidationError):
            PlanRatingIn(score=5, comment="x" * 2001)


@pytest.mark.asyncio
class TestUpsertRating:
    async def test_upsert_replaces_existing_row_not_appends(self):
        plan_id = uuid.uuid4()
        user = MagicMock()
        user.id = uuid.uuid4()
        workspace_id = uuid.uuid4()

        existing = MagicMock()
        existing.score = 4
        existing.comment = "meh"

        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        session.execute = AsyncMock(return_value=result)

        with (
            patch.object(plan_rating_svc.plan_svc, "get_plan", new=AsyncMock(return_value=MagicMock())),
            patch.object(plan_rating_svc.audit_svc, "log", new=AsyncMock()),
        ):
            rating = await plan_rating_svc.upsert_rating(
                session, user, workspace_id, plan_id, score=9, comment="great now"
            )

        # Same object mutated, not a second row added.
        assert rating is existing
        assert rating.score == 9
        assert rating.comment == "great now"
        session.add.assert_not_called()
        session.commit.assert_awaited_once()

    async def test_upsert_creates_row_when_none_exists(self):
        plan_id = uuid.uuid4()
        user = MagicMock()
        user.id = uuid.uuid4()
        workspace_id = uuid.uuid4()

        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        with (
            patch.object(plan_rating_svc.plan_svc, "get_plan", new=AsyncMock(return_value=MagicMock())),
            patch.object(plan_rating_svc.audit_svc, "log", new=AsyncMock()),
        ):
            await plan_rating_svc.upsert_rating(
                session, user, workspace_id, plan_id, score=6, comment=None
            )

        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.score == 6
        assert added.plan_id == plan_id
        assert added.user_id == user.id

    async def test_upsert_404s_for_a_plan_the_caller_does_not_own(self):
        from fastapi import HTTPException

        plan_id = uuid.uuid4()
        user = MagicMock()
        user.id = uuid.uuid4()
        workspace_id = uuid.uuid4()
        session = AsyncMock()

        with patch.object(
            plan_rating_svc.plan_svc,
            "get_plan",
            new=AsyncMock(side_effect=HTTPException(status_code=404, detail="Plan not found")),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await plan_rating_svc.upsert_rating(
                    session, user, workspace_id, plan_id, score=5, comment=None
                )

        assert exc_info.value.status_code == 404
        session.execute.assert_not_called()


@pytest.mark.asyncio
class TestRatingsForPlanIds:
    async def test_empty_input_skips_the_query(self):
        session = AsyncMock()
        result = await plan_rating_svc.ratings_for_plan_ids(session, [])
        assert result == {}
        session.execute.assert_not_called()

    async def test_batches_into_a_single_query(self):
        plan_a, plan_b = uuid.uuid4(), uuid.uuid4()
        rating_a = MagicMock(plan_id=plan_a)
        rating_b = MagicMock(plan_id=plan_b)

        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [rating_a, rating_b]
        session.execute = AsyncMock(return_value=result)

        out = await plan_rating_svc.ratings_for_plan_ids(session, [plan_a, plan_b])

        assert out == {plan_a: rating_a, plan_b: rating_b}
        session.execute.assert_awaited_once()
