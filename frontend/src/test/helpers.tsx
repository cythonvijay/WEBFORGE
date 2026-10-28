import { render } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { Providers } from "../app/providers";
import { routes } from "../app/router";

export function renderApp(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<Providers><RouterProvider router={router} /></Providers>);
  return router;
}

export const user = { id: "u1", email: "ada@example.com" };
export const anon = { "GET /auth/me": { status: 401, body: { detail: "Not authenticated" } }, "POST /auth/refresh": { status: 401, body: { detail: "Invalid refresh token" } } };
export const authed = { "GET /auth/me": { body: user } };

const now = new Date().toISOString();
export const project = (o: Record<string, unknown> = {}) => ({ id: "p1", name: "Snapbook", description: "Photographer marketplace", status: "active", created_at: now, updated_at: now, ...o });

// Fixture shaped like the backend's /overview response (dependency data comes from the backend, not the UI).
const DEPS: Record<string, string[]> = {
  research: [], product: ["research"], ux: ["product"], design: ["ux"], architecture: ["design"],
  frontend: ["architecture"], backend: ["architecture"], database: ["architecture"], api: ["backend", "database"],
  testing: ["frontend", "api"], security: ["testing"], docker: ["security"], cicd: ["docker"],
  infrastructure: ["cicd"], deployment: ["infrastructure"], monitoring: ["deployment"],
  seo: ["design", "frontend"], analytics: ["frontend", "backend"], documentation: ["architecture"],
};
export function overview(statuses: Record<string, string> = {}, extra: Record<string, unknown> = {}) {
  const st = (s: string) => statuses[s] ?? "not_started";
  const names = Object.keys(DEPS);
  return {
    project: project(),
    stages: names.map((s) => ({ stage: s, status: st(s), depends_on: DEPS[s], unmet_dependencies: DEPS[s].filter((d) => st(d) !== "complete") })),
    progress: 0, completed: names.filter((s) => st(s) === "complete"),
    in_progress: names.filter((s) => st(s) === "in_progress"), needs_review: names.filter((s) => st(s) === "needs_review"),
    blocked: names.filter((s) => st(s) === "blocked"), next_action: "research",
    recent_changes: [{ version: 1, change_type: "created", created_at: now }], ...extra,
  };
}
export const emptyBrain = { version: 1, brain: { idea: { raw: "", product_name: "", product_type: "", problem: "", features: [], assumptions: [], open_questions: [] }, target_users: [], goals: [] } };
export const filledBrain = (version = 2) => ({
  version, brain: {
    idea: { raw: "A marketplace for local photographers", product_name: "Snapbook", product_type: "marketplace", problem: "Hard to compare photographers",
      features: ["Package comparison"], assumptions: ["Customers book online"], open_questions: ["Who pays the fee?"] },
    target_users: ["Customers"], goals: ["Increase bookings"],
  },
});

// ---- discovery fixtures (shaped like the backend's /discovery response) ----
export const dq = (o: Record<string, unknown> = {}) => ({
  id: "q1", round: 1, prompt: "Who will use the product first?", rationale: "It decides what the first release must do.", target: "target_users",
  qtype: "free_text", options: [], required: true, priority: 1, max_length: null, status: "open", answer: null, answered_at: null, ...o,
});
export const dstate = (o: Record<string, unknown> = {}) => ({
  status: "awaiting_answers", session_id: "s1", idea_ready: true, round: 1, max_rounds: 3, questions: [dq()],
  counts: { open: 1, answered: 0, skipped: 0, deferred: 0, total: 1 }, outstanding_questions: ["q1"], unresolved_assumptions: [], summary: null,
  next_step: { key: "answer_questions", label: "Answer or skip the open questions" }, last_error: null,
  can_generate_next_round: false, can_review: true, can_complete: false, ...o,
});
export const notStarted = dstate({ status: "not_started", session_id: null, round: 0, questions: [], counts: { open: 0, answered: 0, skipped: 0, deferred: 0, total: 0 }, outstanding_questions: [], can_review: false, next_step: { key: "start_discovery", label: "Start discovery" } });
export const summary = (o: Record<string, unknown> = {}) => ({ confirmed: [], proposed: [], assumptions: [], unanswered: [], deferred: [], skipped: [], ...o });
