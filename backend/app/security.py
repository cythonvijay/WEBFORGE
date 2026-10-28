import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .config import settings

_ph = PasswordHasher()
ACCESS_MINUTES = 15
REFRESH_DAYS = 7
MAX_REQUEST_BODY_BYTES = 512 * 1024  # 512 KiB request body ceiling
MAX_BRAIN_SECTION_BYTES = 64 * 1024  # 64 KiB per brain section edit
MAX_BRAIN_DEPTH = 8
MAX_BRAIN_LIST_LEN = 200
MAX_BRAIN_STR_LEN = 10_000

_FORM_CSRF_TYPES = (
    "application/x-www-form-urlencoded",
    "multipart/form-data",
    "text/plain",
)
_STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def hash_password(p: str) -> str:
    return _ph.hash(p)


def verify_password(h: str, p: str) -> bool:
    if not h or not p:
        return False
    try:
        return _ph.verify(h, p)
    except (VerifyMismatchError, InvalidHashError, VerificationError, ValueError):
        return False


def _secret() -> str:
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not set")
    return settings.jwt_secret


def create_access_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=ACCESS_MINUTES)
    return jwt.encode(
        {"sub": user_id, "iat": int(now.timestamp()), "exp": exp, "typ": "access"},
        _secret(),
        algorithm="HS256",
    )


def decode_access_token(token: str) -> str | None:
    if not token or not isinstance(token, str) or len(token) > 2048:
        return None
    try:
        data = jwt.decode(token, _secret(), algorithms=["HS256"])
        if not isinstance(data, dict) or not {"sub", "exp", "typ"}.issubset(data.keys()):
            return None
        sub = data.get("sub")
        if data.get("typ") != "access" or not isinstance(sub, str) or not (1 <= len(sub.strip()) <= 64):
            return None
        return sub
    except jwt.PyJWTError:
        return None


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def as_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes, PostgreSQL returns aware ones in the session timezone."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _check_nested_bounds(val: Any, depth: int = 0) -> None:
    if depth > MAX_BRAIN_DEPTH:
        raise ValueError(f"Payload nesting depth exceeds maximum allowed ({MAX_BRAIN_DEPTH}).")
    if isinstance(val, str):
        if len(val) > MAX_BRAIN_STR_LEN:
            raise ValueError(f"String value exceeds maximum length ({MAX_BRAIN_STR_LEN} characters).")
    elif isinstance(val, list):
        if len(val) > MAX_BRAIN_LIST_LEN:
            raise ValueError(f"List exceeds maximum length ({MAX_BRAIN_LIST_LEN} items).")
        for item in val:
            _check_nested_bounds(item, depth + 1)
    elif isinstance(val, dict):
        if len(val) > 100:
            raise ValueError("Object exceeds maximum allowed keys (100).")
        for k, v in val.items():
            if not isinstance(k, str) or len(k) > 120:
                raise ValueError("Object key must be a string of at most 120 characters.")
            _check_nested_bounds(v, depth + 1)


def validate_brain_section_payload(value: Any) -> None:
    """Enforce size, depth, and collection bounds on user-supplied ProjectBrain section edits."""
    _check_nested_bounds(value, 0)
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    if len(raw) > MAX_BRAIN_SECTION_BYTES:
        raise ValueError(f"Section payload exceeds maximum size ({MAX_BRAIN_SECTION_BYTES} bytes).")


def _normalize_origin(origin: str) -> str:
    u = urlsplit(origin.strip())
    if u.scheme.lower() not in ("http", "https") or not u.netloc:
        return ""
    return f"{u.scheme.lower()}://{u.netloc.lower()}"


def allowed_origins_for_request(host_header: str = "") -> set[str]:
    allowed = {
        _normalize_origin(o)
        for o in (settings.cors_origins or "").split(",")
        if o.strip()
    }
    allowed.discard("")
    host = host_header.strip().lower()
    if host:
        allowed.add(f"http://{host}")
        allowed.add(f"https://{host}")
    return allowed


class _BodyTooLarge(Exception):
    pass


