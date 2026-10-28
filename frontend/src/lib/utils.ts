export function cn(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

export const STAGE_LABELS: Record<string, string> = {
  research: "Research", product: "Product", ux: "UX", design: "Design", architecture: "Architecture",
  frontend: "Frontend", backend: "Backend", database: "Database", api: "API", testing: "Testing",
  security: "Security", docker: "Docker", cicd: "CI/CD", infrastructure: "Infrastructure",
  deployment: "Deployment", monitoring: "Monitoring", seo: "SEO", analytics: "Analytics",
  documentation: "Documentation",
};
export const stageLabel = (s: string) => STAGE_LABELS[s] ?? s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, " ");

export const STATUS_LABELS = {
  not_started: "Not started", in_progress: "In progress", needs_review: "Needs review",
  complete: "Complete", blocked: "Blocked",
} as const;

export const CHANGE_LABELS: Record<string, string> = {
  created: "Project created", edit: "Brain section edited", ai_intake: "AI intake analysis saved",
  discovery_answer: "Discovery answers saved", research_approved: "Research report approved", strategy_approved: "Product Strategy approved", prd_approved: "PRD approved", design_design_system_approved: "Design System approved", design_prototype_approved: "Interactive Prototype approved", architecture_approved: "Product Architecture approved", discovery_completed: "Discovery completed with documented assumptions",
};
export const changeLabel = (t: string) => CHANGE_LABELS[t] ?? t.replace(/_/g, " ");

export function formatDateTime(iso: string) {
  const d = new Date(asUtcIso(iso));
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function timeAgo(iso: string, now = Date.now()) {
  const t = new Date(asUtcIso(iso)).getTime();
  if (Number.isNaN(t)) return "—";
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)} d ago`;
  return formatDateTime(iso);
}

/** Backend timestamps may lack a timezone suffix; treat those as UTC. */
export const asUtcIso = (s: string) => (/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z");

/** Defense-in-depth URL guard: only allow http:// and https:// URLs in rendered href attributes. */
export function safeHttpUrl(raw?: string | null): string {
  if (!raw) return "#";
  const trimmed = raw.trim();
  return /^https?:\/\//i.test(trimmed) ? trimmed : "#";
}
