export type DiscoveryStatus = "not_started" | "generating" | "awaiting_answers" | "ready_for_review" | "completed" | "failed";
export type QuestionType = "free_text" | "single_choice" | "multiple_choice" | "confirmation";
export type QuestionStatus = "open" | "answered" | "skipped" | "deferred";

export interface QuestionAnswer { text?: string; choice?: string; choices?: string[]; confirmed?: boolean }

export interface DiscoveryQuestion {
  id: string;
  round: number;
  prompt: string;
  rationale: string;
  target: string;
  qtype: QuestionType;
  options: { id: string; label: string }[];
  required: boolean;
  priority: number;
  max_length: number | null;
  status: QuestionStatus;
  answer: QuestionAnswer | null;
  answered_at: string | null;
}

export interface Assumption { id: string; text: string; source: "ai_suggested" | "user_declared" | "unanswered_question"; status: "unverified" | "accepted" }
export interface QuestionRef { id: string; question: string; required: boolean }

export interface DiscoverySummary {
  confirmed: { question_id: string; question: string; target: string; answer: unknown }[];
  proposed: { label: string; target: string | null; items: string[] }[];
  assumptions: Assumption[];
  unanswered: QuestionRef[];
  deferred: QuestionRef[];
  skipped: QuestionRef[];
}

export interface DiscoveryState {
  status: DiscoveryStatus;
  session_id: string | null;
  idea_ready: boolean;
  round: number;
  max_rounds: number;
  questions: DiscoveryQuestion[];
  counts: { open: number; answered: number; skipped: number; deferred: number; total: number };
  outstanding_questions: string[];
  unresolved_assumptions: Assumption[];
  summary: DiscoverySummary | null;
  next_step: { key: string; label: string; note?: string };
  last_error: string | null;
  can_generate_next_round: boolean;
  can_review: boolean;
  can_complete: boolean;
}

/** Unsaved form value for one question. */
export type Draft = string | string[] | boolean | undefined;
