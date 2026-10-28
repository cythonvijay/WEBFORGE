"""Phase 15 Observability, Structured Logging, Correlation IDs, Secret Redaction & Bounded Metrics."""
from __future__ import annotations

import contextvars
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import settings

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_VALID_REQ_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

_REDACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"((?:postgresql(?:\+psycopg)?|postgres|mysql|redis)://[^:\s/@]+:)([^@\s]+)(@)", re.I), r"\1[REDACTED]\3"),
    (re.compile(r"AIza[0-9A-Za-z_-]{20,}"), "[REDACTED_GOOGLE_API_KEY]"),
    (re.compile(r"sk-[0-9A-Za-z_-]{16,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"ghp_[0-9A-Za-z]{20,}"), "[REDACTED_GH_TOKEN]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), "[REDACTED_JWT]"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/-]+=*", re.I), r"\1[REDACTED_TOKEN]"),
    (re.compile(r"((?:access_token|refresh_token|wf_access|wf_refresh)\s*=\s*)[^;\s,\"']+", re.I), r"\1[REDACTED_COOKIE]"),
    (
        re.compile(
            r"""(["']?(?:password|password_hash|jwt_secret|secret_key|google_ai_api_key|api_key|access_token|refresh_token|authorization|cookie|set-cookie)["']?\s*[:=]\s*["']?)([^"',;\s}]+)(["']?)""",
            re.I,
        ),
        r"\1[REDACTED]\3",
    ),
]

SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "jwt_secret",
    "secret_key",
    "google_ai_api_key",
    "api_key",
    "access_token",
    "refresh_token",
    "wf_access",
    "wf_refresh",
    "authorization",
    "cookie",
    "set-cookie",
    "database_url",
}


def redact_sensitive_text(text: str) -> str:
    """Redact credentials, tokens, cookies, API keys, and connection passwords from a string."""
    if not text:
        return text
    out = str(text)
    for secret_val in (settings.jwt_secret, settings.google_ai_api_key):
        if secret_val and len(secret_val) >= 6 and secret_val in out:
            out = out.replace(secret_val, "[REDACTED_SECRET]")
    for pattern, replacement in _REDACTION_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact sensitive keys and string values in a dictionary."""
    sanitized: dict[str, Any] = {}
    for k, v in data.items():
        k_lower = str(k).lower().strip()
        if k_lower in SENSITIVE_KEYS:
            if k_lower == "database_url" and isinstance(v, str):
                sanitized[k] = redact_sensitive_text(v)
            else:
                sanitized[k] = "[REDACTED]"
        elif isinstance(v, dict):
            sanitized[k] = redact_mapping(v)
        elif isinstance(v, list):
            sanitized[k] = [
                redact_mapping(i) if isinstance(i, dict) else (redact_sensitive_text(i) if isinstance(i, str) else i)
                for i in v
            ]
        elif isinstance(v, str):
            sanitized[k] = redact_sensitive_text(v)
        else:
            sanitized[k] = v
    return sanitized


class RedactingFilter(logging.Filter):
    """Logging filter that attaches request_id and scrubs sensitive values from log messages and args."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(record, "request_id", None) or request_id_ctx.get("-")
        record.environment = settings.environment
        if isinstance(record.msg, str):
            record.msg = redact_sensitive_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = redact_mapping(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_sensitive_text(a) if isinstance(a, str) else a for a in record.args
                )
        return True


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON with correlation IDs and redacted messages."""

    def format(self, record: logging.LogRecord) -> str:
        msg = redact_sensitive_text(record.getMessage())
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", None) or request_id_ctx.get("-"),
            "environment": getattr(record, "environment", settings.environment),
            "message": msg,
        }
        for extra_key in ("method", "path", "status_code", "duration_ms", "event", "error_class"):
            val = getattr(record, extra_key, None)
            if val is not None:
                payload[extra_key] = val
        if record.exc_info:
            payload["exception"] = redact_sensitive_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


class RedactingTextFormatter(logging.Formatter):
    """Human-readable log formatter for local development that still enforces redaction and request IDs."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_ctx.get("-")
        return redact_sensitive_text(super().format(record))


def configure_logging(json_output: bool | None = None, level: str | None = None) -> logging.Logger:
    """Configure the `webforge` application logger with redaction and structured formatting."""
    use_json = settings.log_json if json_output is None else json_output
    lvl_name = (level or settings.log_level or "INFO").upper()
    lvl = getattr(logging, lvl_name, logging.INFO)

    logger = logging.getLogger("webforge")
    logger.setLevel(lvl)
    logger.handlers.clear()
    logger.filters.clear()
    logger.addFilter(RedactingFilter())
    logger.propagate = True

    handler = logging.StreamHandler()
    handler.setLevel(lvl)
    handler.addFilter(RedactingFilter())
    handler.setFormatter(StructuredJsonFormatter() if use_json else RedactingTextFormatter())
    logger.addHandler(handler)
    return logger


