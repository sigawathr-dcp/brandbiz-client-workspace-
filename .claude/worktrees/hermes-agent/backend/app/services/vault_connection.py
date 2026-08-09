"""CRUD for the admin-configurable Obsidian vault connection.

Backs the self-service "connect your vault from the frontend" flow
(POST/GET /admin/vault/config in app/routers/vault.py). There is exactly
one live connection row at a time (a singleton by convention, not a DB
constraint — see PLAN.md risk note); ``get_connection`` always returns the
most recently updated row.

Security note (D13 deviation, explicitly user-approved — see
app/models/vault.py module docstring): the access token is the only field
here that is a secret. It is AES-256-GCM encrypted via app/crypto.py before
it ever reaches the database, and ``decrypt_token`` is the only way back to
plaintext — callers must not log or persist its return value anywhere else.
"""
from __future__ import annotations

import uuid
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.crypto as crypto
from app.config import get_settings
from app.models.vault import VaultConnection


async def get_connection(session: AsyncSession) -> VaultConnection | None:
    """Return the current vault connection, or None if never configured."""
    return (
        await session.execute(
            select(VaultConnection).order_by(VaultConnection.updated_at.desc()).limit(1)
        )
    ).scalars().first()


async def upsert_connection(
    session: AsyncSession,
    *,
    git_url: str,
    branch: str = "main",
    token: str | None,
    bot_email: str | None = None,
    templates_dirname: str | None = None,
    updated_by: uuid.UUID,
) -> VaultConnection:
    """Create or update the singleton connection row.

    ``token``: ``None`` leaves any existing token untouched (the frontend
    field is write-only and submits None when the admin didn't retype it);
    ``""`` explicitly clears a stored token; any other value is encrypted
    and replaces the stored token.
    """
    cfg = get_settings()
    conn = await get_connection(session)

    if conn is None:
        conn = VaultConnection(
            git_url=git_url,
            branch=branch,
            bot_email=bot_email or cfg.vault_bot_email,
            templates_dirname=templates_dirname or cfg.vault_templates_dirname,
            updated_by=updated_by,
        )
        session.add(conn)
    else:
        conn.git_url = git_url
        conn.branch = branch
        if bot_email is not None:
            conn.bot_email = bot_email
        if templates_dirname is not None:
            conn.templates_dirname = templates_dirname
        conn.updated_by = updated_by

    if token is not None:
        if token == "":
            conn.token_ciphertext = None
            conn.token_nonce = None
            conn.token_tag = None
            conn.token_key_version = None
        else:
            ct, nonce, tag, key_version = crypto.encrypt(token)
            conn.token_ciphertext = ct
            conn.token_nonce = nonce
            conn.token_tag = tag
            conn.token_key_version = key_version

    await session.commit()
    await session.refresh(conn)
    return conn


def decrypt_token(conn: VaultConnection) -> str | None:
    """Return the plaintext access token, or None if no token is stored."""
    if (
        conn.token_ciphertext is None
        or conn.token_nonce is None
        or conn.token_tag is None
        or conn.token_key_version is None
    ):
        return None
    return crypto.decrypt(
        conn.token_ciphertext, conn.token_nonce, conn.token_tag, conn.token_key_version
    )


def build_authenticated_url(git_url: str, token: str | None) -> str:
    """Inject ``token`` as userinfo into ``git_url`` for git clone/fetch.

    ``https://github.com/org/repo.git`` + token -> ``https://<token>@github.com/org/repo.git``.
    Returns ``git_url`` unchanged when ``token`` is falsy. In-memory only —
    callers must never log the returned URL (it embeds the raw secret).
    """
    if not token:
        return git_url
    parts = urlsplit(git_url)
    netloc = f"{token}@{parts.hostname or ''}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
