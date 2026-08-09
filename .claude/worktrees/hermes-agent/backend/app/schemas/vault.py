"""Pydantic DTOs for the admin vault-connection + sync API (app/routers/vault.py)."""
from __future__ import annotations

import uuid
from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, field_validator


class VaultConfigOut(BaseModel):
    """Current vault connection config. Never includes the access token —
    only whether one is set."""
    git_url: str | None
    branch: str
    bot_email: str
    templates_dirname: str
    token_set: bool
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class VaultConfigIn(BaseModel):
    """Body for PUT /admin/vault/config.

    ``token``: omit/None to leave any existing token untouched (the
    frontend field is write-only and only submits a value when the admin
    retypes it); ``""`` explicitly clears a stored token; any other string
    replaces it.
    """
    git_url: str
    branch: str = "main"
    token: str | None = None
    bot_email: str | None = None
    templates_dirname: str | None = None

    @field_validator("git_url")
    @classmethod
    def _validate_git_url(cls, v: str) -> str:
        v = v.strip()
        parts = urlsplit(v)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("git_url must be an http(s) URL with a host, e.g. https://github.com/org/repo.git")
        return v


class VaultSyncTrigger(BaseModel):
    dry_run: bool = False


class VaultSyncRunOut(BaseModel):
    id: uuid.UUID
    status: str
    added: int
    updated: int
    deleted: int
    quarantined: int
    skipped: int
    failed_count: int
    error_text: str | None
    dry_run: bool
    started_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}
