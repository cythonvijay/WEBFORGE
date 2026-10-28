import json
import logging
import re
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import settings

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger("webforge.ai")


class ProviderNotConfigured(Exception):
    pass


class ProviderError(Exception):
    """Provider failure. `category` is a fixed, non-sensitive label; messages never contain credentials or response bodies."""

    def __init__(self, message: str, category: str = "unknown"):
        super().__init__(message)
        self.category = category


# Safe, operator-useful wording per category (shown in API errors and stored as the discovery `last_error`).
USER_MESSAGES = {
    "auth": "The AI provider rejected the configured credentials.",
    "model_not_found": "The configured AI model is not available to this key.",
    "quota": "The AI provider is rate-limiting requests. Try again later.",
    "timeout": "The AI provider timed out.",
    "network": "The AI provider could not be reached.",
    "upstream": "The AI provider is temporarily unavailable.",
    "blocked": "The AI provider declined to answer this request.",
    "precondition": "The AI provider needs billing enabled or is unavailable in this region.",
    "bad_request": "The AI provider rejected the request.",
    "malformed": "The AI response could not be used.",
}


def user_message(e: "ProviderError") -> str:
    return USER_MESSAGES.get(e.category, "The AI response could not be used.")


class AIProvider:
    async def generate(self, prompt: str) -> str:
        raise NotImplementedError

    async def generate_structured(self, prompt: str, schema: type[T]) -> T:
        text = await self.generate(
            f"{prompt}\n\nRespond with ONLY JSON matching this JSON Schema:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
        try:
            return schema.model_validate_json(text)
        except ValidationError as e:
            raise ProviderError(f"Model output failed validation: {e.error_count()} error(s)", "malformed") from None


GOOGLE_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_MODEL_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


def classify_http_error(status_code: int, body: Any) -> str:
    """Map a Google error response to a category using only the HTTP status and Google's documented `error.status` enum."""
    err = body.get("error") if isinstance(body, dict) else None
    status = str(err.get("status", "")) if isinstance(err, dict) else ""
    msg = str(err.get("message", "")).lower() if isinstance(err, dict) else ""
    if status in ("PERMISSION_DENIED", "UNAUTHENTICATED") or status_code in (401, 403):
        return "auth"
    if status_code == 400 and "api key" in msg:  # Google answers an invalid key with 400 INVALID_ARGUMENT
        return "auth"
    if status == "FAILED_PRECONDITION":
        return "precondition"
    if status == "NOT_FOUND" or status_code == 404:
        return "model_not_found"
    if status == "RESOURCE_EXHAUSTED" or status_code == 429:
        return "quota"
    if status == "DEADLINE_EXCEEDED" or status_code in (408, 504):
        return "timeout"
    if status_code >= 500:
        return "upstream"
    return "bad_request" if status_code == 400 else "unknown"


def extract_text(data: Any) -> str:
    """Pull the answer text from a generateContent response, or raise a categorized ProviderError."""
    if not isinstance(data, dict):
        raise ProviderError("Google AI request failed: malformed", "malformed")
    if (data.get("promptFeedback") or {}).get("blockReason"):
        raise ProviderError("Google AI request failed: blocked", "blocked")
    candidates = data.get("candidates") or []
    if not candidates or not isinstance(candidates[0], dict):
        raise ProviderError("Google AI request failed: malformed", "malformed")
    cand = candidates[0]
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
    if not text.strip():
        blocked = cand.get("finishReason") in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII")
        cat = "blocked" if blocked else "malformed"
        raise ProviderError(f"Google AI request failed: {cat}", cat)
    return text


def _fail(category: str, http_status: int | None = None) -> "ProviderError":
    logger.warning("google ai request failed category=%s http_status=%s", category, http_status)  # no content, no credentials
    return ProviderError(f"Google AI request failed: {category}", category)


class GoogleAIProvider(AIProvider):
    """Calls the Gemini REST API directly (no SDK). The key travels only in the x-goog-api-key header, to Google's fixed host.
    No automatic retries: Google advises against retrying 400/403, and retry policy belongs to the caller."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport  # tests only

    async def generate(self, prompt: str) -> str:
        key, model = settings.google_ai_api_key, settings.google_model
        if not key:
            raise ProviderNotConfigured("GOOGLE_AI_API_KEY is not set")
        if not _MODEL_RE.match(model or ""):
            raise ProviderNotConfigured("GOOGLE_MODEL is not set or invalid")
        body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(settings.google_timeout_seconds, connect=10), transport=self._transport) as c:
                r = await c.post(f"{GOOGLE_API_BASE}/models/{model}:generateContent", json=body, headers={"x-goog-api-key": key})
        except httpx.TimeoutException:
            raise _fail("timeout") from None
        except httpx.HTTPError:
            raise _fail("network") from None
        try:
            data = r.json()
        except ValueError:
            data = None
        if r.status_code != 200:
            raise _fail(classify_http_error(r.status_code, data), r.status_code)
        try:
            return extract_text(data)
        except ProviderError as e:
            raise _fail(e.category, r.status_code) from None


class _Unimplemented(AIProvider):
    name = ""

    async def generate(self, prompt: str) -> str:
        raise ProviderNotConfigured(f"{self.name} provider is not implemented yet")


class OpenAIProvider(_Unimplemented):
    name = "openai"


class AnthropicProvider(_Unimplemented):
    name = "anthropic"


class LocalProvider(_Unimplemented):
    name = "local"


PROVIDERS = {"google": GoogleAIProvider, "openai": OpenAIProvider,
             "anthropic": AnthropicProvider, "local": LocalProvider}


def get_provider() -> AIProvider:
    cls = PROVIDERS.get(settings.ai_provider)
    if not cls:
        raise ProviderNotConfigured(f"Unknown AI_PROVIDER '{settings.ai_provider}'")
    return cls()
