"""Per-request context variables set by RequestContextMiddleware."""
from contextvars import ContextVar

request_ip: ContextVar[str | None] = ContextVar("request_ip", default=None)
request_ua: ContextVar[str | None] = ContextVar("request_ua", default=None)
