import type { StageStatus } from "./lifecycle";
import type { DocStatus } from "./strategy";

export type Priority = "must_have" | "should_have" | "could_have" | "wont_have";
export type ReqStatus = "proposed" | "approved";
export type MvpBoundary = "in_mvp" | "post_mvp" | "out_of_scope";
export type NfrCategory = "performance" | "security" | "reliability" | "usability" | "scalability" | "compliance" | "maintainability";

export interface StrategyRefItem {
  ref_id: string;
  kind: string;
  summary: string;
}

export interface PrdBasisSummary {
  strategy_version: number;
  research_version: number | null;
  product_vision: string;
  value_proposition: string;
  available_refs: StrategyRefItem[];
}

export interface UserStory {
  id: string;
  persona: string;
  action: string;
  benefit: string;
  priority: Priority;
  source_refs: string[];
}

export interface FunctionalRequirement {
  id: string;
  title: string;
  description: string;
  priority: Priority;
  mvp_boundary: MvpBoundary;
  status: ReqStatus;
  user_story_ids: string[];
  source_refs: string[];
  acceptance_criteria: string[];
  edge_cases: string[];
  dependencies: string[];
  origin: "ai" | "user";
  edited_by_user: boolean;
  unlinked: boolean;
}

export interface NonFunctionalRequirement {
  id: string;
  category: NfrCategory;
  title: string;
  description: string;
  priority: Priority;
  mvp_boundary: MvpBoundary;
  status: ReqStatus;
  source_refs: string[];
  acceptance_criteria: string[];
  origin: "ai" | "user";
  edited_by_user: boolean;
  unlinked: boolean;
}

export interface PrdMvpBoundary {
  in_mvp: string[];
  post_mvp: string[];
  out_of_scope: string[];
}

export interface PrdRisk {
  id: string;
  risk: string;
  mitigation: string;
}

export interface PrdQuestion {
  id: string;
  question: string;
}

export interface PrdContent {
  strategy_basis: PrdBasisSummary;
  problem_statement: string;
  target_users: string[];
  user_stories: UserStory[];
  functional_requirements: FunctionalRequirement[];
  non_functional_requirements: NonFunctionalRequirement[];
  mvp_boundaries: PrdMvpBoundary;
  dependencies: string[];
  risks: PrdRisk[];
  open_questions: PrdQuestion[];
  limitations: string[];
}

export interface PrdSummary {
  version: number;
  status: Exclude<DocStatus, "not_started">;
  created_via: string;
  parent_version: number | null;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  approved_at: string | null;
  content_hash: string | null;
  requirement_count: number;
  approved_requirement_count: number;
  proposed_requirement_count: number;
  error: string | null;
}

export interface PrdDocument extends PrdSummary {
  id: string;
  content: PrdContent | null;
  basis: Record<string, unknown>;
  approval_note: string | null;
  acknowledged_unverified: boolean;
  brain_revision: number | null;
  requirement_counts: {
    functional: number;
    non_functional: number;
    total: number;
    proposed: number;
    approved: number;
    unlinked: number;
    must_have: number;
  } | null;
  proposed_count: number;
  unlinked_count: number;
  editable: boolean;
  warnings: { code: string; message: string }[];
}

export interface PrdState {
  status: DocStatus;
  idea_ready: boolean;
  strategy_ready: boolean;
  approved_strategy_version: number | null;
  current: PrdDocument | null;
  approved_version: number | null;
  history: PrdSummary[];
  last_error: string | null;
  basis_preview: PrdBasisSummary | null;
  lifecycle: { stage: "product"; status: StageStatus };
  next_step: { key: string; label: string };
  can_generate: boolean;
  needs_supersede: boolean;
  can_submit: boolean;
  can_approve: boolean;
  limitations: string[];
}

export interface PrdEditResponse {
  document: PrdDocument;
  state: PrdState;
}
