import type { StageStatus } from "./lifecycle";
import type { DocStatus } from "./strategy";

export type UxArtifactType = "personas" | "journeys" | "ia" | "wireframes" | "ux_review";
export type PersonaEvidenceStatus = "evidence_backed" | "mixed" | "hypothesis";
export type NavGroup = "primary" | "secondary" | "utility" | "contextual";
export type ComponentKind = "nav_bar" | "hero" | "section_header" | "card_grid" | "data_table" | "form" | "action_bar" | "callout" | "empty_state" | "status_banner";
export type RegionKind = "header" | "navigation" | "main" | "sidebar" | "footer" | "modal";
export type ViewportKind = "desktop" | "tablet" | "mobile" | "responsive";
export type FindingSeverity = "critical" | "high" | "medium" | "low";
export type FindingCategory = "prd_coverage" | "task_navigation" | "consistency" | "responsive" | "accessibility" | "error_recovery" | "ui_states" | "missing_requirement" | "unsupported_assumption" | "traceability";
export type FindingStatus = "open" | "accepted" | "resolved" | "needs_evidence";
export type AffectedArtifact = "personas" | "journeys" | "ia" | "wireframes" | "cross_artifact";

export interface UxBasisSummary {
  research_version: number;
  strategy_version: number;
  prd_version: number;
  personas_version: number | null;
  journeys_version: number | null;
  ia_version: number | null;
  wireframes_version: number | null;
  valid_req_ids: string[];
  valid_story_ids: string[];
  valid_evidence_refs: string[];
  confirmed_evidence_refs: string[];
  valid_persona_ids: string[];
  valid_journey_ids: string[];
  valid_ia_node_ids: string[];
  valid_wireframe_ids: string[];
}

export interface Persona {
  id: string;
  name: string;
  segment: string;
  context: string;
  goals: string[];
  tasks_behaviors: string[];
  needs_pain_points: string[];
  frustrations_barriers: string[];
  accessibility_device_notes: string[];
  motivations: string[];
  user_story_ids: string[];
  prd_requirement_ids: string[];
  evidence_refs: string[];
  unverified_assumptions: string[];
  evidence_status: PersonaEvidenceStatus;
  needs_evidence: boolean;
  origin: "ai" | "user";
  edited_by_user: boolean;
  note: string | null;
}

export interface PersonasContent {
  basis: UxBasisSummary;
  personas: Persona[];
  limitations: string[];
}

export interface JourneyStage {
  stage_number: number;
  stage_name: string;
  user_actions: string[];
  thoughts_questions: string[];
  thoughts_status: "hypothesis" | "evidence_backed";
  touchpoints: string[];
  pain_points: string[];
  system_responses: string[];
  failure_recovery_paths: string[];
}

export interface UserJourney {
  id: string;
  title: string;
  persona_id: string;
  scenario: string;
  desired_outcome: string;
  entry_point: string;
  preconditions: string[];
  stages: JourneyStage[];
  accessibility_considerations: string[];
  prd_requirement_ids: string[];
  opportunities: string[];
  unresolved_questions: string[];
  origin: "ai" | "user";
  edited_by_user: boolean;
}

export interface JourneysContent {
  basis: UxBasisSummary;
  journeys: UserJourney[];
  limitations: string[];
}

export interface IaNavigationModel {
  primary_nav: string[];
  secondary_nav: string[];
  utility_nav: string[];
}

export interface IaNode {
  id: string;
  name: string;
  path: string;
  parent_id: string | null;
  order: number;
  purpose: string;
  navigation_group: NavGroup;
  content_groups: string[];
  key_actions: string[];
  access_role: string;
  prd_requirement_ids: string[];
  origin: "ai" | "user";
  edited_by_user: boolean;
}

export interface IaContent {
  basis: UxBasisSummary;
  navigation_model: IaNavigationModel;
  nodes: IaNode[];
  open_questions: string[];
  assumptions: string[];
  limitations: string[];
}

