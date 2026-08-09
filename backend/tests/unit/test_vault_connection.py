"""Unit tests for app.services.vault_connection — pure-function coverage.

upsert_connection()/get_connection() need a real DB session (SQLAlchemy
commit/refresh semantics don't mock cleanly) — their round-trip is covered
by backend/tests/integration/test_vault_connection.py instead. This file
covers decrypt_token() and build_authenticated_url(), which don't touch
the DB at all, following the "mock everything DB, run real logic for
everything else" pattern in test_vault_sync.py.
"""
from __future__ import annotations

import uuid

import pytest
from cryptography.exceptions import InvalidTag

import app.crypto as crypto
from app.models.vault import VaultConnection
from app.services.vault_connection import build_authenticated_url, decrypt_token


def _conn_with_token(token: str) -> VaultConnection:
    ct, nonce, tag, key_version = crypto.encrypt(token)
    return VaultConnection(
        id=uuid.uuid4(),
        git_url="https://github.com/org/vault.git",
        branch="main",
        bot_email="obsidian-bot@service.local",
        templates_dirname="templates",
        token_ciphertext=ct,
        token_nonce=nonce,
        token_tag=tag,
        token_key_version=key_version,
    )


class TestDecryptToken:
    def test_round_trip(self):
        conn = _conn_with_token("github_pat_super-secret-token")
        assert decrypt_token(conn) == "github_pat_super-secret-token"

    def test_stored_ciphertext_is_not_plaintext(self):
        conn = _conn_with_token("github_pat_super-secret-token")
        assert conn.token_ciphertext != b"github_pat_super-secret-token"
        assert b"github_pat_super-secret-token" not in conn.token_ciphertext

    def test_no_token_columns_returns_none(self):
        conn = VaultConnection(
            id=uuid.uuid4(),
            git_url="https://github.com/org/vault.git",
            branch="main",
            bot_email="obsidian-bot@service.local",
            templates_dirname="templates",
        )
        assert decrypt_token(conn) is None

    def test_tampered_ciphertext_raises(self):
        conn = _conn_with_token("secret")
        conn.token_ciphertext = bytes([conn.token_ciphertext[0] ^ 0xFF]) + conn.token_ciphertext[1:]
        with pytest.raises(InvalidTag):
            decrypt_token(conn)


class TestBuildAuthenticatedUrl:
    def test_injects_token_into_netloc(self):
        url = build_authenticated_url("https://github.com/org/vault.git", "abc123")
        assert url == "https://abc123@github.com/org/vault.git"

    def test_no_token_leaves_url_unchanged(self):
        url = build_authenticated_url("https://github.com/org/vault.git", None)
        assert url == "https://github.com/org/vault.git"

    def test_empty_token_leaves_url_unchanged(self):
        url = build_authenticated_url("https://github.com/org/vault.git", "")
        assert url == "https://github.com/org/vault.git"

    def test_preserves_explicit_port(self):
        url = build_authenticated_url("https://git.internal:8443/org/vault.git", "tok")
        assert url == "https://tok@git.internal:8443/org/vault.git"