class SecurityMiddleware:
    """ASGI security middleware enforcing:
    1. Request body size limit (MAX_REQUEST_BODY_BYTES = 512 KiB -> 413).
    2. CSRF protection on state-changing `/api/*` requests (Sec-Fetch-Site, Origin/Referer allowlist,
       and blocking HTML form simple-request Content-Types).
    3. Defensive HTTP security headers (nosniff, DENY framing, CSP, Referrer-Policy, Permissions-Policy, Cache-Control).
    """

    def __init__(self, app):
        self.app = app

    def _security_headers(self, path: str, method: str) -> list[tuple[bytes, bytes]]:
        headers = [
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"strict-origin-when-cross-origin"),
            (b"permissions-policy", b"geolocation=(), microphone=(), camera=()"),
            (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
        ]
        if path.startswith("/api") and method != "OPTIONS":
            headers.append((b"cache-control", b"no-store"))
        if settings.cookie_secure:
            headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
        return headers

    async def _send_json_error(self, send, status: int, detail: str, path: str, method: str) -> None:
        body = json.dumps({"detail": detail}).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
            *self._security_headers(path, method),
        ]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", ""))
        raw_headers = scope.get("headers") or []
        hdrs: dict[str, str] = {}
        for k, v in raw_headers:
            hdrs[k.decode("latin1").lower()] = v.decode("latin1")

        # 1. Check Content-Length against MAX_REQUEST_BODY_BYTES
        cl = hdrs.get("content-length")
        if cl:
            try:
                if int(cl) > MAX_REQUEST_BODY_BYTES:
                    await self._send_json_error(
                        send, 413, "Request body exceeds maximum allowed size (512 KiB).", path, method
                    )
                    return
            except ValueError:
                await self._send_json_error(send, 400, "Invalid Content-Length header.", path, method)
                return

        # 2. CSRF & Origin / Fetch-Metadata / Form Content-Type checks on state-changing API requests
        if method in _STATE_CHANGING_METHODS and path.startswith("/api"):
            sec_fetch_site = hdrs.get("sec-fetch-site", "").strip().lower()
            if sec_fetch_site == "cross-site":
                await self._send_json_error(
                    send,
                    403,
                    "Cross-site state-changing request blocked by CSRF protection.",
                    path,
                    method,
                )
                return

            allowed = allowed_origins_for_request(hdrs.get("host", ""))
            origin = hdrs.get("origin", "").strip()
            referer = hdrs.get("referer", "").strip()
            if origin:
                norm_origin = _normalize_origin(origin)
                if origin.lower() == "null" or not norm_origin or norm_origin not in allowed:
                    await self._send_json_error(
                        send,
                        403,
                        "Origin not allowed for state-changing request.",
                        path,
                        method,
                    )
                    return
            elif referer:
                norm_ref = _normalize_origin(referer)
                if not norm_ref or norm_ref not in allowed:
                    await self._send_json_error(
                        send,
                        403,
                        "Referer origin not allowed for state-changing request.",
                        path,
                        method,
                    )
                    return

            ctype = hdrs.get("content-type", "").strip().lower()
            if ctype and any(ctype.startswith(ft) for ft in _FORM_CSRF_TYPES):
                await self._send_json_error(
                    send,
                    403,
                    "Form-encoded content types are not allowed on JSON API endpoints (CSRF protection).",
                    path,
                    method,
                )
                return

        # 3. Enforce streamed body size limit & attach security headers on response
        received_bytes = 0
        response_started = False

        async def wrapped_receive():
            nonlocal received_bytes
            msg = await receive()
            if msg.get("type") == "http.request":
                chunk = msg.get("body", b"")
                received_bytes += len(chunk)
                if received_bytes > MAX_REQUEST_BODY_BYTES:
                    raise _BodyTooLarge()
            return msg

        async def wrapped_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
                existing = list(message.get("headers") or [])
                existing_keys = {k.lower() for k, _ in existing}
                for hk, hv in self._security_headers(path, method):
                    if hk not in existing_keys:
                        existing.append((hk, hv))
                message = {**message, "headers": existing}
            await send(message)

        try:
            await self.app(scope, wrapped_receive, wrapped_send)
        except _BodyTooLarge:
            if not response_started:
                await self._send_json_error(
                    send, 413, "Request body exceeds maximum allowed size (512 KiB).", path, method
                )
