import type { ArtifactStatus, GenerationSource, UpstreamWarning } from "./research";

export type OptimizationArea = "seo" | "analytics" | "performance";
export type OptimizationItemStatus = "proposed" | "confirmed" | "requires_review";

export interface RequirementCoverageEntry {
  requirement_id: string;
  requirement_title: string;
  coverage_status: "covered" | "not_applicable";
  justification?: string | null;
}

export interface SeoStrategySummary {
  primary_search_intent: string;
  target_audience_summary: string;
  canonical_domain_strategy: string;
  url_structure_conventions: string[];
  crawl_and_indexing_policy: string;
  locale_and_language_strategy: string;
  requirement_coverage: RequirementCoverageEntry[];
  open_questions: string[];
}

export interface PageSeoMetadataSpec {
  id: string;
  screen_id: string;
  route_path: string;
  visibility: "public" | "private" | "authenticated" | "transactional" | "admin";
  robots_index: "index" | "noindex";
  robots_follow: "follow" | "nofollow";
  include_in_sitemap: boolean;
  canonical_path: string;
  title_template: string;
  meta_description: string;
  h1_heading: string;
  heading_hierarchy: string[];
  og_title: string;
  og_description: string;
  og_type: "website" | "article" | "product" | "profile";
  twitter_card: "summary" | "summary_large_image";
  structured_data_type: "None" | "WebSite" | "SoftwareApplication" | "Organization" | "FAQPage" | "BreadcrumbList" | "Product";
  structured_data_Justification?: string | null;
  internal_links_to: string[];
  linked_requirement_ids: string[];
  status: OptimizationItemStatus;
  notes?: string | null;
}

export interface SitemapDirectiveSpec {
  sitemap_path: string;
  changefreq_policy: string;
  included_routes: string[];
  excluded_routes: string[];
  exclusion_rationale: string;
}

export interface RobotsDirectiveSpec {
  user_agent: string;
  allow_paths: string[];
  disallow_paths: string[];
  sitemap_Reference: string;
  rationale: string;
}

export interface TechnicalSeoChecklistItem {
  id: string;
  category: "semantics" | "accessibility" | "canonicals" | "links" | "structured_data" | "crawlability";
  title: string;
  verification_rule: string;
  linked_screen_ids: string[];
  status: OptimizationItemStatus;
}

export interface SeoContent {
  seo_strategy: SeoStrategySummary;
  page_metadata: PageSeoMetadataSpec[];
  sitemap_spec: SitemapDirectiveSpec;
  robots_spec: RobotsDirectiveSpec;
  technical_checklist: TechnicalSeoChecklistItem[];
}

export interface AnalyticsMeasurementPlan {
  measurement_objective: string;
  primary_kpis: string[];
  conversion_funnels: string[];
  data_retention_policy: string;
  ip_anonymization_enabled: boolean;
  respect_do_not_track: boolean;
  requirement_coverage: RequirementCoverageEntry[];
  open_questions: string[];
}

export interface EventPropertySchema {
  name: string;
  data_type: "string" | "number" | "boolean" | "enum";
  required: boolean;
  pii_classification: "none" | "pseudonymous_id";
  description: string;
}

export interface AnalyticsEventSpec {
  id: string;
  event_name: string;
  category: "acquisition" | "activation" | "engagement" | "conversion" | "retention" | "system_error";
  trigger_description: string;
  screen_id: string;
  journey_id?: string | null;
  interaction_id?: string | null;
  linked_requirement_ids: string[];
  consent_category: "strictly_necessary" | "analytics" | "functional" | "marketing";
  requires_opt_in: boolean;
  properties: EventPropertySchema[];
  success_metric_tie_in: string;
  status: OptimizationItemStatus;
}

export interface ConsentPrivacyRequirement {
  consent_mode: "opt_in_required" | "essential_only";
  banner_required: boolean;
  consent_categories_supported: string[];
  excluded_sensitive_fields: string[];
  pii_redaction_rules: string[];
  user_deletion_and_opt_out_flow: string;
  provider_neutral_adapter_notes: string;
  third_party_transmission_enabled: boolean;
}

export interface ReportingDiagnosticSpec {
  id: string;
  title: string;
  questions_answered: string[];
  tracked_event_ids: string[];
  primary_audience: string;
  status: OptimizationItemStatus;
}

export interface AnalyticsContent {
  measurement_plan: AnalyticsMeasurementPlan;
  events: AnalyticsEventSpec[];
  consent_and_privacy: ConsentPrivacyRequirement;
  reporting_views: ReportingDiagnosticSpec[];
}

export interface CoreWebVitalsBudget {
  lcp_max_ms: number;
  inp_max_ms: number;
  cls_max_score: number;
  fcp_max_ms: number;
  ttfb_max_ms: number;
  measurement_status: "target_budget_only" | "measured_observation";
  rationale: string;
}