export interface WireframeComponent {
  id: string;
  kind: ComponentKind;
  label: string;
  content_role: string;
  elements: string[];
}

export interface WireframeRegion {
  region: RegionKind;
  heading: string;
  components: WireframeComponent[];
}

export interface WireframeField {
  name: string;
  field_type: "text" | "textarea" | "select" | "checkbox" | "radio" | "date" | "number";
  required: boolean;
  validation_rule: string;
}

export interface WireframeStates {
  loading: string;
  empty: string;
  error: string;
  success: string;
}

export interface WireframeResponsive {
  desktop: string;
  tablet: string;
  mobile: string;
}

export interface WireframeSpec {
  id: string;
  page_name: string;
  purpose: string;
  ia_node_id: string;
  target_viewport: ViewportKind;
  regions: WireframeRegion[];
  primary_actions: string[];
  secondary_actions: string[];
  form_fields: WireframeField[];
  states: WireframeStates;
  responsive_behavior: WireframeResponsive;
  accessibility_keyboard: string[];
  persona_ids: string[];
  journey_ids: string[];
  prd_requirement_ids: string[];
  origin: "ai" | "user";
  edited_by_user: boolean;
}

export interface WireframesContent {
  basis: UxBasisSummary;
  wireframes: WireframeSpec[];
  limitations: string[];
}

export interface UxReviewFinding {
  id: string;
  severity: FindingSeverity;
  category: FindingCategory;
  affected_artifact: AffectedArtifact;
  affected_version: number;
  affected_item_id: string | null;
  title: string;
  reasoning: string;
  prd_requirement_ids: string[];
  recommended_action: string;
  status: FindingStatus;
  resolution_note: string | null;
  origin: "deterministic" | "ai" | "user";
  edited_by_user: boolean;
}

export interface UxReviewContent {
  basis: UxBasisSummary;
  summary: string;
  findings: UxReviewFinding[];
  limitations: string[];
}

export interface UxSummary {
  version: number;
  status: Exclude<DocStatus, "not_started">;
  artifact_type: UxArtifactType;
  created_via: string;
  parent_version: number | null;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  approved_at: string | null;
  content_hash: string | null;
  item_count: number;
  error: string | null;
}

export interface UxDocument<C = unknown> extends UxSummary {
  id: string;
  content: C | null;
  basis: Record<string, unknown>;
  approval_note: string | null;
  acknowledged_unverified: boolean;
  brain_revision: number | null;
  unverified_count: number;
  critical_open_count: number;
  review_counts: {
    total: number;
    critical_open: number;
    open: number;
    needs_evidence: number;
    accepted: number;
    resolved: number;
    deterministic: number;
    ai: number;
    user: number;
  } | null;
  is_stale: boolean;
  stale_reasons: string[];
  editable: boolean;
  warnings: { code: string; message: string }[];
}

export interface UxPrerequisites {
  ready: boolean;
  missing: { artifact: string; label: string; message: string; workspace_path: string }[];
  upstream_versions: Record<string, number | null>;
}

export interface UxArtifactState<C = unknown> {
  artifact_type: UxArtifactType;
  status: DocStatus;
  prerequisites: UxPrerequisites;
  is_stale: boolean;
  stale_reasons: string[];
  current: UxDocument<C> | null;
  approved_version: number | null;
  history: UxSummary[];
  last_error: string | null;
  basis_preview: UxBasisSummary | null;
  lifecycle: {
    stage: "ux";
    status: StageStatus;
    ux_complete: boolean;
    pending_criteria: string[];
  };
  next_step: { key: string; label: string; workspace_path?: string };
  can_generate: boolean;
  needs_supersede: boolean;
  can_submit: boolean;
  can_approve: boolean;
  limitations: string[];
}

export interface UxEditResponse<C = unknown> {
  document: UxDocument<C>;
  state: UxArtifactState<C>;
}
