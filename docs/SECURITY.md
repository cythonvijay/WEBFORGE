# WebForge Security & Verification Guide (Phase 14)

This document records the WebForge security architecture, threat model, confirmed findings from the Phase 14 security review, implemented remediations, repeatable local and CI verification procedures, and known environment limitations.

---

## 1. Authentication and Authorization Model

### Password Hashing
- User passwords are hashed using **Argon2id** (`argon2-cffi` `PasswordHasher`).
- Raw passwords are validated for length (`8..128` characters) before hashing and are never logged, persisted in plaintext, or returned in API responses.
- Verification (`verify_password` in `backend/app/security.py`) catches `VerifyMismatchError`, `InvalidHashError`, and `VerificationError` to ensure corrupted or legacy hashes fail closed (`False`) without unhandled server exceptions.

### Session & Token Architecture
- **Access Tokens (`wf_access`)**: Short-lived (`15` minutes default) HS256 JWTs signed with `settings.secret_key`. Each token includes `sub` (User ID), `typ: "access"`, `iat` (issued-at), and `exp` (expiration). `decode_access_token` explicitly enforces `algorithms=["HS256"]`, required claims (`sub`, `exp`, `typ`), and `typ == "access"`.
- **Refresh Tokens (`wf_refresh`)**: High-entropy opaque tokens (`secrets.token_urlsafe(32)`) stored only as **SHA-256 hashes** (`token_hash`) in the `refresh_tokens` table with a 7-day TTL (`refresh_token_days`).
- **Refresh Token Rotation & Reuse Detection**:
  - `POST /api/auth/refresh` queries the `RefreshToken` row using `.with_for_update()` (row-level lock on PostgreSQL, serialized transaction on SQLite) to prevent concurrent refresh race conditions.
  - Every successful refresh marks the presented token `revoked = True` and issues a new refresh token.
  - Presenting an already-revoked or expired refresh token returns `401 Invalid refresh token`.
- **Logout (`POST /api/auth/logout`)**: Revokes the active refresh token in the database and clears both `wf_access` and `wf_refresh` cookies using identical `Path`, `SameSite`, `HttpOnly`, and `Secure` attributes (`_cookie_kwargs()`).

---

## 2. Project Ownership Enforcement & Isolation

- Every project-scoped endpoint resolves project access through `get_owned_project` (`backend/app/api.py`), which requires an authenticated `User` (`get_current_user`) and verifies `Project.owner_id == user.id`.
- Unauthenticated requests to any `/api/projects/*` route return `401 Not authenticated`.
- Requests for a non-existent project ID receive `404 Project not found`; requests for a project owned by another user receive `403 Forbidden`. No project metadata, Project Brain pointer, or artifact content is leaked across users.
- Every artifact-version route (`/api/projects/{project_id}/research/*`, `/strategy`, `/prd`, `/ux/*`, `/design-system/*`, `/prototype/*`, `/architecture/*`, `/security-verification`) scopes queries by **both** `project_id` and `version_id` (or `finding_id`), preventing cross-project insecure direct object reference (IDOR) attacks.

---

## 3. Session, Cookie, CSRF, and CORS Strategy

### Cookie Security Attributes
- Both `wf_access` and `wf_refresh` cookies are set with:
  - `HttpOnly=True` (inaccessible to `document.cookie` / XSS payloads)
  - `SameSite="lax"`
  - `Secure=settings.cookie_secure` (`False` for local HTTP development; must be set to `True` in HTTPS production via `COOKIE_SECURE=true`)
  - `Path="/"`

### Cross-Site Request Forgery (CSRF) Protection
Because WebForge supports cookie-authenticated requests alongside `Authorization: Bearer` headers, `SecurityMiddleware` (`backend/app/security.py`) enforces defense-in-depth CSRF protections on all state-changing `/api/*` requests (`POST`, `PUT`, `PATCH`, `DELETE`):
1. **Fetch Metadata check**: Requests carrying `Sec-Fetch-Site: cross-site` are immediately rejected with `403 Cross-site requests are forbidden`.
2. **Origin / Referer validation**: If an `Origin` or `Referer` header is present, its scheme + host (+ port) must match either an allowed origin in `settings.cors_origins` or the server's own `Host` header (`http://<Host>` / `https://<Host>`). `Origin: null` (sandboxed iframe / data URI) is explicitly rejected (`403 Untrusted request origin`).
3. **Simple-Request Content-Type block**: HTML `<form>` CSRF media types (`application/x-www-form-urlencoded`, `multipart/form-data`, `text/plain`) are rejected with `403 Unsupported content type for state-changing API request`. State-changing API payloads must use `application/json`.

