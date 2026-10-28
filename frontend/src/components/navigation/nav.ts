export interface NavItem { key: string; label: string; group: string; stage?: string; phase?: number; blurb?: string }

/**
 * Roadmap Phases 0–8 are platform & pre-lifecycle workflows:
 * - Phases 0–5.5: Foundation, Auth, Projects CRUD, Project Brain, Lifecycle Engine, Application Shell
 * - Phases 6–7: Project Overview & AI Idea Intake (`/projects/:id/overview`)
 * - Phase 8: AI Discovery Q&A (`/projects/:id/discovery`)
 *
 * Roadmap Phases 9–17 implement the 19 engineering lifecycle stages (`STAGES`).
 * `phase` is only set on sidebar items whose workspace is not yet implemented (routed to SectionPage).
 */
export const PRE_LIFECYCLE_NOTE =
  "Pre-lifecycle setup (Phases 1–8: Overview, AI Intake, and Discovery) populates your Project Brain. The 19 engineering lifecycle stages start at Phase 9 (Research).";

export const PROJECT_NAV: NavItem[] = [
  { key: "overview", label: "Overview", group: "Project" },
  { key: "discovery", label: "Discovery", group: "Discovery" },
  { key: "research", label: "Research", group: "Discovery", stage: "research" },
  { key: "competitors", label: "Competitors", group: "Discovery", stage: "research", phase: 10 },
  { key: "strategy", label: "Strategy", group: "Product", stage: "product" },
  { key: "prd", label: "PRD", group: "Product", stage: "product" },
  { key: "personas", label: "Personas", group: "UX", stage: "ux" },
  { key: "journeys", label: "User Journeys", group: "UX", stage: "ux" },
  { key: "ia", label: "Information Architecture", group: "UX", stage: "ux" },
  { key: "wireframes", label: "Wireframes", group: "UX", stage: "ux" },
  { key: "ux-review", label: "UX Review", group: "UX", stage: "ux" },
  { key: "design-system", label: "Design System", group: "Design", stage: "design" },
  { key: "prototype", label: "Prototype", group: "Design", stage: "design" },
  { key: "architecture", label: "Architecture", group: "Engineering", stage: "architecture" },
  { key: "frontend", label: "Frontend", group: "Engineering", stage: "frontend", phase: 13 },
  { key: "backend", label: "Backend", group: "Engineering", stage: "backend", phase: 13 },
  { key: "database", label: "Database", group: "Engineering", stage: "database", phase: 13 },
  { key: "api", label: "API", group: "Engineering", stage: "api", phase: 13 },
  { key: "testing", label: "Testing", group: "Quality", stage: "testing", phase: 14 },
  { key: "security", label: "Security", group: "Quality", stage: "security", phase: 14 },
  { key: "docker", label: "Docker", group: "DevOps & Cloud", stage: "docker", phase: 15 },
  { key: "cicd", label: "CI/CD", group: "DevOps & Cloud", stage: "cicd", phase: 15 },
  { key: "jenkins", label: "Jenkins", group: "DevOps & Cloud", stage: "cicd", phase: 15 },
  { key: "infrastructure", label: "Infrastructure", group: "DevOps & Cloud", stage: "infrastructure", phase: 15 },
  { key: "kubernetes", label: "Kubernetes", group: "DevOps & Cloud", stage: "infrastructure", phase: 15 },
  { key: "deployments", label: "Deployments", group: "DevOps & Cloud", stage: "deployment", phase: 15 },
  { key: "monitoring", label: "Monitoring", group: "DevOps & Cloud", stage: "monitoring", phase: 15 },
  { key: "seo", label: "SEO", group: "Growth", stage: "seo" },
  { key: "analytics", label: "Analytics", group: "Growth", stage: "analytics" },
  { key: "performance", label: "Performance", group: "Growth", stage: "analytics" },
  { key: "documentation", label: "Documentation", group: "Docs", stage: "documentation" },
  { key: "settings", label: "Settings", group: "Project" },
];

export const NAV_GROUPS = Array.from(new Set(PROJECT_NAV.map((n) => n.group)));
export const findNav = (key?: string) => PROJECT_NAV.find((n) => n.key === key);
export const findNavItem = findNav;