logger = configure_logging()


class MetricsRegistry:
    """Bounded in-memory platform operational counters (kept strictly separate from generated-product analytics)."""

    def __init__(self) -> None:
        self.started_at = time.monotonic()
        self.requests_total: int = 0
        self.status_classes: dict[str, int] = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0}
        self.errors_total: int = 0
        self.readiness_failures_total: int = 0
        self.slow_requests_total: int = 0
        self.total_duration_ms: float = 0.0
        self.max_duration_ms: float = 0.0
        self.duration_buckets_ms: dict[str, int] = {
            "le_50ms": 0,
            "le_200ms": 0,
            "le_500ms": 0,
            "gt_500ms": 0,
        }

    def record_request(self, status_code: int, duration_ms: float = 0.0) -> None:
        if not settings.enable_metrics:
            return
        self.requests_total += 1
        bucket = f"{status_code // 100}xx"
        if bucket in self.status_classes:
            self.status_classes[bucket] += 1
        if status_code >= 500:
            self.errors_total += 1
        d = max(0.0, float(duration_ms))
        self.total_duration_ms += d
        if d > self.max_duration_ms:
            self.max_duration_ms = d
        if d > getattr(settings, "slow_request_threshold_ms", 500.0):
            self.slow_requests_total += 1
        if d <= 50.0:
            self.duration_buckets_ms["le_50ms"] += 1
        elif d <= 200.0:
            self.duration_buckets_ms["le_200ms"] += 1
        elif d <= 500.0:
            self.duration_buckets_ms["le_500ms"] += 1
        else:
            self.duration_buckets_ms["gt_500ms"] += 1

    def record_readiness_failure(self) -> None:
        if settings.enable_metrics:
            self.readiness_failures_total += 1

    def snapshot(self) -> dict[str, Any]:
        avg_ms = round(self.total_duration_ms / self.requests_total, 2) if self.requests_total > 0 else 0.0
        err_rate = round(self.errors_total / self.requests_total, 4) if self.requests_total > 0 else 0.0
        return {
            "scope": "webforge_platform_operational_only",
            "uptime_seconds": round(max(0.0, time.monotonic() - self.started_at), 2),
            "requests_total": self.requests_total,
            "status_classes": dict(self.status_classes),
            "errors_total": self.errors_total,
            "error_rate": err_rate,
            "readiness_failures_total": self.readiness_failures_total,
            "slow_requests_total": self.slow_requests_total,
            "avg_duration_ms": avg_ms,
            "max_duration_ms": round(self.max_duration_ms, 2),
            "duration_buckets_ms": dict(self.duration_buckets_ms),
        }


metrics = MetricsRegistry()


def resolve_request_id(incoming: str | None) -> str:
    if incoming and _VALID_REQ_ID_RE.match(incoming.strip()):
        return incoming.strip()
    return uuid.uuid4().hex[:16]


class ObservabilityMiddleware:
    """ASGI middleware providing X-Request-ID correlation, structured request logging, and bounded metrics."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", ""))
        raw_headers = scope.get("headers") or []
        incoming_req_id: str | None = None
        for k, v in raw_headers:
            if k.decode("latin1").lower() == "x-request-id":
                incoming_req_id = v.decode("latin1")
                break

        req_id = resolve_request_id(incoming_req_id)
        token = request_id_ctx.set(req_id)
        start = time.perf_counter()
        status_code = 500

        async def wrapped_send(message):
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 200))
                headers = list(message.get("headers") or [])
                existing = {k.lower() for k, _ in headers}
                if b"x-request-id" not in existing:
                    headers.append((b"x-request-id", req_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            metrics.record_request(500, duration_ms)
            logger.error(
                f"Unhandled exception in {method} {path}: {type(exc).__name__}",
                extra={
                    "request_id": req_id,
                    "method": method,
                    "path": path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                    "error_class": type(exc).__name__,
                },
            )
            raise
        else:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            metrics.record_request(status_code, duration_ms)
            is_slow = duration_ms > getattr(settings, 'slow_request_threshold_ms', 500.0)
            lvl = logging.WARNING if (status_code >= 500 or is_slow) else logging.INFO
            logger.log(
                lvl,
                f"{method} {path} -> {status_code} ({duration_ms}ms)",
                extra={
                    "request_id": req_id,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
        finally:
            request_id_ctx.reset(token)
