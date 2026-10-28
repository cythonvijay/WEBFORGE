# AI provider (Google Gemini) — configuration, verification, errors

## How it works
`app/ai.py::GoogleAIProvider` calls the Gemini REST endpoint directly with `httpx` (no Google SDK is installed):
`POST https://generativelanguage.googleapis.com/v1beta/models/{GOOGLE_MODEL}:generateContent`, key in the `x-goog-api-key` header only (never in the URL or body), `generationConfig.responseMimeType = application/json`. The JSON Schema of the expected Pydantic model is appended to the prompt, and the reply is validated with `model_validate_json`; anything that fails is rejected, never repaired. Intake and discovery both go through `ai.get_provider()`. There are **no automatic retries** (Google advises against retrying 400/403; callers decide).

## Configuration
| Variable | Default | Notes |
|---|---|---|
| `GOOGLE_AI_API_KEY` | empty | Required. Set only in an **untracked** `.env` (repo root or `backend/`; `backend/.env` wins) or the real environment. Real environment variables override files. Never put it under `frontend/`. |
| `GOOGLE_MODEL` | `gemini-3.8-flash` | See "Model" below. |
| `GOOGLE_TIMEOUT_SECONDS` | 60 | Connect timeout is fixed at 10 s. |
| `AI_PROVIDER` | `google` | Only `google` is implemented. |
Before this change the backend never read `.env` outside Docker Compose; it now does (`extra="ignore"`, so unrelated keys like `POSTGRES_PASSWORD` are fine).

### Model
The previous default `gemini-2.5-flash` is risky for a new key: Google's changelog (2026-09-18) limits the 2.5 models to users who used them before and says new projects should use **3.5 Flash-Lite or 3.8 Flash**; the Google AI developer forum has 404 "no longer available" reports. The default is now `gemini-3.8-flash` (stable; structured outputs supported per its model page). `gemini-3.5-flash-lite` is the cheaper documented alternative. This is verified against documentation only — **not against a live key**. If your key gets `model_not_found`, run the check below: it lists the models your key can actually call.

## Verify safely (never prints the key)
    cd backend
    python -m app.provider_check                 # configuration only, no network
    python -m app.provider_check --live          # + one minimal real request, validated with Pydantic
    python -m app.provider_check --live --models # + list usable models (names only) on a model error
    python scripts/verify_real_provider.py       # full workflow on a TEMPORARY database:
                                                 # live request, intake, discovery, answer, Brain/provenance/revisions, next round, review
Exit codes: 0 ok · 1 not configured · 2 failed or Google unreachable. The script's output contains the test idea and generated question text (no credentials); `--report file.json` saves the table.

### Runbook for the live run
1. Create a **new** key in Google AI Studio (the key in the earlier shared zip is compromised; revoke it). Put `GOOGLE_AI_API_KEY=…` in `.env` (untracked). Do not paste it anywhere else.
2. `python -m app.provider_check --live` → expect `PASS`. Otherwise read the category (table below).
3. `python scripts/verify_real_provider.py` → expect every row `PASS` (the relevance row may say `REVIEW`: read the printed questions and judge them).
4. UI check (real stack: start PostgreSQL, `alembic upgrade head`, uvicorn, `npm run dev`): create a project, describe an idea, click **Analyze idea** and confirm the panel shows the same product name/problem/users/features that `GET /api/projects/{id}/brain` returns; open **Discovery**, answer a question, generate another round, review.

## Error categories (safe labels; response bodies are never echoed or logged)
| Category | Typical Google signal | Meaning / action |
|---|---|---|
| `auth` | 400 "API key not valid", 401/403, `PERMISSION_DENIED` | Wrong/revoked key or missing permission. Do not retry. |
| `model_not_found` | 404 `NOT_FOUND` | Model not available to this key → change `GOOGLE_MODEL` (see `--models`). |
| `quota` | 429 `RESOURCE_EXHAUSTED` | Rate/spend limit. Wait. |
| `precondition` | 400 `FAILED_PRECONDITION` | Billing needed or region unsupported. |
| `timeout` / `network` | timeout, 504 / connection failure | Retry later / check connectivity. |
| `upstream` | 500, 503 | Google-side problem. |
| `blocked` | `promptFeedback.blockReason`, finish reason SAFETY | Content declined. |
| `malformed` | non-JSON, empty, truncated, schema mismatch | Output rejected; nothing stored. |
| `bad_request` | other 400 | Request rejected. |
API behavior: unconfigured → 503; any provider failure → 502 with the safe message above; nothing is written to the Brain; discovery stores the message as `last_error` and stays retryable without duplicating sessions or questions. The category (not content) is logged by the `webforge.ai` logger.

## What the automated tests prove — and don't
`tests/test_google_provider.py` runs the real provider code against `tests/fake_google.py`, a fake Google at the HTTP level (documented request/response shapes and Google's documented error statuses). It proves request construction, header-only key, parsing, categorization, no leaks, no retries, config loading and the whole verification script. It **cannot** prove Google accepts your key, model, prompts or schema.

## Research uses the same provider
`app/research_api.py` calls `ai.get_provider().generate_structured(prompt, GeneratedResearch)`: same configuration, model, error categories and safe messages as intake and discovery (503 not configured, 502 with the category message; the row is marked `failed` and nothing else changes). The output schema is deliberately narrow (no sources, no citations, evidence limited to hypothesis / ai_suggestion / unsupported, no URLs); see docs/RESEARCH.md. Research quality with the real model has not been verified.
