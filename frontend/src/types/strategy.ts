import type { StageStatus } from "./lifecycle";

export type RecStatus = "grounded_in_confirmed" | "supported_by_research" | "ai_suggestion" | "hypothesis" | "unsupported";
export type RecArea = "vision" | "goals" | "target_users" | "value_proposition" | "differentiation" | "business_model" | "mvp_scope" | "success_metrics" | "risks";
export type DocStatus = "not_started" | "generating" | "failed" | "draft" | "in_review" | "approved" | "superseded";

export interface StrategyInputItem {
  ref_id: string;
  category: string;
  text: string;
  provenance: "user_confirmed" | "ai_suggestion" | "unresolved_assumption" | "research_finding";
  evidence?: string | null;
}

export interface StrategyInputs {
  product_summary: string;
  confirmed_facts: StrategyInputItem[];
  ai_suggestions: StrategyInputItem[];
  unresolved_assumptions: StrategyInputItem[];
  research_findings: StrategyInputItem[];
  missing_inputs: string[];
  research_version: number | null;
  discovery_status: string;
}

export interface StrategyGoal {
  id: string;
  goal: string;
  rationale: string;
  supporting_refs: string[];
  status: "user_confirmed" | "ai_suggestion" | "unsupported";
}

export interface StrategyTargetUser {
  id: string;
  segment: string;
  needs: string;
  supporting_refs: string[];
  status: "user_confirmed" | "ai_suggestion" | "unsupported";
}

export interface MvpScopeItem {
  id: string;
  item: string;
  boundary: "in_mvp" | "post_mvp" | "out_of_scope";
  rationale: string;
  supporting_refs: string[];
}

export interface SuccessMetric {
  id: string;
  metric: string;
  target_direction: string;
  supporting_refs: string[];
}

export interface StrategyRecommendation {
  id: string;
  area: RecArea;
  title: string;
  recommendation: string;
  rationale: string;
  status: RecStatus;
  supporting_refs: string[];
  needs_evidence: boolean;
  origin: "ai" | "user";
  edited_by_user: boolean;
  note: string | null;
}

export interface StrategyRisk {
  id: string;
  risk: string;
  mitigation: string;
  supporting_refs: string[];
}

export interface OpenDecision {
  id: string;
  question: string;
  impact: string;
}

export interface StrategyContent {
  inputs: StrategyInputs;
  product_vision: string;
  value_proposition: string;
  differentiation: string;
  business_model: string;
  goals: StrategyGoal[];
  target_users: StrategyTargetUser[];
  mvp_scope: MvpScopeItem[];
  success_metrics: SuccessMetric[];
  recommendations: StrategyRecommendation[];
  risks: StrategyRisk[];
  constraints: string[];
  open_decisions: OpenDecision[];
  limitations: string[];
}

export interface StrategySummary {
  version: number;
  status: Exclude<DocStatus, "not_started">;
  created_via: string;
  parent_version: number | null;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  approved_at: string | null;
  content_hash: string | null;
  recommendation_count: number;
  unsupported_count: number;
  error: string | null;
}

export interface StrategyDocument extends StrategySummary {
  id: string;
  content: StrategyContent | null;
  basis: Record<string, unknown>;
  approval_note: string | null;
  acknowledged_unverified: boolean;
  brain_revision: number | null;
  recommendation_counts: Record<RecStatus, number> | null;
  unverified_count: number;
  editable: boolean;
  warnings: { code: string; message: string }[];
}

export interface StrategyState {
  status: DocStatus;
  idea_ready: boolean;
  research_ready: boolean;
  approved_research_version: number | null;
  current: StrategyDocument | null;
  approved_version: number | null;
  history: StrategySummary[];
  last_error: string | null;
  inputs_preview: StrategyInputs | null;
  discovery_status: string;
  lifecycle: { stage: "product"; status: StageStatus };
  next_step: { key: string; label: string };
  can_generate: boolean;
  needs_supersede: boolean;
  can_submit: boolean;
  can_approve: boolean;
  limitations: string[];
}

export interface StrategyEditResponse {
  document: StrategyDocument;
  state: StrategyState;
}