export interface RouteAssetBudgetSpec {
  id: string;
  screen_id: string;
  route_path: string;
  initial_js_kb_gzip: number;
  initial_css_kb_gzip: number;
  max_image_weight_kb: number;
  loading_strategy: "eager_critical" | "route_code_split" | "lazy_below_fold" | "ssr_stream" | "static_prerender";
  caching_policy: string;
  linked_requirement_ids: string[];
  status: OptimizationItemStatus;
  notes?: string | null;
}

export interface BackendApiPerformanceBudgetSpec {
  id: string;
  endpoint_id: string;
  route_pattern: string;
  p95_latency_ms: number;
  p99_latency_ms: number;
  max_payload_kb: number;
  caching_and_query_strategy: string;
  linked_requirement_ids: string[];
  status: OptimizationItemStatus;
}

export interface PerformanceMeasurementEvidence {
  id: string;
  metric_name: string;
  target_value: string;
  measured_value?: string | null;
  unit: string;
  measurement_tool: string;
  environment: "local_build" | "ci_pipeline" | "staging" | "production" | "unmeasured_target";
  measured_at?: string | null;
  scope_description: string;
  limitations: string;
  status: "target_only" | "measured_pass" | "measured_warn";
}

export interface PerformanceStrategySummary {
  performance_posture: string;
  bundling_and_code_splitting_strategy: string;
  image_and_font_optimization_strategy: string;
  caching_and_cdn_strategy: string;
  runtime_monitoring_and_alerting: string;
  requirement_coverage: RequirementCoverageEntry[];
  open_questions: string[];
}

export interface PerformanceContent {
  strategy: PerformanceStrategySummary;
  core_web_vitals: CoreWebVitalsBudget;
  route_budgets: RouteAssetBudgetSpec[];
  api_budgets: BackendApiPerformanceBudgetSpec[];
  measurement_evidence: PerformanceMeasurementEvidence[];
}

export interface OptimizationDocument {
  id: string;
  project_id: string;
  area: OptimizationArea;
  version: number;
  status: ArtifactStatus;
  supersedes_version: number | null;
  generation_source: GenerationSource;
  ai_Metadata: Record<string, unknown>;
  content: SeoContent | AnalyticsContent | PerformanceContent;
  basis_summary: Record<string, unknown>;
  content_hash: string;
  approval_note: string | null;
  approved_at: string | null;
  approved_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface OptimizationVersionSummary {
  version: number;
  status: ArtifactStatus;
  supersedes_version: number | null;
  generation_source: GenerationSource;
  content_hash: string;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
}

export interface OptimizationCompleteness {
  ready_for_submission: boolean;
  ready_for_approval: boolean;
  missing_fields: string[];
  unresolved_Constraint_errors: string[];
  unverified_items: string[];
  requires_review_items: string[];
  uncovered_requirement_ids: string[];
  item_count: number;
}

export interface RequirementOptimizationCoverageItem {
  requirement_id: string;
  title: string;
  priority: string;
  covered: boolean;
  coverage_status: "covered" | "not_applicable" | "uncovered";
  justification?: string | null;
  mapped_item_ids: string[];
}

export interface OptimizationTraceabilityFinding {
  code: string;
  severity: "error" | "warning" | "info";
  message: string;
  workspace: string;
  reference_id?: string | null;
}

export interface OptimizationTraceabilitySummary {
  area: OptimizationArea;
  complete: boolean;
  total_requirements: number;
  covered_requirements: number;
  requirement_coverage: RequirementOptimizationCoverageItem[];
  Valid_screen_ids: string[];
  valid_route_paths: string[];
  valid_endpoint_ids: string[];
  findings: OptimizationTraceabilityFinding[];
}

export interface PrerequisiteArtifactStatus {
  artifact: string;
  label: string;
  workspace: string;
  approved_version: number | null;
  open_draft_version: number | null;
  ready: boolean;
  blocker_reason?: string | null;
}

export interface OptimizationPrerequisitesStatus {
  ready: boolean;
  blocking_reasons: string[];
  remediation_links: { label: string; workspace: string; reason: string }[];
  artifacts: PrerequisiteArtifactStatus[];
}

export interface OptimizationAreaState {
  area: OptimizationArea;
  stage_key: string;
  stage_status: string;
  prerequisites: OptimizationPrerequisitesStatus;
  current_approved: OptimizationDocument | null;
  current_draft: OptimizationDocument | null;
  versions: OptimizationVersionSummary[];
  completeness: OptimizationCompleteness;
  traceability: OptimizationTraceabilitySummary;
  warnings: UpstreamWarning[];
  sitemap_xml_preview?: string | null;
  robots_txt_preview?: string | null;
}

export interface OptimizationEditResponse {
  state: OptimizationAreaState;
  edited_version: number;
  copied_from_approved: number | null;
}

export interface OptimizationOverviewState {
  seo_stage_status: string;
  analytics_stage_status: string;
  prerequisites: OptimizationPrerequisitesStatus;
  areas: Record<OptimizationArea, OptimizationAreaState>;
  verification: {
    overall_status: string;
    total_checks: number;
    passed_checks: number;
    warning_checks: number;
    failed_checks: number;
    checks: {
      id: string;
      category: string;
      title: string;
      status: string;
      evidence: string;
      limitation: string;
    }[];
  };
}
