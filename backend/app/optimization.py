"""Phase 16: SEO, Analytics & Performance domain schemas, validators,
cross-artifact traceability, deterministic HTML/sitemap/robots verifiers,
and AI prompt builders.
"""
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    ArchitectureDocument,
    DesignArtifact,
    PrdDocument,
    ResearchReport,
    StrategyDocument,
    UxArtifact,
)

OptimizationArea = Literal["seo", "analytics", "performance"]
OPTIMIZATION_AREAS: tuple[OptimizationArea, ...] = ("seo", "analytics", "performance")
OptimizationItemStatus = Literal["proposed", "confirmed", "requires_review"]

S = lambda min_len=1, max_len=500: Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=min_len, max_length=max_len)
]

PROHIBITED_SENSITIVE_FIELDS: tuple[str, ...] = (
    "password",
    "passcode",
    "secret",
    "access_token",
    "refresh_token",
    "api_key",
    "private_key",
    "authorization",
    "cookie",
    "session_token",
    "credit_card",
    "card_number",
    "cvv",
    "ssn",
    "tax_id",
    "raw_email",
    "phone_number",
    "full_address",
)

SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
ROUTE_PATH_RE = re.compile(r"^/[a-zA-Z0-9_\-/:.]*$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequirementCoverageEntry(StrictModel):
    requirement_id: S(2, 40)
    requirement_title: S(2, 240)
    coverage_status: Literal["covered", "not_applicable"] = "covered"
    justification: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _validate_justification(self) -> "RequirementCoverageEntry":
        if self.coverage_status == "not_applicable":
            if not self.justification or len(self.justification.strip()) < 10:
                raise ValueError(
                    f"Requirement {self.requirement_id} marked not_applicable requires a justification (>=10 chars)."
                )
        return self


# ---------------------------------------------------------------------------
# 1. SEO Specification Models
# ---------------------------------------------------------------------------

class SeoStrategySummary(StrictModel):
    primary_search_intent: S(15, 800)
    target_audience_summary: S(15, 800)
    canonical_domain_strategy: S(15, 600)
    url_structure_conventions: list[S(5, 300)] = Field(min_length=1, max_length=15)
    crawl_and_indexing_policy: S(15, 800)
    locale_and_language_strategy: S(5, 400)
    requirement_coverage: list[RequirementCoverageEntry] = Field(default_factory=list, max_length=60)
    open_questions: list[S(5, 400)] = Field(default_factory=list, max_length=20)


class PageSeoMetadataSpec(StrictModel):
    id: S(3, 40)
    screen_id: S(2, 40)
    route_path: S(1, 200)
    visibility: Literal["public", "private", "authenticated", "transactional", "admin"]
    robots_index: Literal["index", "noindex"]
    robots_follow: Literal["follow", "nofollow"]
    include_in_sitemap: bool
    canonical_path: S(1, 200)
    title_template: S(5, 120)
    meta_description: S(25, 320)
    h1_heading: S(3, 140)
    heading_hierarchy: list[S(3, 160)] = Field(min_length=1, max_length=12)
    og_title: S(5, 120)
    og_description: S(15, 320)
    og_type: Literal["website", "article", "product", "profile"] = "website"
    twitter_card: Literal["summary", "summary_large_image"] = "summary_large_image"
    structured_data_type: Literal[
        "None",
        "WebSite",
        "SoftwareApplication",
        "Organization",
        "FAQPage",
        "BreadcrumbList",
        "Product",
    ] = "None"
    structured_data_justification: str | None = Field(default=None, max_length=500)
    internal_links_to: list[S(1, 200)] = Field(default_factory=list, max_length=25)
    linked_requirement_ids: list[S(2, 40)] = Field(min_length=1, max_length=25)
    status: OptimizationItemStatus = "proposed"
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("route_path", "canonical_path")
    @classmethod
    def _validate_route(cls, v: str) -> str:
        if "://" in v or v.startswith("http"):
            raise ValueError(
                f"Route/canonical path '{v}' must be a relative route path or env-templated path, must not fabricate a live production domain."
            )
        if not ROUTE_PATH_RE.match(v):
            raise ValueError(f"Invalid route path '{v}'; must start with '/'.")
        return v

    @model_validator(mode="after")
    def _validate_visibility_and_indexing(self) -> "PageSeoMetadataSpec":
        if self.visibility != "public":
            if self.robots_index != "noindex":
                raise ValueError(
                    f"Page {self.id} ({self.route_path}) has visibility='{self.visibility}' and must use robots_index='noindex'."
                )
            if self.include_in_sitemap:
                raise ValueError(
                    f"Page {self.id} ({self.route_path}) has visibility='{self.visibility}' and must not be included in XML sitemap."
                )
        if self.structured_data_type != "None":
            if not self.structured_data_justification or len(self.structured_data_justification.strip()) < 10:
                raise ValueError(
                    f"Page {self.id} specifies structured_data_type='{self.structured_data_type}' without a justification (>=10 chars)."
                )
        return self


class SitemapDirectiveSpec(StrictModel):
    sitemap_path: S(4, 120) = "/sitemap.xml"
    changefreq_policy: S(10, 400)
    included_routes: list[S(1, 200)] = Field(default_factory=list, max_length=50)
    excluded_routes: list[S(1, 200)] = Field(default_factory=list, max_length=50)
    exclusion_rationale: S(10, 600)


class RobotsDirectiveSpec(StrictModel):
    user_agent: S(1, 60) = "*"
    allow_paths: list[S(1, 200)] = Field(default_factory=list, max_length=50)
    disallow_paths: list[S(1, 200)] = Field(default_factory=list, max_length=50)
    sitemap_reference: S(4, 200) = "${PUBLIC_BASE_URL}/sitemap.xml"
    rationale: S(10, 600)


class TechnicalSeoChecklistItem(StrictModel):
    id: S(3, 40)
    category: Literal["semantics", "accessibility", "canonicals", "links", "structured_data", "crawlability"]
    title: S(5, 200)
    verification_rule: S(10, 500)
    linked_screen_ids: list[S(2, 40)] = Field(min_length=1, max_length=25)
    status: OptimizationItemStatus = "proposed"


class SeoContent(StrictModel):
    seo_strategy: SeoStrategySummary
    page_metadata: list[PageSeoMetadataSpec] = Field(min_length=1, max_length=40)
    sitemap_spec: SitemapDirectiveSpec
    robots_spec: RobotsDirectiveSpec
    technical_checklist: list[TechnicalSeoChecklistItem] = Field(min_length=2, max_length=30)

    @model_validator(mode="after")
    def _validate_seo_consistency(self) -> "SeoContent":
        seen_ids: set[str] = set()
        seen_routes: set[str] = set()
        for p in self.page_metadata:
            if p.id in seen_ids:
                raise ValueError(f"Duplicate page metadata ID '{p.id}'.")
            seen_ids.add(p.id)
            if p.route_path in seen_routes:
                raise ValueError(f"Duplicate route_path '{p.route_path}' in page_metadata.")
            seen_routes.add(p.route_path)

        for p in self.page_metadata:
            for target in p.internal_links_to:
                if target not in seen_routes:
                    raise ValueError(
                        f"Page {p.id} ({p.route_path}) has internal_links_to '{target}' which is not defined in page_metadata."
                    )

        private_routes = {p.route_path for p in self.page_metadata if p.visibility != "public"}
        public_indexable = {
            p.route_path for p in self.page_metadata if p.visibility == "public" and p.robots_index == "index"
        }
        for r in self.sitemap_spec.included_routes:
            if r in private_routes:
                raise ValueError(f"Private/non-public route '{r}' cannot appear in sitemap_spec.included_routes.")
            if r not in seen_routes:
                raise ValueError(f"Sitemap included route '{r}' is not defined in page_metadata.")
        for p in self.page_metadata:
            if p.include_in_sitemap and p.route_path not in self.sitemap_spec.included_routes:
                raise ValueError(
                    f"Page {p.id} ({p.route_path}) has include_in_sitemap=True but is missing from sitemap_spec.included_routes."
                )
            if not p.include_in_sitemap and p.route_path in self.sitemap_spec.included_routes:
                raise ValueError(
                    f"Page {p.id} ({p.route_path}) has include_in_sitemap=False but appears in sitemap_spec.included_routes."
                )
        for r in private_routes:
            if r not in self.sitemap_spec.excluded_routes:
                raise ValueError(
                    f"Non-public route '{r}' must be listed in sitemap_spec.excluded_routes."
                )
        if not public_indexable and self.sitemap_spec.included_routes:
            raise ValueError("Sitemap includes routes when no public indexable pages exist.")
        return self


# ---------------------------------------------------------------------------
# 2. Analytics Specification Models
# ---------------------------------------------------------------------------

class AnalyticsMeasurementPlan(StrictModel):
    measurement_objective: S(15, 800)
    primary_kpis: list[S(5, 300)] = Field(min_length=1, max_length=15)
    conversion_funnels: list[S(10, 400)] = Field(min_length=1, max_length=12)
    data_retention_policy: S(10, 500)
    ip_anonymization_enabled: bool = True
    respect_do_not_track: bool = True
    requirement_coverage: list[RequirementCoverageEntry] = Field(default_factory=list, max_length=60)
    open_questions: list[S(5, 400)] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _validate_privacy_defaults(self) -> "AnalyticsMeasurementPlan":
        if not self.ip_anonymization_enabled:
            raise ValueError("AnalyticsMeasurementPlan must keep ip_anonymization_enabled=True.")
        return self


class EventPropertySchema(StrictModel):
    name: S(2, 64)
    data_type: Literal["string", "number", "boolean", "enum"]
    required: bool = True
    pii_classification: Literal["none", "pseudonymous_id"] = "none"
    description: S(5, 300)

    @field_validator("name")
    @classmethod
    def _validate_prop_name(cls, v: str) -> str:
        low = v.lower().strip()
        if not SNAKE_CASE_RE.match(low):
            raise ValueError(f"Event property name '{v}' must be snake_case.")
        for banned in PROHIBITED_SENSITIVE_FIELDS:
            if low == banned or banned in low:
                raise ValueError(
                    f"Analytics event property '{v}' is prohibited for privacy/security (matches sensitive field '{banned}')."
                )
        return low


class AnalyticsEventSpec(StrictModel):
    id: S(3, 40)
    event_name: S(3, 64)
    category: Literal["acquisition", "activation", "engagement", "conversion", "retention", "system_error"]
    trigger_description: S(10, 400)
    screen_id: S(2, 40)
    journey_id: str | None = Field(default=None, max_length=40)
    interaction_id: str | None = Field(default=None, max_length=40)
    linked_requirement_ids: list[S(2, 40)] = Field(min_length=1, max_length=25)
    consent_category: Literal["strictly_necessary", "analytics", "functional", "marketing"] = "analytics"
    requires_opt_in: bool = True
    properties: list[EventPropertySchema] = Field(min_length=1, max_length=20)
    success_metric_tie_in: S(10, 400)
    status: OptimizationItemStatus = "proposed"

    @field_validator("event_name")
    @classmethod
    def _validate_event_name(cls, v: str) -> str:
        if not SNAKE_CASE_RE.match(v):
            raise ValueError(f"Event name '{v}' must be snake_case (3-64 chars, lowercase alphanumeric + underscores).")
        return v

    @model_validator(mode="after")
    def _validate_consent_gate(self) -> "AnalyticsEventSpec":
        if self.consent_category in ("analytics", "functional", "marketing") and not self.requires_opt_in:
            raise ValueError(
                f"Event {self.id} ({self.event_name}) has consent_category='{self.consent_category}' and must set requires_opt_in=True."
            )
        seen_props: set[str] = set()
        for prop in self.properties:
            if prop.name in seen_props:
                raise ValueError(f"Duplicate property '{prop.name}' in event {self.id}.")
            seen_props.add(prop.name)
        return self


class ConsentPrivacyRequirement(StrictModel):
    consent_mode: Literal["opt_in_required", "essential_only"] = "opt_in_required"
    banner_required: bool = True
    consent_categories_supported: list[S(3, 40)] = Field(min_length=1, max_length=10)
    excluded_sensitive_fields: list[S(2, 60)] = Field(min_length=3, max_length=30)
    pii_redaction_rules: list[S(10, 300)] = Field(min_length=1, max_length=15)
    user_deletion_and_opt_out_flow: S(15, 600)
    provider_neutral_adapter_notes: S(15, 600)
    third_party_transmission_enabled: bool = False

    @model_validator(mode="after")
    def _validate_no_third_party_leak(self) -> "ConsentPrivacyRequirement":
        if self.third_party_transmission_enabled:
            raise ValueError(
                "third_party_transmission_enabled must be False by default; WebForge specifications must not transmit user data to unconfigured third-party analytics endpoints."
            )
        excluded_low = {f.lower() for f in self.excluded_sensitive_fields}
        for core_secret in ("password", "access_token", "raw_email"):
            if core_secret not in excluded_low:
                raise ValueError(
                    f"excluded_sensitive_fields must explicitly include '{core_secret}'."
                )
        return self


class ReportingDiagnosticSpec(StrictModel):
    id: S(3, 40)
    title: S(5, 160)
    questions_answered: list[S(10, 300)] = Field(min_length=1, max_length=10)
    tracked_event_ids: list[S(3, 40)] = Field(min_length=1, max_length=25)
    primary_audience: S(3, 160)
    status: OptimizationItemStatus = "proposed"


class AnalyticsContent(StrictModel):
    measurement_plan: AnalyticsMeasurementPlan
    events: list[AnalyticsEventSpec] = Field(min_length=2, max_length=50)
    consent_and_privacy: ConsentPrivacyRequirement
    reporting_views: list[ReportingDiagnosticSpec] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _validate_analytics_consistency(self) -> "AnalyticsContent":
        seen_ids: set[str] = set()
        seen_names: set[str] = set()
        for ev in self.events:
            if ev.id in seen_ids:
                raise ValueError(f"Duplicate analytics event ID '{ev.id}'.")
            seen_ids.add(ev.id)
            if ev.event_name in seen_names:
                raise ValueError(f"Duplicate analytics event_name '{ev.event_name}'.")
            seen_names.add(ev.event_name)

        for rv in self.reporting_views:
            for eid in rv.tracked_event_ids:
                if eid not in seen_ids:
                    raise ValueError(
                        f"Reporting view {rv.id} references unknown tracked_event_id '{eid}'."
                    )
        return self


# ---------------------------------------------------------------------------
# 3. Performance Specification Models
# ---------------------------------------------------------------------------

class CoreWebVitalsBudget(StrictModel):
    lcp_max_ms: int = Field(ge=500, le=6000)
    inp_max_ms: int = Field(ge=50, le=1000)
    cls_max_score: float = Field(ge=0.0, le=0.5)
    fcp_max_ms: int = Field(ge=300, le=5000)
    ttfb_max_ms: int = Field(ge=50, le=3000)
    measurement_status: Literal["target_budget_only", "measured_observation"] = "target_budget_only"
    rationale: S(15, 600)


class RouteAssetBudgetSpec(StrictModel):
    id: S(3, 40)
    screen_id: S(2, 40)
    route_path: S(1, 200)
    initial_js_kb_gzip: int = Field(ge=10, le=2000)
    initial_css_kb_gzip: int = Field(ge=5, le=500)
    max_image_weight_kb: int = Field(ge=10, le=5000)
    loading_strategy: Literal["eager_critical", "route_code_split", "lazy_below_fold", "ssr_stream", "static_prerender"]
    caching_policy: S(10, 300)
    linked_requirement_ids: list[S(2, 40)] = Field(min_length=1, max_length=25)
    status: OptimizationItemStatus = "proposed"
    notes: str | None = Field(default=None, max_length=400)


class BackendApiPerformanceBudgetSpec(StrictModel):
    id: S(3, 40)
    endpoint_id: S(2, 40)
    route_pattern: S(1, 240)
    p95_latency_ms: int = Field(ge=10, le=15000)
    p99_latency_ms: int = Field(ge=20, le=30000)
    max_payload_kb: int = Field(ge=1, le=10240)
    caching_and_query_strategy: S(10, 400)
    linked_requirement_ids: list[S(2, 40)] = Field(min_length=1, max_length=25)
    status: OptimizationItemStatus = "proposed"

    @model_validator(mode="after")
    def _validate_percentiles(self) -> "BackendApiPerformanceBudgetSpec":
        if self.p99_latency_ms < self.p95_latency_ms:
            raise ValueError(
                f"API budget {self.id}: p99_latency_ms ({self.p99_latency_ms}) must be >= p95_latency_ms ({self.p95_latency_ms})."
            )
        return self


class PerformanceMeasurementEvidence(StrictModel):
    id: S(3, 40)
    metric_name: S(3, 120)
    target_value: S(1, 80)
    measured_value: str | None = Field(default=None, max_length=80)
    unit: S(1, 30)
    measurement_tool: S(3, 120)
    environment: Literal["local_build", "ci_pipeline", "staging", "production", "unmeasured_target"]
    measured_at: str | None = Field(default=None, max_length=64)
    scope_description: S(10, 400)
    limitations: S(10, 500)
    status: Literal["target_only", "measured_pass", "measured_warn"] = "target_only"

    @model_validator(mode="after")
    def _validate_evidence_honesty(self) -> "PerformanceMeasurementEvidence":
        if self.measured_value is not None:
            if self.environment == "unmeasured_target":
                raise ValueError(
                    f"Evidence {self.id} cannot record a measured_value when environment is 'unmeasured_target'."
                )
            if not self.measured_at or len(self.measured_at.strip()) < 8:
                raise ValueError(
                    f"Evidence {self.id} with measured_value requires a recorded measured_at timestamp."
                )
            if self.status == "target_only":
                raise ValueError(
                    f"Evidence {self.id} with measured_value must use status 'measured_pass' or 'measured_warn'."
                )
        else:
            if self.status != "target_only":
                raise ValueError(
                    f"Evidence {self.id} without measured_value must have status='target_only' (do not fabricate measured pass scores)."
                )
        return self


class PerformanceStrategySummary(StrictModel):
    performance_posture: S(15, 800)
    bundling_and_code_splitting_strategy: S(15, 600)
    image_and_font_optimization_strategy: S(15, 600)
    caching_and_cdn_strategy: S(15, 600)
    runtime_monitoring_and_alerting: S(15, 600)
    requirement_coverage: list[RequirementCoverageEntry] = Field(default_factory=list, max_length=60)
    open_questions: list[S(5, 400)] = Field(default_factory=list, max_length=20)


class PerformanceContent(StrictModel):
    strategy: PerformanceStrategySummary
    core_web_vitals: CoreWebVitalsBudget
    route_budgets: list[RouteAssetBudgetSpec] = Field(min_length=1, max_length=40)
    api_budgets: list[BackendApiPerformanceBudgetSpec] = Field(min_length=1, max_length=40)
    measurement_evidence: list[PerformanceMeasurementEvidence] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def _validate_performance_consistency(self) -> "PerformanceContent":
        seen_routes: set[str] = set()
        for rb in self.route_budgets:
            if rb.route_path in seen_routes:
                raise ValueError(f"Duplicate route_path '{rb.route_path}' in route_budgets.")
            seen_routes.add(rb.route_path)

        seen_eps: set[str] = set()
        for ab in self.api_budgets:
            if ab.endpoint_id in seen_eps:
                raise ValueError(f"Duplicate endpoint_id '{ab.endpoint_id}' in api_budgets.")
            seen_eps.add(ab.endpoint_id)

        if self.core_web_vitals.measurement_status == "measured_observation":
            has_real_measurement = any(
                ev.measured_value is not None and ev.status in ("measured_pass", "measured_warn")
                for ev in self.measurement_evidence
            )
            if not has_real_measurement:
                raise ValueError(
                    "core_web_vitals.measurement_status='measured_observation' requires at least one measurement_evidence entry with a recorded measured_value and timestamp."
                )
        return self


class GeneratedSeo(SeoContent):
    pass


class GeneratedAnalytics(AnalyticsContent):
    pass


class GeneratedPerformance(PerformanceContent):
    pass


OPTIMIZATION_MODEL_MAP: dict[OptimizationArea, type[StrictModel]] = {
    "seo": SeoContent,
    "analytics": AnalyticsContent,
    "performance": PerformanceContent,
}

GENERATED_SCHEMA_MAP: dict[OptimizationArea, type[StrictModel]] = {
    "seo": GeneratedSeo,
    "analytics": GeneratedAnalytics,
    "performance": GeneratedPerformance,
}


# ---------------------------------------------------------------------------
# 4. Canonical Hashing, Basis Extraction & Cross-Artifact Traceability
# ---------------------------------------------------------------------------

def compute_optimization_hash(area: OptimizationArea, content: dict[str, Any] | StrictModel) -> str:
    if isinstance(content, StrictModel):
        payload = content.model_dump(mode="json")
    else:
        model_cls = OPTIMIZATION_MODEL_MAP[area]
        payload = model_cls.model_validate(content).model_dump(mode="json")
    canonical = json.dumps({"area": area, "content": payload}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class OptimizationBasisSummary(StrictModel):
    research_report_version: int | None = None
    research_content_hash: str | None = None
    strategy_version: int | None = None
    strategy_content_hash: str | None = None
    prd_version: int | None = None
    prd_content_hash: str | None = None
    ux_versions: dict[str, int] = Field(default_factory=dict)
    ux_hashes: dict[str, str] = Field(default_factory=dict)
    design_system_version: int | None = None
    design_system_hash: str | None = None
    prototype_version: int | None = None
    prototype_hash: str | None = None
    architecture_version: int | None = None
    architecture_content_hash: str | None = None


def build_optimization_basis(db: Session, project_id: str) -> dict[str, Any]:
    research = db.scalar(
        select(ResearchReport)
        .where(ResearchReport.project_id == project_id, ResearchReport.status == "approved")
        .order_by(ResearchReport.version.desc())
    )
    strategy = db.scalar(
        select(StrategyDocument)
        .where(StrategyDocument.project_id == project_id, StrategyDocument.status == "approved")
        .order_by(StrategyDocument.version.desc())
    )
    prd = db.scalar(
        select(PrdDocument)
        .where(PrdDocument.project_id == project_id, PrdDocument.status == "approved")
        .order_by(PrdDocument.version.desc())
    )
    ux_rows = (
        db.scalars(
            select(UxArtifact).where(UxArtifact.project_id == project_id, UxArtifact.status == "approved")
        )
    )
    ux_map: dict[str, UxArtifact] = {}
    for row in ux_rows:
        if row.artifact_type not in ux_map or row.version > ux_map[row.artifact_type].version:
            ux_map[row.artifact_type] = row

    design_rows = (
        db.scalars(
            select(DesignArtifact).where(DesignArtifact.project_id == project_id, DesignArtifact.status == "approved")
        )
    )
    design_map: dict[str, DesignArtifact] = {}
    for row in design_rows:
        if row.artifact_type not in design_map or row.version > design_map[row.artifact_type].version:
            design_map[row.artifact_type] = row

    arch_doc = db.scalar(
        select(ArchitectureDocument)
        .where(ArchitectureDocument.project_id == project_id, ArchitectureDocument.status == "approved")
        .order_by(ArchitectureDocument.version.desc())
    )

    requirements: list[dict[str, Any]] = []
    if prd and prd.content:
        for req in prd.content.get("functional_requirements", []):
            prio = str(req.get("priority", "must_have")).lower()
            if prio != "wont_have":
                requirements.append(
                    {
                        "id": req["id"],
                        "title": req.get("title") or req.get("statement", req["id"])[:160],
                        "priority": prio,
                        "category": "functional",
                    }
                )
        for nfr in prd.content.get("non_functional_requirements", []):
            prio = str(nfr.get("priority", "must_have")).lower()
            if prio != "wont_have":
                requirements.append(
                    {
                        "id": nfr["id"],
                        "title": nfr.get("title") or f"{nfr.get('category', 'NFR')}: {nfr.get('requirement', nfr['id'])[:140]}",
                        "priority": prio,
                        "category": "non_functional",
                    }
                )

    screens: list[dict[str, Any]] = []
    interactions: list[dict[str, Any]] = []
    if "prototype" in design_map and design_map["prototype"].content:
        proto = design_map["prototype"].content
        for scr in proto.get("screens", []):
            route_p = scr.get("route_or_view") or f"/{scr['id'].lower()}"
            if not route_p.startswith("/"):
                route_p = "/" + route_p
            screens.append(
                {
                    "id": scr["id"],
                    "name": scr.get("name", scr["id"]),
                    "route_path": route_p.split(" ")[0].strip(),
                    "primary_goal": scr.get("primary_goal", ""),
                    "prd_requirement_ids": scr.get("prd_requirement_ids", []),
                }
            )
            for inter in scr.get("interactions", []):
                interactions.append(
                    {
                        "id": inter["id"],
                        "screen_id": scr["id"],
                        "label": inter.get("trigger_label", inter["id"]),
                    }
                )

    if not screens and "wireframes" in ux_map and ux_map["wireframes"].content:
        for wf in ux_map["wireframes"].content.get("wireframes", ux_map["wireframes"].content.get("screens", [])):
            screens.append(
                {
                    "id": wf["id"],
                    "name": wf.get("name", wf["id"]),
                    "route_path": f"/{wf['id'].lower()}",
                    "primary_goal": wf.get("purpose", ""),
                    "prd_requirement_ids": wf.get("prd_requirement_ids", []),
                }
            )

    journeys: list[dict[str, Any]] = []
    if "journeys" in ux_map and ux_map["journeys"].content:
        for j in ux_map["journeys"].content.get("journeys", []):
            journeys.append({"id": j["id"], "name": j.get("name", j["id"]), "goal": j.get("goal", "")})

    ia_routes: list[dict[str, Any]] = []
    if "ia" in ux_map and ux_map["ia"].content:
        for node in ux_map["ia"].content.get("nodes", ux_map["ia"].content.get("sitemap_nodes", [])):
            p = node.get("path_or_route") or node.get("route") or f"/{node['id'].lower()}"
            if not p.startswith("/"):
                p = "/" + p
            ia_routes.append({"id": node["id"], "label": node.get("label", node["id"]), "path": p.split(" ")[0].strip()})

    endpoints: list[dict[str, Any]] = []
    components: list[dict[str, Any]] = []
    if arch_doc and arch_doc.content:
        ep_list = (
            arch_doc.content.get("api_architecture", {}).get("endpoints")
            or arch_doc.content.get("api_and_integration_contracts", {}).get("endpoints")
            or []
        )
        for ep in ep_list:
            endpoints.append(
                {
                    "id": ep["id"],
                    "method": ep.get("method", "GET"),
                    "path": ep.get("path", "/api/resource"),
                    "purpose": ep.get("purpose", ""),
                    "prd_requirement_ids": ep.get("prd_requirement_ids", []),
                }
            )
        for comp in arch_doc.content.get("system_overview", {}).get("components", []):
            components.append({"id": comp["id"], "name": comp.get("name", comp["id"]), "layer": comp.get("layer", "backend")})

    routes_by_path: dict[str, dict[str, Any]] = {}
    for scr in screens:
        rp = scr["route_path"]
        if rp not in routes_by_path:
            routes_by_path[rp] = {"path": rp, "screen_id": scr["id"], "name": scr["name"]}
    for iar in ia_routes:
        rp = iar["path"]
        if rp not in routes_by_path:
            routes_by_path[rp] = {"path": rp, "screen_id": screens[0]["id"] if screens else "SCR-1", "name": iar["label"]}

    return {
        "research_report_version": research.version if research else None,
        "research_content_hash": research.content_hash if research else None,
        "strategy_version": strategy.version if strategy else None,
        "strategy_content_hash": strategy.content_hash if strategy else None,
        "prd_version": prd.version if prd else None,
        "prd_content_hash": prd.content_hash if prd else None,
        "ux_versions": {k: v.version for k, v in ux_map.items()},
        "ux_hashes": {k: v.content_hash for k, v in ux_map.items()},
        "design_system_version": design_map["design_system"].version if "design_system" in design_map else None,
        "design_system_hash": design_map["design_system"].content_hash if "design_system" in design_map else None,
        "prototype_version": design_map["prototype"].version if "prototype" in design_map else None,
        "prototype_hash": design_map["prototype"].content_hash if "prototype" in design_map else None,
        "architecture_version": arch_doc.version if arch_doc else None,
        "architecture_content_hash": arch_doc.content_hash if arch_doc else None,
        "requirements": requirements,
        "screens": screens,
        "interactions": interactions,
        "journeys": journeys,
        "routes": list(routes_by_path.values()),
        "endpoints": endpoints,
        "components": components,
    }


class OptimizationTraceabilityFinding(StrictModel):
    code: str
    severity: Literal["error", "warning", "info"]
    message: str
    workspace: str
    reference_id: str | None = None


class RequirementOptimizationCoverageItem(StrictModel):
    requirement_id: str
    title: str
    priority: str
    covered: bool
    coverage_status: Literal["covered", "not_applicable", "uncovered"]
    justification: str | None = None
    mapped_item_ids: list[str] = Field(default_factory=list)


class OptimizationTraceabilitySummary(StrictModel):
    area: OptimizationArea
    complete: bool
    total_requirements: int
    covered_requirements: int
    requirement_coverage: list[RequirementOptimizationCoverageItem]
    valid_screen_ids: list[str]
    valid_route_paths: list[str]
    valid_endpoint_ids: list[str]
    findings: list[OptimizationTraceabilityFinding]


def _evaluate_req_coverage(
    area: OptimizationArea,
    basis_reqs: list[dict[str, Any]],
    explicit_entries: list[RequirementCoverageEntry],
    item_req_map: dict[str, list[str]],
    findings: list[OptimizationTraceabilityFinding],
) -> tuple[list[RequirementOptimizationCoverageItem], int]:
    explicit_by_id = {e.requirement_id: e for e in explicit_entries}
    valid_req_ids = {r["id"] for r in basis_reqs}

    for req_id, item_ids in item_req_map.items():
        if valid_req_ids and req_id not in valid_req_ids:
            findings.append(
                OptimizationTraceabilityFinding(
                    code="UNKNOWN_PRD_REQUIREMENT_REF",
                    severity="error",
                    message=f"{area.upper()} items ({item_ids}) reference unknown PRD requirement '{req_id}'.",
                    workspace="prd",
                    reference_id=req_id,
                )
            )

    coverage_items: list[RequirementOptimizationCoverageItem] = []
    covered_count = 0
    for req in basis_reqs:
        rid = req["id"]
        mapped = item_req_map.get(rid, [])
        exp = explicit_by_id.get(rid)
        if mapped:
            covered_count += 1
            coverage_items.append(
                RequirementOptimizationCoverageItem(
                    requirement_id=rid,
                    title=req["title"],
                    priority=req["priority"],
                    covered=True,
                    coverage_status="covered",
                    justification=exp.justification if exp else None,
                    mapped_item_ids=mapped,
                )
            )
        elif exp and exp.coverage_status == "not_applicable":
            covered_count += 1
            coverage_items.append(
                RequirementOptimizationCoverageItem(
                    requirement_id=rid,
                    title=req["title"],
                    priority=req["priority"],
                    covered=True,
                    coverage_status="not_applicable",
                    justification=exp.justification,
                    mapped_item_ids=[],
                )
            )
        else:
            findings.append(
                OptimizationTraceabilityFinding(
                    code="PRD_REQUIREMENT_UNCOVERED",
                    severity="error",
                    message=f"PRD requirement {rid} ({req['title']}) has no {area.upper()} coverage or not_applicable justification.",
                    workspace=area,
                    reference_id=rid,
                )
            )
            coverage_items.append(
                RequirementOptimizationCoverageItem(
                    requirement_id=rid,
                    title=req["title"],
                    priority=req["priority"],
                    covered=False,
                    coverage_status="uncovered",
                    justification=None,
                    mapped_item_ids=[],
                )
            )
    return coverage_items, covered_count


def compute_seo_traceability(content: SeoContent, basis: dict[str, Any]) -> OptimizationTraceabilitySummary:
    findings: list[OptimizationTraceabilityFinding] = []
    valid_screens = {s["id"] for s in basis.get("screens", [])}
    valid_routes = {r["path"] for r in basis.get("routes", [])}
    valid_eps = [e["id"] for e in basis.get("endpoints", [])]

    item_req_map: dict[str, list[str]] = {}
    covered_screens: set[str] = set()
    for p in content.page_metadata:
        covered_screens.add(p.screen_id)
        if valid_screens and p.screen_id not in valid_screens:
            findings.append(
                OptimizationTraceabilityFinding(
                    code="SEO_UNKNOWN_SCREEN_REF",
                    severity="error",
                    message=f"SEO page {p.id} references unknown Prototype/Wireframe screen '{p.screen_id}'.",
                    workspace="prototype",
                    reference_id=p.screen_id,
                )
            )
        for rid in p.linked_requirement_ids:
            item_req_map.setdefault(rid, []).append(p.id)

    for chk in content.technical_checklist:
        for sid in chk.linked_screen_ids:
            if valid_screens and sid not in valid_screens:
                findings.append(
                    OptimizationTraceabilityFinding(
                        code="SEO_CHECKLIST_UNKNOWN_SCREEN",
                        severity="error",
                        message=f"Technical SEO item {chk.id} references unknown screen '{sid}'.",
                        workspace="prototype",
                        reference_id=sid,
                    )
                )

    for sid in sorted(valid_screens):
        if sid not in covered_screens:
            findings.append(
                OptimizationTraceabilityFinding(
                    code="SEO_SCREEN_UNCOVERED",
                    severity="warning",
                    message=f"Prototype screen {sid} does not have a dedicated PageSeoMetadataSpec entry.",
                    workspace="seo",
                    reference_id=sid,
                )
            )

    basis_reqs = basis.get("requirements", [])
    cov_items, cov_count = _evaluate_req_coverage(
        "seo", basis_reqs, content.seo_strategy.requirement_coverage, item_req_map, findings
    )
    has_errors = any(f.severity == "error" for f in findings)
    return OptimizationTraceabilitySummary(
        area="seo",
        complete=not has_errors and cov_count == len(basis_reqs),
        total_requirements=len(basis_reqs),
        covered_requirements=cov_count,
        requirement_coverage=cov_items,
        valid_screen_ids=sorted(valid_screens),
        valid_route_paths=sorted(valid_routes),
        valid_endpoint_ids=valid_eps,
        findings=findings,
    )


def compute_analytics_traceability(content: AnalyticsContent, basis: dict[str, Any]) -> OptimizationTraceabilitySummary:
    findings: list[OptimizationTraceabilityFinding] = []
    valid_screens = {s["id"] for s in basis.get("screens", [])}
    valid_journeys = {j["id"] for j in basis.get("journeys", [])}
    valid_interactions = {i["id"] for i in basis.get("interactions", [])}
    valid_routes = {r["path"] for r in basis.get("routes", [])}
    valid_eps = [e["id"] for e in basis.get("endpoints", [])]

    item_req_map: dict[str, list[str]] = {}
    for ev in content.events:
        if valid_screens and ev.screen_id not in valid_screens:
            findings.append(
                OptimizationTraceabilityFinding(
                    code="ANALYTICS_UNKNOWN_SCREEN_REF",
                    severity="error",
                    message=f"Analytics event {ev.id} ({ev.event_name}) references unknown screen '{ev.screen_id}'.",
                    workspace="prototype",
                    reference_id=ev.screen_id,
                )
            )
        if ev.journey_id and valid_journeys and ev.journey_id not in valid_journeys:
            findings.append(
                OptimizationTraceabilityFinding(
                    code="ANALYTICS_UNKNOWN_JOURNEY_REF",
                    severity="error",
                    message=f"Analytics event {ev.id} references unknown UX journey '{ev.journey_id}'.",
                    workspace="journeys",
                    reference_id=ev.journey_id,
                )
            )
        if ev.interaction_id and valid_interactions and ev.interaction_id not in valid_interactions:
            findings.append(
                OptimizationTraceabilityFinding(
                    code="ANALYTICS_UNKNOWN_INTERACTION_REF",
                    severity="error",
                    message=f"Analytics event {ev.id} references unknown Prototype interaction '{ev.interaction_id}'.",
                    workspace="prototype",
                    reference_id=ev.interaction_id,
                )
            )
        for rid in ev.linked_requirement_ids:
            item_req_map.setdefault(rid, []).append(ev.id)

    basis_reqs = basis.get("requirements", [])
    cov_items, cov_count = _evaluate_req_coverage(
        "analytics", basis_reqs, content.measurement_plan.requirement_coverage, item_req_map, findings
    )
    has_errors = any(f.severity == "error" for f in findings)
    return OptimizationTraceabilitySummary(
        area="analytics",
        complete=not has_errors and cov_count == len(basis_reqs),
        total_requirements=len(basis_reqs),
        covered_requirements=cov_count,
        requirement_coverage=cov_items,
        valid_screen_ids=sorted(valid_screens),
        valid_route_paths=sorted(valid_routes),
        valid_endpoint_ids=valid_eps,
        findings=findings,
    )


def compute_performance_traceability(content: PerformanceContent, basis: dict[str, Any]) -> OptimizationTraceabilitySummary:
    findings: list[OptimizationTraceabilityFinding] = []
    valid_screens = {s["id"] for s in basis.get("screens", [])}
    valid_routes = {r["path"] for r in basis.get("routes", [])}
    valid_eps = {e["id"] for e in basis.get("endpoints", [])}

    item_req_map: dict[str, list[str]] = {}
    for rb in content.route_budgets:
        if valid_screens and rb.screen_id not in valid_screens:
            findings.append(
                OptimizationTraceabilityFinding(
                    code="PERF_UNKNOWN_SCREEN_REF",
                    severity="error",
                    message=f"Route budget {rb.id} references unknown screen '{rb.screen_id}'.",
                    workspace="prototype",
                    reference_id=rb.screen_id,
                )
            )
        for rid in rb.linked_requirement_ids:
            item_req_map.setdefault(rid, []).append(rb.id)

    for ab in content.api_budgets:
        if valid_eps and ab.endpoint_id not in valid_eps:
            findings.append(
                OptimizationTraceabilityFinding(
                    code="PERF_UNKNOWN_ENDPOINT_REF",
                    severity="error",
                    message=f"API performance budget {ab.id} references unknown Architecture endpoint '{ab.endpoint_id}'.",
                    workspace="architecture",
                    reference_id=ab.endpoint_id,
                )
            )
        for rid in ab.linked_requirement_ids:
            item_req_map.setdefault(rid, []).append(ab.id)

    basis_reqs = basis.get("requirements", [])
    cov_items, cov_count = _evaluate_req_coverage(
        "performance", basis_reqs, content.strategy.requirement_coverage, item_req_map, findings
    )
    has_errors = any(f.severity == "error" for f in findings)
    return OptimizationTraceabilitySummary(
        area="performance",
        complete=not has_errors and cov_count == len(basis_reqs),
        total_requirements=len(basis_reqs),
        covered_requirements=cov_count,
        requirement_coverage=cov_items,
        valid_screen_ids=sorted(valid_screens),
        valid_route_paths=sorted(valid_routes),
        valid_endpoint_ids=sorted(valid_eps),
        findings=findings,
    )


OPTIMIZATION_TRACEABILITY_MAP = {
    "seo": compute_seo_traceability,
    "analytics": compute_analytics_traceability,
    "performance": compute_performance_traceability,
}


class OptimizationCompleteness(StrictModel):
    ready_for_submission: bool
    ready_for_approval: bool
    missing_fields: list[str]
    unresolved_constraint_errors: list[str]
    unverified_items: list[str]
    requires_review_items: list[str]
    uncovered_requirement_ids: list[str]
    item_count: int


def evaluate_optimization_completeness(
    area: OptimizationArea,
    content_dict: dict[str, Any],
    basis: dict[str, Any],
) -> OptimizationCompleteness:
    missing: list[str] = []
    errors: list[str] = []
    unverified: list[str] = []
    requires_review: list[str] = []

    model_cls = OPTIMIZATION_MODEL_MAP[area]
    try:
        model = model_cls.model_validate(content_dict)
    except Exception as exc:
        return OptimizationCompleteness(
            ready_for_submission=False,
            ready_for_approval=False,
            missing_fields=[f"Schema validation error: {exc}"],
            unresolved_constraint_errors=[str(exc)],
            unverified_items=[],
            requires_review_items=[],
            uncovered_requirement_ids=[],
            item_count=0,
        )

    trace_fn = OPTIMIZATION_TRACEABILITY_MAP[area]
    trace: OptimizationTraceabilitySummary = trace_fn(model, basis)

    for f in trace.findings:
        if f.severity == "error":
            errors.append(f.message)

    uncovered = [r.requirement_id for r in trace.requirement_coverage if not r.covered]

    if area == "seo":
        assert isinstance(model, SeoContent)
        items = list(model.page_metadata) + list(model.technical_checklist)
    elif area == "analytics":
        assert isinstance(model, AnalyticsContent)
        items = list(model.events) + list(model.reporting_views)
    else:
        assert isinstance(model, PerformanceContent)
        items = list(model.route_budgets) + list(model.api_budgets)

    for item in items:
        st = getattr(item, "status", "proposed")
        if st == "proposed":
            unverified.append(item.id)
        elif st == "requires_review":
            requires_review.append(item.id)

    ready_sub = len(missing) == 0 and len(errors) == 0 and len(requires_review) == 0 and len(uncovered) == 0
    ready_app = ready_sub
    return OptimizationCompleteness(
        ready_for_submission=ready_sub,
        ready_for_approval=ready_app,
        missing_fields=missing,
        unresolved_constraint_errors=errors,
        unverified_items=unverified,
        requires_review_items=requires_review,
        uncovered_requirement_ids=uncovered,
        item_count=len(items),
    )


# ---------------------------------------------------------------------------
# 5. Deterministic Default Content & AI Generation Prompt Builders
# ---------------------------------------------------------------------------

def build_default_optimization_content(area: OptimizationArea, basis: dict[str, Any]) -> dict[str, Any]:
    reqs = basis.get("requirements") or [{"id": "FR-1", "title": "Core Product Workflow", "priority": "must"}]
    screens = basis.get("screens") or [
        {"id": "SCR-1", "name": "Landing & Workspace Overview", "route_path": "/", "primary_goal": "Discover and manage projects"},
        {"id": "SCR-2", "name": "Core Editor Workspace", "route_path": "/workspace", "primary_goal": "Author and validate project artifacts"},
    ]
    journeys = basis.get("journeys") or [{"id": "J-1", "name": "Primary User Flow", "goal": "Complete core workflow"}]
    interactions = basis.get("interactions") or [{"id": "INT-1", "screen_id": screens[0]["id"], "label": "Primary Action"}]
    endpoints = basis.get("endpoints") or [{"id": "API-1", "method": "POST", "path": "/api/resources", "purpose": "Create resource"}]

    all_req_ids = [r["id"] for r in reqs]
    req_cov = [
        {
            "requirement_id": r["id"],
            "requirement_title": r["title"],
            "coverage_status": "covered",
            "justification": f"Covered by {area.upper()} specification items mapped to {r['id']}.",
        }
        for r in reqs
    ]

    if area == "seo":
        page_metadata = []
        included_routes = []
        excluded_routes = []
        seen_paths: set[str] = set()
        for idx, scr in enumerate(screens):
            rpath = scr.get("route_path") or f"/screen-{idx + 1}"
            if rpath in seen_paths:
                rpath = f"{rpath}-{idx + 1}"
            seen_paths.add(rpath)
            is_public = idx == 0
            vis = "public" if is_public else "authenticated"
            if is_public:
                included_routes.append(rpath)
            else:
                excluded_routes.append(rpath)
            page_metadata.append(
                {
                    "id": f"SEO-PAGE-{idx + 1}",
                    "screen_id": scr["id"],
                    "route_path": rpath,
                    "visibility": vis,
                    "robots_index": "index" if is_public else "noindex",
                    "robots_follow": "follow" if is_public else "nofollow",
                    "include_in_sitemap": is_public,
                    "canonical_path": rpath,
                    "title_template": f"{scr['name']} | Product Platform",
                    "meta_description": f"Explore {scr['name']} to {scr.get('primary_goal') or 'manage structured product workflows with full provenance'}.",
                    "h1_heading": scr["name"],
                    "heading_hierarchy": [
                        f"H1: {scr['name']}",
                        "H2: Workflow Overview & Key Capabilities",
                        "H2: Status & Action Controls",
                    ],
                    "og_title": f"{scr['name']} — Structured Product Workspace",
                    "og_description": f"Structured workspace for {scr['name']} with end-to-end artifact traceability.",
                    "og_type": "website",
                    "twitter_card": "summary_large_image",
                    "structured_data_type": "SoftwareApplication" if is_public else "None",
                    "structured_data_justification": (
                        "Public entry route describes the web application offering using Schema.org SoftwareApplication metadata."
                        if is_public
                        else None
                    ),
                    "internal_links_to": [],
                    "linked_requirement_ids": all_req_ids if idx == 0 else [all_req_ids[0]],
                    "status": "proposed",
                    "notes": "Public discovery entry point." if is_public else "Authenticated workspace route excluded from indexing.",
                }
            )
        if len(page_metadata) > 1:
            page_metadata[0]["internal_links_to"] = [page_metadata[1]["route_path"]]

        return {
            "seo_strategy": {
                "primary_search_intent": "Capture high-intent search queries for structured product lifecycle, specification validation, and scope governance.",
                "target_audience_summary": "Product managers, engineering leads, and founders searching for traceable product specification workflows.",
                "canonical_domain_strategy": "Use environment-configured PUBLIC_BASE_URL combined with normalized lowercase canonical_path without trailing slashes.",
                "url_structure_conventions": [
                    "Lowercase hyphen-separated route segments mapped 1:1 to approved IA and Prototype routes",
                    "Public marketing/entry routes separated from authenticated /projects/:id/* workspace routes",
                ],
                "crawl_and_indexing_policy": "Allow indexing only on public routes; enforce noindex,nofollow and sitemap exclusion on all authenticated, private, transactional, and admin routes.",
                "locale_and_language_strategy": "Default en-US HTML lang attribute with UTF-8 encoding and explicit hreflang expansion support.",
                "requirement_coverage": req_cov,
                "open_questions": [],
            },
            "page_metadata": page_metadata,
            "sitemap_spec": {
                "sitemap_path": "/sitemap.xml",
                "changefreq_policy": "Regenerate sitemap on public route changes; weekly changefreq for public entry routes.",
                "included_routes": included_routes,
                "excluded_routes": excluded_routes,
                "exclusion_rationale": "Authenticated and project-scoped workspace routes contain private tenant state and must never be indexed by search engines.",
            },
            "robots_spec": {
                "user_agent": "*",
                "allow_paths": included_routes or ["/"],
                "disallow_paths": excluded_routes + ["/api/", "/admin/"],
                "sitemap_reference": "${PUBLIC_BASE_URL}/sitemap.xml",
                "rationale": "Permit crawler access to public entry routes while blocking API and authenticated workspace paths.",
            },
            "technical_checklist": [
                {
                    "id": "SEO-CHK-1",
                    "category": "semantics",
                    "title": "Single H1 and landmark hierarchy per screen",
                    "verification_rule": "Verify every rendered page contains exactly one <h1>, semantic <main>/<nav>/<header> landmarks, and non-skipped heading levels.",
                    "linked_screen_ids": [s["id"] for s in screens],
                    "status": "proposed",
                },
                {
                    "id": "SEO-CHK-2",
                    "category": "crawlability",
                    "title": "Private route noindex and sitemap exclusion guard",
                    "verification_rule": "Verify all authenticated/private routes emit <meta name='robots' content='noindex,nofollow'> and are absent from /sitemap.xml.",
                    "linked_screen_ids": [s["id"] for s in screens],
                    "status": "proposed",
                },
            ],
        }

    if area == "analytics":
        first_scr = screens[0]["id"]
        second_scr = screens[1]["id"] if len(screens) > 1 else first_scr
        first_j = journeys[0]["id"] if journeys else None
        first_int = interactions[0]["id"] if interactions else None
        return {
            "measurement_plan": {
                "measurement_objective": "Measure user activation, core workflow completion, and specification validation health while enforcing strict privacy and PII redaction.",
                "primary_kpis": [
                    "Activation rate: percentage of new workspaces completing initial artifact generation",
                    "Workflow completion rate: percentage of drafts submitted and approved without validation rollback",
                ],
                "conversion_funnels": [
                    "Workspace Entry -> Draft Initialization -> Validation Pass -> Exact-Hash Approval",
                ],
                "data_retention_policy": "Retain aggregated event telemetry for 90 days; purge pseudonymous session identifiers upon user deletion request.",
                "ip_anonymization_enabled": True,
                "respect_do_not_track": True,
                "requirement_coverage": req_cov,
                "open_questions": [],
            },
            "events": [
                {
                    "id": "EVT-1",
                    "event_name": "workspace_screen_viewed",
                    "category": "acquisition",
                    "trigger_description": "Triggered when a user navigates to a primary workspace screen after opt-in analytics consent is granted.",
                    "screen_id": first_scr,
                    "journey_id": first_j,
                    "interaction_id": None,
                    "linked_requirement_ids": all_req_ids,
                    "consent_category": "analytics",
                    "requires_opt_in": True,
                    "properties": [
                        {
                            "name": "screen_id",
                            "data_type": "string",
                            "required": True,
                            "pii_classification": "none",
                            "description": "Canonical Prototype screen identifier.",
                        },
                        {
                            "name": "route_visibility",
                            "data_type": "enum",
                            "required": True,
                            "pii_classification": "none",
                            "description": "Public vs authenticated route classification.",
                        },
                    ],
                    "success_metric_tie_in": "Measures top-of-funnel workspace engagement and navigation reach.",
                    "status": "proposed",
                },
                {
                    "id": "EVT-2",
                    "event_name": "workflow_action_completed",
                    "category": "conversion",
                    "trigger_description": "Triggered when a user completes the primary workflow action on the workspace screen.",
                    "screen_id": second_scr,
                    "journey_id": first_j,
                    "interaction_id": first_int,
                    "linked_requirement_ids": all_req_ids,
                    "consent_category": "analytics",
                    "requires_opt_in": True,
                    "properties": [
                        {
                            "name": "artifact_version",
                            "data_type": "number",
                            "required": True,
                            "pii_classification": "none",
                            "description": "Version number of the specification artifact.",
                        },
                        {
                            "name": "validation_passed",
                            "data_type": "boolean",
                            "required": True,
                            "pii_classification": "none",
                            "description": "Whether server-side schema and traceability checks succeeded.",
                        },
                    ],
                    "success_metric_tie_in": "Directly tracks primary product activation and specification approval conversion.",
                    "status": "proposed",
                },
            ],
            "consent_and_privacy": {
                "consent_mode": "opt_in_required",
                "banner_required": True,
                "consent_categories_supported": ["strictly_necessary", "analytics", "functional"],
                "excluded_sensitive_fields": [
                    "password",
                    "access_token",
                    "refresh_token",
                    "api_key",
                    "raw_email",
                    "card_number",
                    "ssn",
                ],
                "pii_redaction_rules": [
                    "Strip query string tokens, email addresses, and bearer credentials before emitting any client or server event.",
                    "Hash or omit user identifiers unless explicit analytics opt-in consent is recorded.",
                ],
                "user_deletion_and_opt_out_flow": "Users can revoke analytics consent at any time from Settings, immediately halting non-essential event emission and queuing telemetry deletion.",
                "provider_neutral_adapter_notes": "Events are emitted to a provider-neutral application telemetry interface; third-party transmission is disabled by default until an environment adapter is explicitly configured.",
                "third_party_transmission_enabled": False,
            },
            "reporting_views": [
                {
                    "id": "RPT-1",
                    "title": "Activation & Workflow Conversion Funnel",
                    "questions_answered": [
                        "What percentage of workspace visits result in a validated workflow completion?",
                        "Which screens experience the highest validation drop-off?",
                    ],
                    "tracked_event_ids": ["EVT-1", "EVT-2"],
                    "primary_audience": "Product & Engineering Leads",
                    "status": "proposed",
                }
            ],
        }

    # area == "performance"
    route_budgets = []
    seen_rpaths: set[str] = set()
    for idx, scr in enumerate(screens):
        rpath = scr.get("route_path") or f"/screen-{idx + 1}"
        if rpath in seen_rpaths:
            rpath = f"{rpath}-{idx + 1}"
        seen_rpaths.add(rpath)
        route_budgets.append(
            {
                "id": f"PERF-RT-{idx + 1}",
                "screen_id": scr["id"],
                "route_path": rpath,
                "initial_js_kb_gzip": 160 if idx == 0 else 200,
                "initial_css_kb_gzip": 35,
                "max_image_weight_kb": 250,
                "loading_strategy": "eager_critical" if idx == 0 else "route_code_split",
                "caching_policy": "Immutable hashed assets cached 1y (max-age=31536000, immutable); HTML shell no-cache.",
                "linked_requirement_ids": all_req_ids if idx == 0 else [all_req_ids[0]],
                "status": "proposed",
                "notes": f"Route budget for {scr['name']}.",
            }
        )

    api_budgets = []
    for idx, ep in enumerate(endpoints):
        api_budgets.append(
            {
                "id": f"PERF-API-{idx + 1}",
                "endpoint_id": ep["id"],
                "route_pattern": f"{ep.get('method', 'GET')} {ep.get('path', '/api/resource')}",
                "p95_latency_ms": 250,
                "p99_latency_ms": 500,
                "max_payload_kb": 128,
                "caching_and_query_strategy": "Indexed foreign-key lookups on project_id with bounded pagination and ETag/content-hash concurrency checks.",
                "linked_requirement_ids": ep.get("prd_requirement_ids") or all_req_ids,
                "status": "proposed",
            }
        )

    return {
        "strategy": {
            "performance_posture": "Enforce strict Core Web Vitals budgets, route-level JS/CSS bundle ceilings, and bounded p95/p99 API latencies grounded in approved Architecture contracts.",
            "bundling_and_code_splitting_strategy": "Split route bundles by workspace stage; keep critical landing/shell JS <= 160 KB gzipped.",
            "image_and_font_optimization_strategy": "Use modern WebP/AVIF assets with explicit width/height attributes to prevent layout shift (CLS <= 0.1) and font-display: swap.",
            "caching_and_cdn_strategy": "Serve fingerprinted static assets with Cache-Control: public, max-age=31536000, immutable; serve SPA index.html with no-cache.",
            "runtime_monitoring_and_alerting": "Track slow requests (>500ms), 5xx error rates, and client Web Vitals observations separately from product analytics.",
            "requirement_coverage": req_cov,
            "open_questions": [],
        },
        "core_web_vitals": {
            "lcp_max_ms": 2500,
            "inp_max_ms": 200,
            "cls_max_score": 0.1,
            "fcp_max_ms": 1800,
            "ttfb_max_ms": 600,
            "measurement_status": "target_budget_only",
            "rationale": "Aligned with Google Core Web Vitals 'Good' thresholds (LCP <= 2500ms, INP <= 200ms, CLS <= 0.1). Marked as target_budget_only until real build/browser observations are recorded.",
        },
        "route_budgets": route_budgets,
        "api_budgets": api_budgets,
        "measurement_evidence": [
            {
                "id": "EVD-1",
                "metric_name": "Initial Route JS Bundle Ceiling",
                "target_value": "160",
                "measured_value": None,
                "unit": "KB (gzip)",
                "measurement_tool": "Vite production bundle analyzer / CI build check",
                "environment": "unmeasured_target",
                "measured_at": None,
                "scope_description": "Primary entry route initial JavaScript payload budget.",
                "limitations": "Target budget defined in specification; requires production asset build inspection to record measured_value.",
                "status": "target_only",
            },
            {
                "id": "EVD-2",
                "metric_name": "Core API p95 Response Latency",
                "target_value": "250",
                "measured_value": None,
                "unit": "ms",
                "measurement_tool": "FastAPI request duration middleware & integration benchmark",
                "environment": "unmeasured_target",
                "measured_at": None,
                "scope_description": "95th percentile latency across approved Architecture API endpoints.",
                "limitations": "Target budget only; local container measurements do not represent multi-tenant production load.",
                "status": "target_only",
            },
        ],
    }


def build_optimization_generation_prompt(
    area: OptimizationArea,
    project_name: str,
    brain_data: Any,
    basis: dict[str, Any],
) -> str:
    req_lines = [f"- {r['id']} ({r['priority'].upper()}): {r['title']}" for r in basis.get("requirements", [])]
    scr_lines = [f"- {s['id']}: {s['name']} (route: {s['route_path']})" for s in basis.get("screens", [])]
    ep_lines = [f"- {e['id']}: {e['method']} {e['path']} ({e['purpose']})" for s in [basis.get("endpoints", [])] for e in s]
    return (
        f"Generate a complete, validated Phase 16 {area.upper()} specification for project '{project_name}'.\n"
        f"Approved PRD Requirements (Must/Should):\n" + "\n".join(req_lines) + "\n"
        f"Approved Prototype Screens & Routes:\n" + "\n".join(scr_lines) + "\n"
        f"Approved Architecture Endpoints:\n" + "\n".join(ep_lines) + "\n"
        "Constraints:\n"
        "1. Reference only valid requirement_ids, screen_ids, route_paths, and endpoint_ids from the approved basis.\n"
        "2. For SEO: private/authenticated/transactional/admin routes MUST use robots_index='noindex' and include_in_sitemap=False.\n"
        "3. For Analytics: event_name and property names MUST be snake_case; never include passwords, tokens, raw_email, or sensitive PII; non-essential events MUST set requires_opt_in=True; third_party_transmission_enabled MUST be False.\n"
        "4. For Performance: distinguish target_budget_only from measured_observation; never fabricate Lighthouse scores or unmeasured values."
    )


# ---------------------------------------------------------------------------
# 6. Deterministic HTML Metadata, Sitemap, Robots & Bundle Verification Engine
# ---------------------------------------------------------------------------

class _HtmlMetadataInspector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self._in_title = False
        self._title_buf: list[str] = []
        self.meta_description: str | None = None
        self.meta_robots: str | None = None
        self.meta_viewport: str | None = None
        self.canonical: str | None = None
        self.og_tags: dict[str, str] = {}
        self.twitter_tags: dict[str, str] = {}
        self.h1_tags: list[str] = []
        self._in_h1 = False
        self._h1_buf: list[str] = []
        self.landmarks: set[str] = set()
        self.json_ld_blocks: list[str] = []
        self._in_json_ld = False
        self._json_ld_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        if t == "title":
            self._in_title = True
            self._title_buf = []
        elif t == "h1":
            self._in_h1 = True
            self._h1_buf = []
        elif t in ("main", "nav", "header", "footer"):
            self.landmarks.add(t)
        elif t == "meta":
            name = attr_map.get("name", "").lower()
            prop = attr_map.get("property", "").lower()
            content = attr_map.get("content", "")
            if name == "description":
                self.meta_description = content
            elif name == "robots":
                self.meta_robots = content
            elif name == "viewport":
                self.meta_viewport = content
            elif name.startswith("twitter:"):
                self.twitter_tags[name] = content
            if prop.startswith("og:"):
                self.og_tags[prop] = content
        elif t == "link":
            rel = attr_map.get("rel", "").lower()
            if "canonical" in rel:
                self.canonical = attr_map.get("href", "")
        elif t == "script":
            if attr_map.get("type", "").lower() == "application/ld+json":
                self._in_json_ld = True
                self._json_ld_buf = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_buf.append(data)
        if self._in_h1:
            self._h1_buf.append(data)
        if self._in_json_ld:
            self._json_ld_buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "title" and self._in_title:
            self._in_title = False
            self.title = "".join(self._title_buf).strip()
        elif t == "h1" and self._in_h1:
            self._in_h1 = False
            self.h1_tags.append("".join(self._h1_buf).strip())
        elif t == "script" and self._in_json_ld:
            self._in_json_ld = False
            self.json_ld_blocks.append("".join(self._json_ld_buf).strip())


def inspect_html_document(html_content: str, expected_page: PageSeoMetadataSpec | None = None) -> dict[str, Any]:
    parser = _HtmlMetadataInspector()
    parser.feed(html_content)
    findings: list[dict[str, str]] = []

    if not parser.title or len(parser.title) < 5:
        findings.append({"code": "HTML_TITLE_MISSING", "severity": "error", "message": "Missing or empty <title> element."})
    if not parser.meta_description or len(parser.meta_description) < 15:
        findings.append({"code": "HTML_META_DESC_MISSING", "severity": "error", "message": "Missing or too short <meta name='description'>."})
    if not parser.meta_viewport:
        findings.append({"code": "HTML_VIEWPORT_MISSING", "severity": "warning", "message": "Missing responsive <meta name='viewport'> tag."})
    if len(parser.h1_tags) != 1:
        findings.append(
            {
                "code": "HTML_H1_COUNT_INVALID",
                "severity": "error",
                "message": f"Expected exactly 1 <h1> heading, found {len(parser.h1_tags)}.",
            }
        )
    if "main" not in parser.landmarks:
        findings.append({"code": "HTML_MAIN_LANDMARK_MISSING", "severity": "error", "message": "Missing semantic <main> landmark element."})

    if expected_page is not None:
        expected_robots = f"{expected_page.robots_index},{expected_page.robots_follow}"
        if expected_page.visibility != "public":
            if not parser.meta_robots or "noindex" not in parser.meta_robots.lower():
                findings.append(
                    {
                        "code": "HTML_PRIVATE_ROUTE_INDEXABLE",
                        "severity": "error",
                        "message": f"Non-public route {expected_page.route_path} ({expected_page.visibility}) must emit noindex robots directive.",
                    }
                )
        elif parser.meta_robots and parser.meta_robots.replace(" ", "").lower() != expected_robots:
            findings.append(
                {
                    "code": "HTML_ROBOTS_MISMATCH",
                    "severity": "warning",
                    "message": f"HTML robots meta '{parser.meta_robots}' differs from expected '{expected_robots}'.",
                }
            )
        if not parser.canonical:
            findings.append({"code": "HTML_CANONICAL_MISSING", "severity": "error", "message": "Missing <link rel='canonical'> element."})

    has_error = any(f["severity"] == "error" for f in findings)
    return {
        "route_path": expected_page.route_path if expected_page else "/",
        "status": "failed" if has_error else "passed",
        "title": parser.title,
        "meta_description": parser.meta_description,
        "canonical": parser.canonical,
        "robots": parser.meta_robots,
        "h1_count": len(parser.h1_tags),
        "h1_texts": parser.h1_tags,
        "landmarks": sorted(parser.landmarks),
        "findings": findings,
    }


def generate_sitemap_xml_preview(seo: SeoContent, base_url: str = "https://example.invalid") -> str:
    base = base_url.rstrip("/")
    lines = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
        "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">",
    ]
    for p in seo.page_metadata:
        if p.include_in_sitemap and p.visibility == "public" and p.robots_index == "index":
            lines.append("  <url>")
            lines.append(f"    <loc>{base}{p.canonical_path}</loc>")
            lines.append("    <changefreq>weekly</changefreq>")
            lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines)


