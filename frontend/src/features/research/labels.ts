import type { Evidence, ReportStatus, Topic } from "../../types/research";

export const EVIDENCE: Record<Evidence, { label: string; tone: "success" | "info" | "neutral" | "warning" | "danger"; help: string }> = {
  verified_source: { label: "Source examined by you", tone: "success", help: "Backed by a cited source you state you examined. WebForge did not check the source." },
  user_provided: { label: "Provided by you (unverified)", tone: "info", help: "Supplied by you and not independently verified." },
  hypothesis: { label: "Hypothesis", tone: "neutral", help: "Plausible but unverified." },
  ai_suggestion: { label: "AI suggestion", tone: "warning", help: "A model-generated proposal, not a fact." },
  unsupported: { label: "Unsupported claim", tone: "danger", help: "A claim that needs evidence before it can be relied on." },
};
export const EVIDENCE_ORDER = Object.keys(EVIDENCE) as Evidence[];

export const TOPICS: Record<Topic, string> = {
  user_needs: "User needs and pain points", market_context: "Market context", competitors_alternatives: "Competitors and alternatives",
  technology_trends: "Technology and industry trends", opportunities: "Opportunities and product gaps", risks: "Risks",
  assumptions: "Assumptions to validate", recommendations: "Recommendations",
};
export const TOPIC_ORDER = Object.keys(TOPICS) as Topic[];

export const STATUS: Record<ReportStatus | "not_started", { label: string; tone: "success" | "info" | "neutral" | "warning" | "danger" }> = {
  not_started: { label: "Not started", tone: "neutral" }, generating: { label: "Generating", tone: "info" }, failed: { label: "Failed", tone: "danger" },
  draft: { label: "Draft", tone: "warning" }, in_review: { label: "In review", tone: "info" }, approved: { label: "Approved", tone: "success" }, superseded: { label: "Superseded", tone: "neutral" },
};
