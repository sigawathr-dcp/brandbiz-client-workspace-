"""Seed a demo Client Workspace end to end (Phase 5, D21/D22).

Creates everything needed to click through the funnel once at an event:
  1. A "demo" workspace with a sensible per-seat + pooled token budget.
  2. The "client-workspaces" department, granted Perplexity so
     POST /client/research works for any redeemed seat (D19 — additive over
     role; client seats stay role=L1).
  3. A sanitized rate card (global rows, workspace_id=NULL) so
     POST /client/plan/draft has something real to price against — ATTENTION:
     replace the numbers below with Brandbiz's actual sanitized rate card
     before the event; these are placeholders shaped like the design mockup's
     line items, not real prices.
  4. A น้อง brandbiz Agent, scoped to the workspace via assign_agent() (forces
     visibility="public" so client seats can see it).
  5. One invite, printed as a ready-to-use /try/<token> link.

Idempotent on workspace slug: re-running with the same slug reuses the
existing workspace and agent, and only mints a fresh invite.

Run from inside the backend-api container:
    docker compose exec backend-api python scripts/seed_client_demo.py

Deliberately NOT seeded here: case-study documents. Run this script first,
then scripts/seed_case_studies.py to generate, upload, and attach the case
library to the agent seeded here — see that script's docstring.
POST /client/cases only ever surfaces files actually attached that way.
"""

import asyncio
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import engine
from app.llm.router import LOCAL_MODEL_CODE, PERPLEXITY_MODEL_CODE
from app.models.model_catalog import ModelCatalog
from app.models.permission import DepartmentModelPermission
from app.models.rate_card import RateCardItem
from app.models.user import User
from app.models.workspace import Workspace
from app.services import workspace as workspace_svc
from app.services.agent import create_agent

_SESSION = async_sessionmaker(engine, expire_on_commit=False)

WORKSPACE_SLUG = "brandbiz-demo"
WORKSPACE_NAME = "Brandbiz Demo — Common Grounds Co."
SEED_ADMIN_EMAIL = "demo-seeder@brandbiz.seed"

# Placeholder rate card — shaped like the design mockup's budget table.
# REPLACE with the real sanitized Brandbiz rate card before the event; a
# hallucinated line is bad, but a real-looking placeholder price is worse.
_RATE_CARD = [
    {"section": "1.2", "code": "brand-audit-workshop", "label": "Brand audit & positioning workshop", "unit": "project", "unit_price": "85000.00"},
    {"section": "2.1", "code": "identity-refresh-retail", "label": "Identity refresh + retail bag system", "unit": "project", "unit_price": "120000.00"},
    {"section": "2.6", "code": "layout-signage-kit", "label": "Weekday layout & signage kit (per branch)", "unit": "branch", "unit_price": "60000.00"},
    {"section": "3.4", "code": "content-production", "label": "Content production, 12 assets/month", "unit": "month", "unit_price": "72000.00"},
    {"section": "4.1", "code": "paid-social-min", "label": "Paid social — minimum monthly spend", "unit": "month", "unit_price": "80000.00"},
    {"section": "5.2", "code": "measurement-review", "label": "Measurement & monthly review", "unit": "engagement", "unit_price": "60000.00"},
]


async def _get_or_create_seed_admin(session) -> User:
    result = await session.execute(select(User).where(User.google_email == SEED_ADMIN_EMAIL))
    user = result.scalar_one_or_none()
    if user is not None:
        return user
    user = User(
        google_email=SEED_ADMIN_EMAIL,
        display_name="Demo Seeder",
        role="ADMIN",
        is_active=True,
        consent_acknowledged_at=datetime.now(timezone.utc),
    )
    session.add(user)
    await session.flush()
    print(f"  Created seed admin: {SEED_ADMIN_EMAIL}")
    return user


async def _get_or_create_workspace(session, admin: User):
    existing = (await session.execute(
        select(Workspace).where(Workspace.slug == WORKSPACE_SLUG)
    )).scalar_one_or_none()
    if existing is not None:
        print(f"  Existing workspace: {existing.name} ({existing.id})")
        return existing

    ws = await workspace_svc.create_workspace(
        session,
        name=WORKSPACE_NAME,
        slug=WORKSPACE_SLUG,
        kind="demo",
        # Per-seat monthly ceiling — generous for a demo, still a real cap.
        monthly_token_limit=500_000,
        # Pooled cap across every seat this workspace ever mints — the
        # event cost-control backstop (Rule 5 in PolicyEngine.decide()).
        token_budget_limit=3_000_000,
        contact_name="Ploy Suwannarat",
        contact_email="ploy@commongrounds.example",
    )
    print(f"  Created workspace: {ws.name} ({ws.id})")
    return ws


