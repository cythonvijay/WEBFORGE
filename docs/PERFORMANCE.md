# Phase 16 — Performance Budgets, Honest Measurement & Platform Optimization

## 1. Scope Separation

WebForge separates generated-product performance requirements from WebForge's own platform performance:

1. **Generated Product Performance Specification (`backend/app/optimization.py`, `backend/app/optimization_api.py`)**:
   - Defines Core Web Vitals budgets, per-route asset/bundle budgets (`PERF-ROUTE-N`), backend API latency/payload budgets (`PERF-API-N`), caching/lazy-loading rules, and recorded measurement evidence (`EVD-N`) for the **user's product**.
   - Persisted in `optimization_artifacts` (`area = 'performance'`) and referenced in `ProjectBrain.optimization_spec.performance`.
2. **WebForge Platform Performance & Caching (`backend/app/observability.py`, `frontend/nginx.conf`, `frontend/vite.config.ts`)**:
   - **Frontend Delivery**: `frontend/nginx.conf` serves fingerprinted `/assets/*` bundles with `Cache-Control: public, max-age=31536000, immutable`, `index.html` with `Cache-Control: no-cache, no-store, must-revalidate`, and `gzip on` compression.
   - **Backend Observability**: `ObservabilityMiddleware` in `backend/app/observability.py` records request latency histograms (`le_50ms`, `le_200ms`, `le_500ms`, `gt_500ms`), `avg_duration_ms`, `max_duration_ms`, and `slow_requests_total` (requests exceeding `SLOW_REQUEST_THRESHOLD_MS`, default `500.0ms`), logging a structured `WARNING` whenever a slow request occurs.

---

## 2. Performance Domain Model (`PerformanceContent`)

### 2.1 `CoreWebVitalsBudget`
- `lcp_ms`: Largest Contentful Paint budget in milliseconds (`500..4000`, Google "Good" threshold `<= 2500ms`)
- `inp_ms`: Interaction to Next Paint budget in milliseconds (`50..500`, Google "Good" threshold `<= 200ms`)
- `cls_max`: Cumulative Layout Shift maximum (`0.0..0.25`, Google "Good" threshold `<= 0.10`)
- `fcp_ms`: First Contentful Paint budget in milliseconds (`300..3000`, `<= lcp_ms`)
- `ttfb_ms`: Time to First Byte budget in milliseconds (`50..1800`)
- `measurement_posture`: `"target_budget_only" | "measured_observation"`

### 2.2 `RouteAssetBudgetSpec` (`PERF-ROUTE-1..N`)
Linked to approved Prototype/Wireframe screens (`screen_id`) and PRD requirements (`linked_requirement_ids`):
- `route_path`: unique normalized route path
- `max_js_kb` (`10..2000` KiB), `max_css_kb` (`5..500` KiB), `max_image_kb` (`10..5000` KiB), `max_initial_requests` (`1..60`)
- `caching_policy`: explicit HTTP caching directive for route assets and HTML document
- `lazy_loading_Boundary`: code-splitting and below-the-fold lazy-loading boundary
- `image_optimization_rule`: modern image format (`WebP`/`AVIF`), explicit `width`/`height` dimensions (preventing CLS), and priority hints

### 2.3 `BackendApiPerformanceBudgetSpec` (`PERF-API-1..N`)
Linked to approved Phase 13 Architecture API endpoints (`endpoint_id`: `API-1..N`) and PRD requirements:
- `route_pattern`: e.g. `GET /api/projects`
- `p95_latency_ms` (`10..15000` ms) and `p99_latency_ms` (`20..30000` ms, enforced `p99_latency_ms >= p95_latency_ms`)
- `max_payload_kb` (`1..10240` KiB)
- `caching_and_query_strategy`: indexing, pagination, and caching strategy

---

## 3. Honest Measurement Policy (`PerformanceMeasurementEvidence`)

WebForge strictly prohibits fabricated Lighthouse scores, fake benchmark numbers, or unverified load-test claims:

1. **Target Budget vs. Measured Observation**:
   - By default, generated specifications start with `core_web_vitals.measurement_posture = "target_budget_only"` and `PerformanceMeasurementEvidence.status = "target_only"`, `environment = "unmeasured_target"`, and `measured_value = None`.
2. **Evidence Requirements for Measured Claims**:
   - An evidence item (`EVD-N`) may only record a non-null `measured_value` if:
     - `environment` is a real execution environment (`"local_build" | "ci_pipeline" | "staging" | "production"`, never `"unmeasured_target"`),
     - `measured_at` records an explicit ISO-8601 timestamp (`>= 8` chars),
     - `measurement_tool` names the concrete tool used (e.g., `vite build bundle analyzer`, `pytest latency fixture`, `Lighthouse CI`),
     - `scope_description` and `limitations` document what was measured and what remains unmeasured, and
     - `status` is `"measured_pass"` or `"measured_warn"`.
   - Conversely, if `measured_value is None`, `status` **must** remain `"target_only"`.
   - Setting `core_web_vitals.measurement_posture = "measured_observation"` without at least one valid measured `EVD-N` record raises a validation error (`422`).
3. **Interactive Evidence Recording**:
   - Operators and developers can record real benchmark observations via `POST /api/projects/{project_id}/optimization/performance/versions/{version}/evidence` (or the **Record Measured Observation** form in `/projects/:projectId/performance`).

---

## 4. Deterministic Product Verification Checks

`GET /api/projects/{project_id}/optimization` and `POST /api/projects/{project_id}/optimization/verify-product` execute `run_product_verification_checks`, verifying:
1. `OPT-CHK-SEO-INDEXABILITY`: Public routes are indexable, private/authenticated routes enforce `noindex` and are excluded from `/sitemap.xml`, and `robots.txt` disallows private/API paths.
2. `OPT-CHK-HTML-SEMANTICS`: Rendered `frontend/index.html` contains `lang`, `<title>`, `<meta name="description">`, `<meta name="viewport">`, and `<meta name="robots">`.
3. `OPT-CHK-ANALYTICS-PRIVACY`: Analytics specification enforces opt-in consent, IP anonymization, Do-Not-Track, zero prohibited sensitive fields, and zero third-party data transmission.
4. `OPT-CHK-PERF-BUDGETS`: Core Web Vitals targets meet Google "Good" thresholds (`LCP <= 2500ms`, `INP <= 200ms`, `CLS <= 0.1`), route/API budgets are valid, and measurement posture is honest.
5. `OPT-CHK-NGINX-CACHING`: `frontend/nginx.conf` configures immutable `/assets/` caching, `no-cache` HTML shell headers, and `gzip` compression, while WebForge platform observability remains isolated from product analytics.
