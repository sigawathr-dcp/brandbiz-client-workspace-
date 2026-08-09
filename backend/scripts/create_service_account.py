"""Create a service-account User + API key for machine-to-machine auth (n8n).

Run from inside the backend-api container AFTER `alembic upgrade head`:

    docker compose exec backend-api python scripts/create_service_account.py \
        --email n8n-bot@service.local \
        --role L4 \
        --name "n8n Gmail labelling bot"

The raw API key (gw_…) is printed once and never stored — save it immediately
in your n8n credential or a secrets manager.

Usage
-----
  --email   Service account email (must be unique; use a fake @service.local domain)
  --role    Role level L1-L6 or ADMIN (default: L4 — may use external models)
  --name    Human-readable key name shown in /admin/api-keys (default: "n8n service key")
  --revoke  Revoke ALL existing keys for this email before creating a new one

Example n8n configuration after running this script:
  OpenAI Chat Model → Credential → API Key: <paste the gw_… value>
  Base URL: https://api.decomplica.tech/v1
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import engine
from app.models.api_key import ApiKey, generate_key
from app.models.user import User

_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def main(email: str, role: str, key_name: str, revoke_existing: bool) -> None:
    VALID_ROLES = {"L1", "L2", "L3", "L4", "L5", "L6", "ADMIN"}
    if role not in VALID_ROLES:
        print(f"ERROR: role must be one of {VALID_ROLES}", file=sys.stderr)
        sys.exit(1)

    async with _session_factory() as session:
        # Upsert the service User
        result = await session.execute(select(User).where(User.google_email == email))
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                google_email=email,
                display_name=key_name,
                role=role,
                is_active=True,
                consent_acknowledged_at=datetime.now(timezone.utc),
            )
            session.add(user)
            await session.flush()
            print(f"Created service user: {user.id} ({email}, role={role})")
        else:
            user.role = role
            user.is_active = True
            # Ensure consent is set for new or existing accounts
            if user.consent_acknowledged_at is None:
                user.consent_acknowledged_at = datetime.now(timezone.utc)
            print(f"Existing service user: {user.id} ({email}) — updated role → {role}")

        # Optionally revoke existing keys
        if revoke_existing:
            existing_keys = (await session.execute(
                select(ApiKey).where(
                    ApiKey.service_user_id == user.id,
                    ApiKey.revoked_at.is_(None),
                )
            )).scalars().all()
            if existing_keys:
                now = datetime.now(timezone.utc)
                for key in existing_keys:
                    key.revoked_at = now
                print(f"Revoked {len(existing_keys)} existing key(s).")

        # Generate new key
        raw_secret, key_hash = generate_key()
        api_key = ApiKey(
            name=key_name,
            key_hash=key_hash,
            service_user_id=user.id,
        )
        session.add(api_key)
        await session.commit()

    print()
    print("=" * 60)
    print(f"  API Key ID  : {api_key.id}")
    print(f"  Key name    : {key_name}")
    print(f"  User email  : {email}")
    print(f"  Role        : {role}")
    print()
    print("  RAW SECRET (copy now — never shown again):")
    print(f"  {raw_secret}")
    print()
    print("  n8n OpenAI Chat Model configuration:")
    print("    Base URL : https://api.decomplica.tech/v1")
    print(f"    API Key  : {raw_secret}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", default="n8n-bot@service.local", help="Service account email")
    parser.add_argument("--role", default="L4", help="Role level (default: L4)")
    parser.add_argument("--name", default="n8n service key", help="Human-readable key label")
    parser.add_argument("--revoke", action="store_true", help="Revoke existing keys before creating new")
    args = parser.parse_args()

    asyncio.run(main(email=args.email, role=args.role, key_name=args.name, revoke_existing=args.revoke))