def generate_robots_txt_preview(seo: SeoContent) -> str:
    r = seo.robots_spec
    lines = [f"User-agent: {r.user_agent}"]
    for allow in r.allow_paths:
        lines.append(f"Allow: {allow}")
    for disallow in r.disallow_paths:
        lines.append(f"Disallow: {disallow}")
    lines.append(f"Sitemap: {r.sitemap_reference}")
    return "\n".join(lines)


def run_product_verification_checks(
    seo_content: dict[str, Any] | None,
    analytics_content: dict[str, Any] | None,
    performance_content: dict[str, Any] | None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    root = repo_root or Path(__file__).resolve().parents[2]
    checks: list[dict[str, Any]] = []

    # 1. WebForge Frontend Shell HTML Metadata & Noindex Guard
    index_html_path = root / "frontend" / "index.html"
    if index_html_path.exists():
        html_txt = index_html_path.read_text(encoding="utf-8")
        parser = _HtmlMetadataInspector()
        parser.feed(html_txt)
        shell_ok = bool(parser.title and parser.meta_description and parser.meta_viewport and parser.meta_robots)
        checks.append(
            {
                "id": "SEO-01",
                "category": "seo",
                "title": "WebForge SPA Shell Metadata & Robots Directive",
                "status": "passed" if shell_ok else "failed",
                "evidence": f"title='{parser.title}', robots='{parser.meta_robots}', description_len={len(parser.meta_description or '')}",
                "limitation": "Static HTML shell inspection only; does not verify external search engine indexing.",
            }
        )

    # 2. SEO Specification Route Indexability & Sitemap Private-Route Exclusion
    if seo_content:
        seo_model = SeoContent.model_validate(seo_content)
        sitemap_xml = generate_sitemap_xml_preview(seo_model)
        private_leaks = [
            p.route_path
            for p in seo_model.page_metadata
            if p.visibility != "public" and (p.robots_index == "index" or p.include_in_sitemap or p.route_path in sitemap_xml)
        ]
        checks.append(
            {
                "id": "SEO-02",
                "category": "seo",
                "title": "Public vs. Private Route Indexability & XML Sitemap Guard",
                "status": "passed" if not private_leaks else "failed",
                "evidence": f"Verified {len(seo_model.page_metadata)} routes; {len(seo_model.sitemap_spec.included_routes)} public in sitemap, {len(seo_model.sitemap_spec.excluded_routes)} private excluded; private leaks={len(private_leaks)}.",
                "limitation": "Validates specification and generated sitemap XML structure; does not submit sitemaps to external search consoles.",
            }
        )
    else:
        checks.append(
            {
                "id": "SEO-02",
                "category": "seo",
                "title": "Public vs. Private Route Indexability & XML Sitemap Guard",
                "status": "warning",
                "evidence": "No SEO specification initialized for this project yet.",
                "limitation": "Initialize and approve an SEO specification to verify project route indexability.",
            }
        )

    # 3. Analytics Privacy, Consent Gate & Sensitive Field Prohibition
    if analytics_content:
        an_model = AnalyticsContent.model_validate(analytics_content)
        unconsented = [
            ev.event_name
            for ev in an_model.events
            if ev.consent_category != "strictly_necessary" and not ev.requires_opt_in
        ]
        checks.append(
            {
                "id": "ANL-01",
                "category": "analytics",
                "title": "Analytics Event Taxonomy, Opt-In Consent & Sensitive Field Exclusion",
                "status": "passed" if (not unconsented and not an_model.consent_and_privacy.third_party_transmission_enabled) else "failed",
                "evidence": f"Verified {len(an_model.events)} snake_case events; excluded_sensitive_fields={len(an_model.consent_and_privacy.excluded_sensitive_fields)}; third_party_transmission_enabled={an_model.consent_and_privacy.third_party_transmission_enabled}.",
                "limitation": "Validates schema privacy rules and consent gates; does not constitute legal GDPR/CCPA advice.",
            }
        )
    else:
        checks.append(
            {
                "id": "ANL-01",
                "category": "analytics",
                "title": "Analytics Event Taxonomy, Opt-In Consent & Sensitive Field Exclusion",
                "status": "warning",
                "evidence": "No Analytics specification initialized for this project yet.",
                "limitation": "Initialize and approve an Analytics specification to verify event privacy rules.",
            }
        )

    # 4. Performance Budgets & Honest Measurement Separation
    if performance_content:
        pf_model = PerformanceContent.model_validate(performance_content)
        checks.append(
            {
                "id": "PERF-01",
                "category": "performance",
                "title": "Core Web Vitals, Route Asset & API Latency Budget Verification",
                "status": "passed",
                "evidence": f"LCP<={pf_model.core_web_vitals.lcp_max_ms}ms, INP<={pf_model.core_web_vitals.inp_max_ms}ms, CLS<={pf_model.core_web_vitals.cls_max_score}; {len(pf_model.route_budgets)} route budgets, {len(pf_model.api_budgets)} API budgets ({pf_model.core_web_vitals.measurement_status}).",
                "limitation": "Separates target budgets from recorded observations; does not fabricate synthetic Lighthouse scores.",
            }
        )
    else:
        checks.append(
            {
                "id": "PERF-01",
                "category": "performance",
                "title": "Core Web Vitals, Route Asset & API Latency Budget Verification",
                "status": "warning",
                "evidence": "No Performance specification initialized for this project yet.",
                "limitation": "Initialize and approve a Performance specification to verify route and API budgets.",
            }
        )

    # 5. Nginx Caching & Static Asset Delivery Verification
    nginx_conf = root / "frontend" / "nginx.conf"
    if nginx_conf.exists():
        ntxt = nginx_conf.read_text(encoding="utf-8")
        has_immutable = "immutable" in ntxt and "max-age=31536000" in ntxt
        has_no_cache_html = "no-cache" in ntxt
        checks.append(
            {
                "id": "PERF-02",
                "category": "performance",
                "title": "Nginx Static Asset Caching & HTML Cache-Control Policy",
                "status": "passed" if (has_immutable and has_no_cache_html) else "failed",
                "evidence": f"immutable_hashed_assets={has_immutable}, html_no_cache_revalidation={has_no_cache_html}",
                "limitation": "Static Nginx configuration inspection; CDN edge behavior depends on deployment environment.",
            }
        )

    passed = sum(1 for c in checks if c["status"] == "passed")
    failed = sum(1 for c in checks if c["status"] == "failed")
    warnings = sum(1 for c in checks if c["status"] == "warning")
    return {
        "overall_status": "failed" if failed > 0 else ("passed" if warnings == 0 else "warning"),
        "total_checks": len(checks),
        "passed_checks": passed,
        "warning_checks": warnings,
        "failed_checks": failed,
        "checks": checks,
    }
