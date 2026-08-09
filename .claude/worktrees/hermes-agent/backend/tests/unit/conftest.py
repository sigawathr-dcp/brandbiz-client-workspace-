import os
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Required env vars must be set before any app module loads Settings()
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleQ==")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

import importlib.util as _ilu

def _is_missing(top_level: str) -> bool:
    """Return True only when the top-level package is genuinely not installed."""
    return top_level not in sys.modules and _ilu.find_spec(top_level) is None

# asyncpg and redis are not installed in the local dev env; stub them at import time
for _mod in ("asyncpg", "redis", "redis.asyncio"):
    if _mod not in sys.modules:
        sys.modules[_mod] = ModuleType(_mod)

# openai / anthropic / httpx — absent in the minimal test venv but present in the
# full [external] extras venv.  Only stub when genuinely missing so we don't clobber
# the real SDK for tests that use it (test_openai_llm.py etc.).
if _is_missing("openai"):
    for _m in ("openai", "openai.types", "openai.types.chat"):
        sys.modules[_m] = ModuleType(_m)

if _is_missing("anthropic"):
    sys.modules["anthropic"] = ModuleType("anthropic")

if _is_missing("httpx"):
    sys.modules["httpx"] = ModuleType("httpx")

# google.genai — build the submodule hierarchy so `from google import genai` and
# `from google.genai import errors` resolve even when the real package is absent.
if _is_missing("google"):
    _google_mod = ModuleType("google")
    _google_genai_mod = ModuleType("google.genai")
    _google_genai_errors_mod = ModuleType("google.genai.errors")
    _google_genai_types_mod = ModuleType("google.genai.types")

    # Minimal APIError stub — matches the real SDK's constructor and __str__ shape
    # so `except genai_errors.APIError` and match="google 400" assertions work.
    class _APIError(Exception):
        def __init__(self, code=None, response_json=None):
            self.code = code
            msg = ""
            if isinstance(response_json, dict):
                msg = response_json.get("message", "")
            elif isinstance(response_json, str):
                msg = response_json
            super().__init__(f"google {code}: {msg}" if code else msg)

    # Minimal types stubs — accept any args/kwargs, store as attrs.
    class _GenericConfig:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class _Part:
        @staticmethod
        def from_bytes(data=None, mime_type=None):
            return _Part()

    # Minimal Client stub — exists so patch("app.llm.google.genai.Client") resolves.
    class _Client:
        def __init__(self, **kwargs):
            pass

    _google_genai_errors_mod.APIError = _APIError                                       # type: ignore[attr-defined]
    _google_genai_types_mod.GenerateContentConfig = _GenericConfig                      # type: ignore[attr-defined]
    _google_genai_types_mod.GenerateImagesConfig = _GenericConfig                       # type: ignore[attr-defined]
    _google_genai_types_mod.GenerateVideosConfig = _GenericConfig                       # type: ignore[attr-defined]
    _google_genai_types_mod.Part = _Part                                                # type: ignore[attr-defined]
    _google_genai_mod.Client = _Client                                                  # type: ignore[attr-defined]
    _google_genai_mod._IS_STUB = True                                                   # type: ignore[attr-defined]
    _google_mod.genai = _google_genai_mod                                  # type: ignore[attr-defined]
    _google_genai_mod.errors = _google_genai_errors_mod                    # type: ignore[attr-defined]
    _google_genai_mod.types = _google_genai_types_mod                      # type: ignore[attr-defined]
    sys.modules.update({
        "google": _google_mod,
        "google.genai": _google_genai_mod,
        "google.genai.errors": _google_genai_errors_mod,
        "google.genai.types": _google_genai_types_mod,
        "google.generativeai": ModuleType("google.generativeai"),
    })

# pgvector.sqlalchemy.Vector must be a real SQLAlchemy type so the ORM mapper
# can handle `Mapped[list[float]] = mapped_column(Vector(1024))` without error.
if "pgvector" not in sys.modules:
    from sqlalchemy import types as _sa_types

    class _VectorType(_sa_types.TypeDecorator):
        """Minimal pgvector Vector stub — stores as LargeBinary in unit tests."""
        impl = _sa_types.LargeBinary
        cache_ok = True
        def __init__(self, dim=None):
            super().__init__()
        def process_bind_param(self, value, dialect):
            return value
        def process_result_value(self, value, dialect):
            return value

    _pgvector = ModuleType("pgvector")
    _pgvector_sa = ModuleType("pgvector.sqlalchemy")
    _pgvector_sa.Vector = _VectorType
    sys.modules["pgvector"] = _pgvector
    sys.modules["pgvector.sqlalchemy"] = _pgvector_sa

# Stub app.db so the engine isn't created at import time (no real DB in unit tests).
# session_factory must be an async context manager callable (used by audit.py).
if "app.db" not in sys.modules:
    db_stub = ModuleType("app.db")
    db_stub.engine = MagicMock()
    db_stub.get_db = AsyncMock()

    # session_factory() must return an object that supports `async with ... as session:`
    _inner_session = AsyncMock()
    _inner_session.add = MagicMock()
    _inner_session.commit = AsyncMock()
    _fake_cm = MagicMock()
    _fake_cm.__aenter__ = AsyncMock(return_value=_inner_session)
    _fake_cm.__aexit__ = AsyncMock(return_value=False)
    db_stub.session_factory = MagicMock(return_value=_fake_cm)

    sys.modules["app.db"] = db_stub


@pytest.fixture(autouse=True)
def _silence_audit_celery():
    """Silence audit.log() in unit tests by patching the top-level coroutine.

    Yields the AsyncMock so tests can assert on call_args_list when needed.
    Calling convention: audit.log(**kwargs) → check mock.call_args_list[i].kwargs.
    """
    # Ensure the module is imported before patching — patch() requires the
    # dotted target to already exist in sys.modules when it is the first test.
    import app.services.audit  # noqa: F401
    with patch("app.services.audit.log", new_callable=AsyncMock) as mock_log:
        yield mock_log
