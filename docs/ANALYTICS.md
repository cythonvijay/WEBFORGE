# Phase 16 — Product Analytics, Privacy & Consent Specification

## 1. Scope Separation: Generated Product Analytics vs. WebForge Platform Observability

WebForge strictly separates product analytics specifications from platform operational monitoring:

1. **Generated Product Analytics Specification (`backend/app/optimization.py`, `backend/app/optimization_api.py`)**:
   - Defines the taxonomy of product events (`EVT-N`), typed event properties, consent categories, PII redaction rules, retention policies, and reporting/funnel views (`VIEW-N`) that the **user's generated product** requires to measure its approved PRD goals and user journeys.
   - Persisted in `optimization_artifacts` (`area = 'analytics'`) and referenced in `ProjectBrain.optimization_spec.analytics`.
   - WebForge **never** loads third-party analytics trackers or transmits end-user behavioral telemetry for a generated product while authoring its specification.
2. **WebForge Platform Operational Observability (`backend/app/observability.py`)**:
   - Measures WebForge's own operational health (`MetricsRegistry.snapshot()` exposed on `/api/health/live` with `scope = "webforge_platform_operational_only"`): request counts, status classes (`2xx`, `4xx`, `5xx`), `error_rate`, `slow_requests_total` (above `SLOW_REQUEST_THRESHOLD_MS`), `avg_duration_ms`, `max_duration_ms`, and latency histogram buckets (`duration_buckets_ms`: `le_50ms`, `le_200ms`, `le_500ms`, `gt_500ms`).

---

## 2. Analytics Domain Model (`AnalyticsContent`)

### 2.1 `AnalyticsMeasurementPlan`
- `measurement_objective`: primary product measurement objective tied to PRD goals.
- `primary_kpis`: concrete product KPIs (`min_length=1`).
- `conversion_funnels`: multi-step user journey funnels (`min_length=1`).
- `data_retention_policy`: explicit retention window and deletion workflow.
- `ip_anonymization_enabled: bool` (must be `True`).
- `respect_do_not_track: bool` (must be `True`).
- `requirement_coverage`: `RequirementCoverageEntry` list covering all PRD requirements (`covered` or `not_applicable` with justification).

### 2.2 `AnalyticsEventSpec` (`EVT-1..N`)
- `id`: `EVT-1..N`
- `event_name`: `snake_case` identifier (`^[a-z][a-z0-9_]{2,63}$`, unique across the specification)
- `category`: `"acquisition" | "activation" | "engagement" | "conversion" | "retention" | "error_diagnostic"`
- `trigger_description`: exact user or system action that emits the event
- `screen_id`: validated against approved Prototype (`SCR-N`) or Wireframe (`WF-N`) screens
- `journey_id`: optional reference validated against approved UX Journeys (`J-N`)
- `interaction_id`: optional reference validated against approved Prototype interactions (`INT-N`)
- `linked_requirement_ids`: validated against approved PRD requirements (`FR-N`, `NFR-N`)
- `consent_category`: `"essential" | "analytics" | "functional" | "marketing"`
- `requires_opt_in`: `bool`
- `properties`: list of `AnalyticsEventPropertySpec` (`name`, `data_type`, `required`, `pii_classification`, `description`)

### 2.3 `ConsentAndPrivacySpec`
- `consent_Framework`: e.g. `"explicit_opt_in_banner_with_granular_categories"`
- `default_consent_state`: must be `"denied_until_opt_in"` (or `"essential_only"`)
- `pii_redaction_rules`: explicit server/client scrubbing rules (`min_length=2`)
- `prohibited_fields`: explicit denylist of never-collected fields
- `user_opt_out_mechanism`: how users revoke consent or delete telemetry
- `third_party_transmission_enabled`: must be `False` (provider-neutral specification; no unconsented third-party transmission)

### 2.4 `AnalyticsReportingViewSpec` (`VIEW-1..N`)
- Links reporting dashboards and funnel views (`included_event_ids`) to approved `EVT-N` events, target roles, and primary decisions enabled.

---

## 3. Server-Side Privacy, Consent & Security Enforcement

`AnalyticsContent` enforces strict privacy-by-design invariants in Pydantic validators and `run_product_verification_checks`:

1. **Prohibited Sensitive Property Denylist**:
   - Any event property whose name matches or contains a sensitive token (`password`, `passcode`, `secret`, `access_token`, `refresh_token`, `jwt`, `bearer`, `session_token`, `api_key`, `private_key`, `credit_card`, `card_number`, `cvv`, `cvc`, `ssn`, `social_security`, `tax_id`, `raw_email`, `phone_number`, `cookie`, `authorization`, `bank_account`) is rejected with `422 Unprocessable Entity`.
2. **No Direct PII in Event Properties**:
   - `pii_classification` only permits `"none"` or `"pseudonymous_id"`. Direct PII classifications (`raw_pii`, `email`, `sensitive`) are rejected by schema validation.
3. **Explicit Opt-In Consent for Non-Essential Tracking**:
   - Any event with `consent_category` in `{"analytics", "functional", "marketing"}` must set `requires_opt_in = True`.
   - `measurement_plan.ip_anonymization_enabled` and `measurement_plan.respect_do_not_track` must both be `True`.
   - `consent_and_privacy.third_party_transmission_enabled` must be `False`.

---

## 4. Lifecycle & Approval Workflow

- Follows the same versioned lifecycle as all WebForge artifacts:
  - `POST /api/projects/{project_id}/optimization/analytics/initialize` (or `/generate`) creates `draft` `v1`.
  - Editing an `approved` version via `PUT` or `PATCH` automatically clones a new `draft` version (`v+1`) via copy-on-write while preserving the approved version immutable.
  - `POST /api/projects/{project_id}/optimization/analytics/versions/{v}/submit` validates completeness and requirement coverage (`covered` or `not_applicable` with justification).
  - `POST /api/projects/{project_id}/optimization/analytics/versions/{v}/approve` verifies `content_hash`, promotes `status` to `"approved"`, writes `ProjectBrain.optimization_spec.analytics`, and synchronizes the `analytics` lifecycle stage (`sync_optimization_stages`).
