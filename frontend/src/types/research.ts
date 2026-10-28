export type Evidence = "verified_source" | "user_provided" | "hypothesis" | "ai_suggestion" | "unsupported";
export type Topic = "user_needs" | "market_context" | "competitors_alternatives" | "technology_trends" | "opportunities" | "risks" | "assumptions" | "recommendations";
export type ReportStatus = "generating" | "failed" | "draft" | "in_review" | "approved" | "superseded";

export interface Citation { source_id: string; claim: string }
export interface Source { id: string; title: string; url: string; publisher: string | null; accessed_on: string | null; examined: boolean; examined_by: "user" | "webforge" | null; note: string | null }
export interface Finding {
  id: string; topic: Topic; statement: string; detail: string | null; evidence: Evidence; citations: Citation[];
  follow_up: boolean; follow_up_note: string | null; origin: "ai" | "user"; edited_by_user: boolean; note: string | null;
}
export interface BriefItem { text: string; status: "user_confirmed" | "ai_suggested"; question_id: string | null }
export interface Brief {
  product_summary: string; problem: BriefItem | null; target_users: BriefItem[]; business_goals: BriefItem[]; confirmed_requirements: BriefItem[];
  constraints: BriefItem[]; unknowns: string[]; missing_inputs: string[]; objectives: string[]; research_questions: string[]; scope_in: string[]; scope_out: string[];
}
export interface ReportContent { brief: Brief; findings: Finding[]; sources: Source[]; unresolved_questions: { id: string; question: string }[]; limitations: string[] }

export interface ReportSummary {
  version: number; status: ReportStatus; created_via: string; parent_version: number | null; created_at: string; updated_at: string;
  submitted_at: string | null; approved_at: string | null; content_hash: string | null; finding_count: number; source_count: number; error: string | null;
}
export interface Report extends ReportSummary {
  id: string; mode: string; content: ReportContent | null; basis: Record<string, unknown>; approval_note: string | null; acknowledged_unverified: boolean;
  brain_revision: number | null; evidence_counts: Record<Evidence, number> | null; unverified_count: number; editable: boolean;
  warnings: { code: string; message: string }[];
}
export interface ResearchState {
  status: "not_started" | "generating" | "failed" | "draft" | "in_review" | "approved";
  idea_ready: boolean; mode: string; current: Report | null; approved_version: number | null; history: ReportSummary[]; last_error: string | null;
  brief_preview: Brief | null; discovery_status: string; lifecycle: { stage: string; status: string }; next_step: { key: string; label: string };
  can_generate: boolean; needs_supersede: boolean; can_submit: boolean; can_approve: boolean; limitations: string[];
}
export interface EditResponse { report: Report; state: ResearchState }
