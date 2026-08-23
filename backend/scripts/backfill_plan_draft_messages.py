"""
scripts/backfill_plan_draft_messages.py

Stamp messages.engagement_step_id on plan-drafting turns written BEFORE
services/plan.py::draft_plan started setting it.

Why it matters: draft_plan shares the engagement's conversation, so every
draft persists its ~8k-char prompt and the model's raw JSON reply as two
ordinary message rows. GET /client/bootstrap's transcript replay
(routers/client.py::_chat_transcript) filters on `engagement_step_id IS
NULL` to keep that machinery out of the client's chat thread — but rows
written earlier all have NULL, so a client reloading /w sees the drafting
prompt and a wall of JSON in their conversation.

Message content is encrypted (§7.1), so legacy draft turns can only be
recognised by decrypting and matching plan.DRAFTING_PROMPT_OPENING. The
assistant reply that goes with a matched prompt is found by created_at:
call_llm persists both rows in one commit, and Postgres `now()` is
transaction start time, so the pair shares an exact timestamp.

Run inside the backend container. Use `-m`: running the file by path puts
/app/scripts on sys.path instead of /app, so `import app` fails.

    docker compose exec backend-api python -m scripts.backfill_plan_draft_messages --dry-run
    docker compose exec backend-api python -m scripts.backfill_plan_draft_messages

Idempotent: rows that already carry an engagement_step_id are never read or
touched, so re-running finds nothing left to do.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from sqlalchemy import select

from app import crypto
from app.db import session_factory
from app.models.conversation import Conversation
from app.models.engagement import Engagement, EngagementStep
from app.models.message import Message
from app.services.plan import DRAFTING_PROMPT_OPENING


async def _plan_step_by_conversation(session) -> dict[uuid.UUID, uuid.UUID]:
    """{conversation_id: plan engagement_step id} for every engagement."""
    rows = (
        await session.execute(
            select(Engagement.conversation_id, EngagementStep.id)
            .join(EngagementStep, EngagementStep.engagement_id == Engagement.id)
            .where(EngagementStep.step_key == "plan")
        )
    ).all()
    return {conv_id: step_id for conv_id, step_id in rows if conv_id is not None}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = parser.parse_args()

    tagged = 0
    conversations_touched = 0

    async with session_factory() as session:
        plan_steps = await _plan_step_by_conversation(session)
        print(f"{len(plan_steps)} engagement conversation(s)")

        for conversation_id, plan_step_id in plan_steps.items():
            kind = (
                await session.execute(
                    select(Conversation.kind).where(Conversation.id == conversation_id)
                )
            ).scalar_one_or_none()
            if kind != "client_workspace":
                continue

            rows = (
                await session.execute(
                    select(Message)
                    .where(
                        Message.conversation_id == conversation_id,
                        Message.engagement_step_id.is_(None),
                    )
                    .order_by(Message.created_at)
                )
            ).scalars().all()

            # Timestamps of the commits that wrote a drafting prompt. The
            # assistant reply in the same commit shares the timestamp exactly.
            draft_commits = set()
            for row in rows:
                if row.role != "user":
                    continue
                text = crypto.decrypt_message(
                    row.content_ciphertext, row.content_nonce, row.content_tag, row.key_version
                )
                if text.startswith(DRAFTING_PROMPT_OPENING):
                    draft_commits.add(row.created_at)

            if not draft_commits:
                continue

            hits = [r for r in rows if r.created_at in draft_commits]
            for row in hits:
                row.engagement_step_id = plan_step_id
            tagged += len(hits)
            conversations_touched += 1
            print(
                f"  conversation {conversation_id}: {len(draft_commits)} draft(s), "
                f"{len(hits)} message(s) tagged"
            )

        if args.dry_run:
            await session.rollback()
            print("\n--dry-run: rolled back")
        else:
            await session.commit()

    print(f"\nconversations={conversations_touched} messages_tagged={tagged}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
