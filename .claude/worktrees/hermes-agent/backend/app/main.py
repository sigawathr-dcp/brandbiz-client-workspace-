import asyncio
import logging
import pathlib
from contextlib import asynccontextmanager

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.context import request_ip, request_ua
from app.db import engine, session_factory
from app.llm.base import LLMProviderError
from app.routers import (
    admin,
    agents as agents_router,
    auth,
    automations,
    chat,
    conversations,
    files as files_router,
    image as image_router,
    models as models_router,
    openai_compat,
    quota as quota_router,
    reveal,
    studio as studio_router,
    tasks as tasks_router,
    vault as vault_router,
)
import app.services.classifier as classifier

_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: run DB migrations, load classifier rules, ping LLM."""
    # Run pending Alembic migrations at startup so the DB is always in sync with
    # the code.  This is non-fatal: a migration failure logs the error but does
    # not prevent the server from starting.
    # env.py uses asyncio.run() internally, so we run this in a thread to
    # avoid a nested-event-loop error.
    try:
        _alembic_ini = pathlib.Path(__file__).parent.parent / "alembic.ini"
        alembic_cfg = AlembicConfig(str(_alembic_ini))
        await asyncio.to_thread(alembic_command.upgrade, alembic_cfg, "head")
        _log.info("Alembic: DB migrations applied (or already up to date).")
    except Exception:
        _log.exception("Alembic: failed to apply DB migrations at startup.")

    # Load data-classification rules into the in-process cache (§7.6).
    # A transient DB failure here is non-fatal: detect_tier() will default to
    # TIER_1_PUBLIC until the admin triggers a reload.
    try:
        async with session_factory() as session:
            count = await classifier.load_rules(session)
            _log.info("Classifier ready: %d rules loaded.", count)
    except Exception:
        _log.exception(
            "Failed to load classifier rules at startup — defaulting to TIER_1_PUBLIC."
        )

    # Ping the local model server at startup — non-fatal, mirrors the classifier pattern above.
    try:
        from app.llm.router import get_router, LOCAL_MODEL_CODE
        reachable = await get_router().get(LOCAL_MODEL_CODE).ping()
        if reachable:
            _log.info("Local model OK at %s (model: %s)", settings.llm_primary_url, settings.llm_primary_model)
        else:
            _log.warning(
                "Local model unreachable at %s — chat requests will fail until it is reachable.",
                settings.llm_primary_url,
            )
    except Exception:
        _log.exception("Error pinging local model at startup.")

    yield
    # (shutdown teardown goes here if needed)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Capture IP and User-Agent into context vars for the duration of each request."""

    async def dispatch(self, request: Request, call_next):
        forwarded_for = request.headers.get("X-Forwarded-For")
        ip = forwarded_for.split(",")[0].strip() if forwarded_for else (
            request.client.host if request.client else None
        )
        ua = request.headers.get("User-Agent")
        tok_ip = request_ip.set(ip)
        tok_ua = request_ua.set(ua)
        try:
            return await call_next(request)
        finally:
            request_ip.reset(tok_ip)
            request_ua.reset(tok_ua)


app = FastAPI(title="Brandbiz AI", version="0.1.0", lifespan=lifespan)

# RequestContextMiddleware must be outermost so context vars are set before
# any route handler or other middleware runs.
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(agents_router.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(files_router.router)
app.include_router(image_router.router)
app.include_router(models_router.router)
app.include_router(quota_router.router)
app.include_router(reveal.router)
app.include_router(admin.router)
# n8n integration — Part A (OpenAI-compat passthrough) and Part B (outbound triggers)
app.include_router(openai_compat.router)
app.include_router(automations.router)
app.include_router(studio_router.router)
app.include_router(tasks_router.router)
app.include_router(vault_router.router)


@app.exception_handler(LLMProviderError)
async def llm_provider_error_handler(request: Request, exc: LLMProviderError) -> JSONResponse:
    provider_code = exc.provider_code
    if provider_code == 429:
        status_code = 429
    elif provider_code in (401, 403):
        status_code = 502
    elif provider_code is not None and provider_code >= 500:
        status_code = 502
    else:
        status_code = 502
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


@app.get("/health")
async def health() -> dict[str, str]:
    db_status = "error"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        pass

    llm_status = "error"
    try:
        from app.llm.router import get_router, LOCAL_MODEL_CODE
        llm_status = "ok" if await get_router().get(LOCAL_MODEL_CODE).ping() else "error"
    except Exception:
        pass

    overall = "ok" if db_status == "ok" else "degraded"
    return {"status": overall, "db": db_status, "llm": llm_status}