### Defensive HTTP Security Headers
Every HTTP response from the backend includes:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()`
- `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` (automatically enabled when `COOKIE_SECURE=true` or request scheme is `https`)
- `Cache-Control: no-store` on `/api/*` responses.

---

## 4. Input Validation, Payload Limits, and Browser Hardening

- **Request Body Cap**: `SecurityMiddleware` enforces `MAX_REQUEST_BODY_BYTES = 512 KiB` (`524,288` bytes) via both `Content-Length` header inspection and streaming chunk counting, returning `413 Request body too large` before oversized payloads reach route handlers.
- **Strict Schema Validation**: All request schemas (`Credentials`, `ProjectIn`, `ProjectPatch`, `SectionIn`, `StageIn`, `IntakeIn`, and Phase 4–13 artifact schemas) enforce `ConfigDict(extra="forbid")` and explicit string/list bounds.
- **Project Brain Section Bounds**: `validate_brain_section_payload` enforces a `64 KiB` serialized JSON limit, maximum nesting depth of `8`, maximum list length of `200`, and maximum string length of `10,000` characters.
- **Frontend XSS & URL Sanitization**:
  - Zero occurrences of `dangerouslySetInnerHTML`, `eval()`, or `new Function()` across all 62 frontend TypeScript/React modules.
  - External URLs rendered in `FindingCard.tsx` and `Panels.tsx` are sanitized through `safeHttpUrl()` (`frontend/src/lib/utils.ts`), which parses URLs via `new URL()` and allows only `http:` and `https:` protocols (blocking `javascript:`, `data:`, and `vbscript:` URIs).

---

## 5. AI-Provider Secret Handling & Prompt-Injection Defense

- **Server-Side Key Isolation**: `GEMINI_API_KEY` is read exclusively by `backend/app/config.py` on the server. Frontend code (`frontend/src/`) never references or bundles AI provider keys.
- **Sanitized Error Handling**: Provider exceptions (`ProviderError`) are mapped to structured error categories (`missing_api_key`, `rate_limited`, `timeout`, `malformed_output`, `network_error`, `invalid_request`, `provider_unavailable`, `unknown`) with safe user-facing messages. Raw upstream exception strings (`str(e)`) are never returned to clients.
- **Untrusted AI Output Validation**: All AI-generated outputs (Intake, Research, Strategy, PRD, UX, Design System, Prototype, Architecture) are parsed as JSON and validated against strict Pydantic schemas before persistence.
- **Lifecycle & Authorization Invariance**: AI outputs are pure data proposals stored as `draft` versions. An AI response can never self-approve an artifact, alter `owner_id`, bypass upstream readiness gates, or execute system commands.

---

## 6. Artifact Approval, Integrity, and Lifecycle Guarantees

1. **Exact-Hash Approval Binding**: Every artifact computes a canonical SHA-256 `content_hash` over its normalized content. Approval (`POST .../approve`) requires `ApproveRequest.content_hash` to match the stored artifact's `content_hash`; any modification changes the hash and rejects stale approval requests with `409 content_hash mismatch`.
2. **Copy-on-Write Immutability**: Approved and superseded versions cannot be mutated or deleted in place (`409 Conflict`). Creating a new draft clones the approved version into a new `version_number` with `status="draft"`.
3. **Transitive Upstream Invalidation**: Opening a new upstream draft or approving a new upstream version cascades `is_stale = True` (`stale_reason`) down the dependency chain (`Research -> Strategy -> PRD -> UX -> Design System -> Prototype -> Architecture`) and reopens affected lifecycle stages.
4. **Server-Side Stage Completion Guards**: `PUT /api/projects/{project_id}/stages/{stage}` enforces real completion checks across every governed stage (`research`, `strategy`, `requirements`, `ux`, `design`, `prototype`, `architecture`, `testing`, `security`). Manually flipping a stage to `complete` without an non-stale approved artifact (and verified hash provenance + security controls for `testing` and `security`) is rejected with `400 Bad Request`.
5. **Phase 14 Verification Engine (`GET /api/projects/{project_id}/security-verification`)**: Evaluates 5 deterministic project integrity and security controls (`CHK-BRAIN-INTEGRITY`, `CHK-HASH-PROVENANCE`, `CHK-UPSTREAM-GATES`, `CHK-PRD-TRACEABILITY`, `CHK-SECURITY-ARCHITECTURE`), recomputing SHA-256 content hashes across all approved artifacts to detect out-of-band tampering.

---

## 7. Prioritized Security Findings Inventory (Phase 14 Audit)

| ID | Severity | Finding | Evidence | Remediation | Verification |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SEC-01** | **High** (Confirmed Defect — Fixed) | Manual stage status endpoint (`PUT /api/projects/{id}/stages/{stage}`) allowed marking `ux` and `design` complete when 0 artifacts existed (`if ux_rows:` / `if d_rows:` skipped validation when empty) and had no completion guards for `testing` or `security`. | `backend/app/api.py` lines 407–424 previously guarded `ux_stage_completion_check` and `design_stage_completion_check` behind non-empty row checks and omitted `testing`/`security`. | Unconditionally enforce `ux_stage_completion_check`, `design_stage_completion_check`, `architecture_stage_completion_check`, `testing_stage_completion_check`, and `security_stage_completion_check` in `update_stage`. | `backend/tests/test_security_phase14.py::test_stage_completion_guards_and_phase14_verification` |
| **SEC-02** | **High** (Confirmed Defect — Fixed) | Cookie-authenticated state-changing endpoints (`POST`, `PUT`, `PATCH`, `DELETE`) lacked server-side CSRF / Origin / Referer / `Sec-Fetch-Site` / form `Content-Type` validation. | `backend/app/api.py` accepted `wf_access` and `wf_refresh` cookies on mutating routes without checking `Origin`, `Referer`, `Sec-Fetch-Site`, or blocking `application/x-www-form-urlencoded` requests. | Added `SecurityMiddleware` (`backend/app/security.py`) blocking `Sec-Fetch-Site: cross-site`, untrusted `Origin`/`Referer` headers, `Origin: null`, and HTML form Content-Types on mutating `/api/*` routes. | `backend/tests/test_security_phase14.py::test_security_headers_csrf_and_cookie_hardening` |
| **SEC-03** | **Medium** (Confirmed Defect — Fixed) | Core request models (`Credentials`, `ProjectIn`, `ProjectPatch`, `SectionIn`, `StageIn`, `IntakeIn`) lacked `extra="forbid"`, `Project.description` and `ProjectBrain` sections were unbounded, and no global request body size limit existed. | `backend/app/api.py` lines 69–104 allowed arbitrary extra JSON fields, unlimited `description` strings, and arbitrarily large `SectionIn.data` dicts. | Added `MAX_REQUEST_BODY_BYTES` (512 KiB `413` guard), `ConfigDict(extra="forbid")`, `description` max length (`5,000`), `validate_brain_section_payload` (64 KiB, depth <= 8), and bounded `IntakeResult` in `backend/app/brain.py`. | `backend/tests/test_security_phase14.py::test_input_validation_and_payload_hardening` |
| **SEC-04** | **Medium** (Confirmed Defect — Fixed) | API responses lacked defensive HTTP security headers (`X-Content-Type-Options`, `X-Frame-Options`, `CSP`, `Referrer-Policy`, `Cache-Control: no-store`), and `POST /api/auth/logout` deleted cookies without matching security flags. | `backend/app/main.py` only registered `CORSMiddleware`; `backend/app/api.py` called `response.delete_cookie(ACCESS_COOKIE)` without `_cookie_kwargs()`. | Added defensive security headers in `SecurityMiddleware` and passed `**_cookie_kwargs()` to `delete_cookie` in `logout`. | `backend/tests/test_security_phase14.py::test_security_headers_csrf_and_cookie_hardening` |
| **SEC-05** | **Medium** (Confirmed Defect — Fixed) | `POST /api/projects/{id}/intake` leaked raw upstream exception details (`str(e)`) when `ProviderError.category == "unknown"`, `verify_password` did not catch `InvalidHashError`, and JWT decoding did not explicitly require `iat`/`sub`/`exp`/`typ` keys. | `backend/app/api.py` line 444 interpolated `str(e)` into HTTP 502 detail; `backend/app/security.py` only caught `VerifyMismatchError`. | Sanitized unknown provider error responses in `intake`, caught `InvalidHashError`/`VerificationError` in `verify_password`, and enforced `require=["exp", "sub", "typ"]` + `iat` in `decode_access_token`. | `backend/tests/test_security_phase14.py::test_ai_provider_secret_isolation_and_error_sanitization` & `test_jwt_and_password_edge_cases` |
| **SEC-06** | **Medium** (Confirmed Defect — Fixed) | Refresh token rotation (`POST /api/auth/refresh`) queried `RefreshToken` without `.with_for_update()` row locking or token length validation. | `backend/app/api.py` line 213 queried `RefreshToken` without locking, leaving a concurrent refresh window under PostgreSQL. | Added `.with_for_update()` on `RefreshToken` lookup and rejected refresh tokens exceeding 256 characters. | `backend/tests/test_postgres.py::test_postgres_concurrent_refresh_token_rotation` |
| **SEC-07** | **Low** (Hardening — Fixed) | `backend/Dockerfile` ran the container process as `root`, and frontend external citation links (`FindingCard.tsx`, `Panels.tsx`) rendered `href={s.url}` without client-side URL protocol filtering. | `backend/Dockerfile` had no `USER` directive; `FindingCard.tsx` and `Panels.tsx` passed `s.url` directly to `<a href=...>`. | Added non-root `webforge` user in `backend/Dockerfile` and added `safeHttpUrl()` in `frontend/src/lib/utils.ts`, `FindingCard.tsx`, and `Panels.tsx`. | `frontend/src/test/security_phase14.test.tsx` & `verify_phase14.py` |

---

## 8. Local Verification Commands & Procedures

Run the consolidated Phase 14 verification runner from the repository root:

```bash
make verify-phase14
# or directly:
python3 backend/scripts/verify_phase14.py
```

The runner distinguishes **`PASSED`**, **`FAILED`**, **`SKIPPED`**, **`BLOCKED BY ENVIRONMENT`**, **`NOT RUN`**, and **`NOT APPLICABLE`**, and never converts a blocked check into a pass.

### Individual Verification Commands
- **Backend Unit, Integration & Security Regression Suite (SQLite)**:
  ```bash
  cd backend && pytest -q
  ```
- **Alembic Migration Upgrade/Downgrade Round-Trip (`0001..0007`)**:
  ```bash
  cd backend && DATABASE_URL=sqlite:///./migration_check.db alembic upgrade head && DATABASE_URL=sqlite:///./migration_check.db alembic downgrade base
  ```
- **PostgreSQL Integration & Concurrency Suite** (requires running PostgreSQL instance):
  ```bash
  cd backend && POSTGRES_TEST_URL=postgresql+psycopg://webforge:webforge@localhost:5432/webforge_test pytest -m postgres -v
  ```
- **Frontend Unit Tests, Typecheck & Production Build** (requires Node.js + npm):
  ```bash
  cd frontend && npm test && npm run typecheck && npm run build
  ```
- **Dependency Vulnerability Audit** (requires `pip-audit` and `npm audit` with network access):
  ```bash
  pip-audit -r backend/requirements.txt
  cd frontend && npm audit --audit-level=high
  ```

---

## 9. Incident Response Basics for Exposed Credentials

1. **JWT Secret Key (`SECRET_KEY`) Compromise**:
   - Rotate `SECRET_KEY` immediately in environment configuration and restart backend instances (invalidates all active `wf_access` JWTs).
   - Revoke all active refresh tokens in PostgreSQL: `UPDATE refresh_tokens SET revoked = true WHERE revoked = false;`.
2. **AI Provider Key (`GEMINI_API_KEY`) Exposure**:
   - Immediately revoke the exposed key in Google AI Studio / Google Cloud Console, provision a replacement key with restricted API scope and quota limits, and update the server environment variable `GEMINI_API_KEY`.
3. **Database Credential Compromise**:
   - Rotate the PostgreSQL role password, restrict network ingress to private VPC subnets, and audit `artifact_versions` content hashes via `GET /api/projects/{id}/security-verification` (`CHK-HASH-PROVENANCE`) to verify no approved artifacts were tampered with.

---

## 10. Known Limitations & Unverified Controls in Sandbox Environment

- **PostgreSQL Concurrency Execution**: While PostgreSQL integration and concurrency tests (`backend/tests/test_postgres.py`, including concurrent approval locking and concurrent refresh token rotation with `SELECT ... FOR UPDATE`) are implemented, the verification sandbox does not run a live PostgreSQL daemon (`POSTGRES_TEST_URL` is unset), so those 8 tests are reported as **BLOCKED BY ENVIRONMENT** (and `skipped` in pytest).
- **Node.js / Vitest / TypeScript Execution**: The verification sandbox does not have `node` or `npm` installed, so frontend Vitest execution, `tsc --noEmit`, and `vite build` are reported as **BLOCKED BY ENVIRONMENT** and must be run in a local developer environment or CI runner with Node.js 20+.
- **Offline Vulnerability Database Access**: Outbound internet access is disabled in the verification sandbox, so live CVE database lookups via `pip-audit` / `npm audit` are **BLOCKED BY ENVIRONMENT**. Static dependency manifest pinning and secret scanning are verified locally.


---

## 11. Phase 15 Infrastructure, Container & CI/CD Security Controls

- **Fail-Fast Production Configuration (`backend/app/config.py`)**: `enforce_startup_settings()` refuses startup in `staging`/`production` if `JWT_SECRET` is `< 32` characters or uses a default/placeholder, if `DATABASE_URL` uses SQLite or a weak password, if `CORS_ORIGINS` contains `*` or non-HTTPS origins in `production`, or if `COOKIE_SECURE` is `false` in `production`.
- **Log Redaction (`backend/app/observability.py`)**: `RedactingFilter` automatically scrubs passwords, database connection strings, `GOOGLE_AI_API_KEY` (`AIza...`), JWTs, bearer tokens, and session cookies from all text and JSON logs.
- **Container Hardening (`backend/Dockerfile`, `frontend/Dockerfile`, `.dockerignore`)**:
  - Multi-stage builds keep compilers and build caches out of runtime images.
  - Backend runs as non-root `USER webforge` (`UID 10001`); frontend runs as unprivileged `USER nginx` (`UID 101`) on port `8080`.
  - `.dockerignore` files exclude `.env`, `.env.*`, `.git`, local databases, and test artifacts from build contexts.
- **CI Security (`.github/workflows/ci.yml`)**: Enforces `permissions: contents: read`, separates mandatory checks from the manual-only `optional-live-ai` workflow_dispatch job, and scans frontend `dist/` bundles to ensure no server secrets are embedded.

## Phase 16 — SEO, Analytics & Privacy Security Controls

- **Private & Authenticated Route Indexability Guard (`SEO`)**: Non-public routes (`authenticated`, `private_user_data`, `transactional`, `admin`) are blocked at schema validation time from using `robots_index="index"` or `include_in_sitemap=True`, and are automatically excluded from generated `/sitemap.xml` previews and disallowed in `/robots.txt`.
- **Analytics Sensitive Property Denylist & Opt-In Consent (`Analytics`)**: Event properties matching sensitive credential, token, financial, or raw PII patterns (`password`, `access_token`, `refresh_token`, `jwt`, `api_key`, `secret`, `card_number`, `cvv`, `ssn`, `raw_email`, `phone_number`, etc.) are rejected with `422 Unprocessable Entity`. Non-essential event categories (`analytics`, `functional`, `marketing`) require `requires_opt_in=True`, and `third_party_transmission_enabled` must be `False`.
- **Approval Hash & Provenance Verification (`CHK-HASH-PROVENANCE`)**: `backend/app/security_verification.py` verifies `OptimizationArtifact` SHA-256 content hashes alongside Research, Strategy, PRD, UX, Design, and Architecture artifacts.

## Phase 17 Documentation & Export Security Controls
- **Authentication & Cross-Project Ownership Isolation**: All `/api/projects/{project_id}/documentation*` endpoints enforce `current_user` (`401`) and `owned(project_id)` (`404` on non-owner access, preventing export ID enumeration).
- **Archive Path & Extension Hardening (`validate_safe_archive_path`)**: Rejects path traversal (`..`), leading slashes, backslashes, drive letters, hidden dotfiles (`.env`, `.git`), control characters, duplicate archive paths, and any file extension outside `.md` and `.json`.
- **Pre-Export Secret & Internal Path Scanning (`scan_export_for_secrets`)**: Blocks export generation (`422`) if any generated document or `MANIFEST.json` matches API keys (`AIza...`, `sk-...`, `ghp_...`, `AKIA...`), PEM private keys, database URLs with credentials, `JWT_SECRET` assignments, Argon2 password hashes, or internal server paths (`/working_dir/...`).
- **Cryptographic Provenance & Tamper Detection**: Recomputes SHA-256 content hashes for all 14 source artifacts and verifies `manifest_sha256` and `bundle_sha256` before serving any download (`409` on integrity mismatch), with `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, and `Cache-Control: no-store`.