async def _grant_perplexity_to_client_department(session) -> None:
    dept = await workspace_svc._ensure_client_department(session)
    model = (await session.execute(
        select(ModelCatalog).where(ModelCatalog.code == PERPLEXITY_MODEL_CODE)
    )).scalar_one_or_none()
    if model is None:
        print(f"  WARNING: model_catalog has no row for {PERPLEXITY_MODEL_CODE!r} — "
              f"POST /client/research will downgrade to local until this is fixed.")
        return
    existing = (await session.execute(
        select(DepartmentModelPermission).where(
            DepartmentModelPermission.department_id == dept.id,
            DepartmentModelPermission.model_id == model.id,
        )
    )).scalar_one_or_none()
    if existing is not None:
        print(f"  Existing grant: {dept.code} -> {PERPLEXITY_MODEL_CODE}")
        return
    session.add(DepartmentModelPermission(department_id=dept.id, model_id=model.id))
    print(f"  Granted: {dept.code} -> {PERPLEXITY_MODEL_CODE}")


async def _seed_rate_card(session) -> None:
    for item in _RATE_CARD:
        existing = (await session.execute(
            select(RateCardItem).where(
                RateCardItem.code == item["code"], RateCardItem.workspace_id.is_(None)
            )
        )).scalar_one_or_none()
        if existing is not None:
            print(f"  SKIP rate card item {item['code']!r}")
            continue
        session.add(RateCardItem(
            workspace_id=None,
            section=item["section"],
            code=item["code"],
            label=item["label"],
            unit=item["unit"],
            unit_price=Decimal(item["unit_price"]),
            currency="THB",
            active=True,
        ))
        print(f"  OK rate card item {item['code']!r}")


async def _get_or_create_agent(session, admin: User, workspace):
    existing = await workspace_svc.get_workspace_agent(session, workspace.id)
    if existing is not None:
        print(f"  Existing agent: {existing.name} ({existing.id})")
        return existing

    agent = await create_agent(
        session=session,
        user=admin,
        name="น้อง brandbiz",
        provider="local",
        model=LOCAL_MODEL_CODE,  # upgrade via /agent/{id}/edit for real plan-drafting quality
        description="Brandbiz brand strategist — client-facing intake, research, and plan drafting.",
        instructions=(
            'คุณคือ "น้อง brandbiz" ที่ปรึกษาแบรนด์ของ Brandbiz พูดจาสุภาพ เป็นกันเอง ถามทีละคำถาม\n'
            "ห้ามเดาราคา — ใช้เฉพาะตัวเลขจาก rate card ที่แนบมาเท่านั้น "
            "งานที่ไม่มีแถวใน rate card ให้บอกว่าต้องให้ผู้เชี่ยวชาญประเมินราคา"
        ),
        capabilities={"web_search": True, "image_gen": False},
        creativity_level=30,
        visibility="public",
        status="published",
        category="Sales",
    )
    await workspace_svc.assign_agent(session, workspace_id=workspace.id, agent_id=agent.id, admin_id=admin.id)
    print(f"  Created + assigned agent: {agent.name} ({agent.id})")
    return agent


async def main() -> None:
    async with _SESSION() as session:
        print("--- Seed admin ---")
        admin = await _get_or_create_seed_admin(session)
        await session.commit()

        print("\n--- Workspace ---")
        workspace = await _get_or_create_workspace(session, admin)
        await session.commit()

        print("\n--- Department permission (Perplexity, D19) ---")
        await _grant_perplexity_to_client_department(session)
        await session.commit()

        print("\n--- Rate card (PLACEHOLDER — replace before the event) ---")
        await _seed_rate_card(session)
        await session.commit()

        print("\n--- Agent ---")
        await _get_or_create_agent(session, admin, workspace)
        await session.commit()

        print("\n--- Invite ---")
        invite, raw_token = await workspace_svc.create_invite(
            session, workspace_id=workspace.id, created_by=admin.id, expires_in_hours=24 * 14,
        )
        print(f"  Invite minted (expires {invite.expires_at.isoformat()}):")
        print(f"\n  /try/{raw_token}\n")
        print("  Open that path on the frontend (e.g. http://localhost:3000/try/{token}) to redeem it.")

    print("\nDone. Remember: run scripts/seed_case_studies.py to load the case library (see module docstring),")
    print("and replace the placeholder rate card with real sanitized numbers before the event.")


if __name__ == "__main__":
    asyncio.run(main())
