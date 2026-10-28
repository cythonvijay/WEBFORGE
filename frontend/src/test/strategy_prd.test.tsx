import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { authed, project, renderApp } from "./helpers";
import { mockApi } from "./mockApi";

const base = { ...authed, "GET /projects/:id": { body: project() } };
const HASH_S1 = "s".repeat(64);
const HASH_P1 = "p".repeat(64);
const HASH_P2 = "q".repeat(64);

const strategyInputs = {
  product_summary: "ScopeGuard - B2B SaaS",
  confirmed_facts: [{ ref_id: "fact-q1", category: "target_users", text: "Who will use it? -> Boutique agencies", provenance: "user_confirmed" }],
  ai_suggestions: [{ ref_id: "idea-problem", category: "problem", text: "Agencies lose margin on scope creep", provenance: "ai_suggestion" }],
  unresolved_assumptions: [{ ref_id: "idea-assum-1", category: "assumption", text: "Clients will sign scope baselines online", provenance: "unresolved_assumption" }],
  research_findings: [{ ref_id: "res-f-1", category: "user_needs", text: "Agencies need explicit scope boundaries", provenance: "research_finding", evidence: "hypothesis" }],
  missing_inputs: ["No business model has been confirmed."],
  research_version: 1,
  discovery_status: "completed",
};

const strategyDoc = (over: Record<string, unknown> = {}) => ({
  id: "sd-1",
  version: 1,
  status: "draft",
  created_via: "generated",
  parent_version: null,
  created_at: "2026-04-12T10:00:00Z",
  updated_at: "2026-04-12T10:00:00Z",
  submitted_at: null,
  approved_at: null,
  content_hash: HASH_S1,
  recommendation_count: 2,
  unsupported_count: 1,
  error: null,
  basis: { brain_version: 2, research_version: 1 },
  approval_note: null,
  acknowledged_unverified: false,
  brain_revision: null,
  recommendation_counts: { grounded_in_confirmed: 1, supported_by_research: 0, ai_suggestion: 0, hypothesis: 0, unsupported: 1 },
  unverified_count: 1,
  editable: true,
  warnings: [{ code: "unsupported", message: "1 recommendation(s) are unsupported or lack input references and need evidence." }],
  content: {
    inputs: strategyInputs,
    product_vision: "Eliminate unbilled scope creep for boutique digital agencies.",
    value_proposition: "Turn discovery notes into enforceable scope baselines.",
    differentiation: "Built for agency deliverable sign-off rather than generic task tracking.",
    business_model: "Monthly subscription per agency workspace.",
    goals: [{ id: "sg-1", goal: "Protect fixed-fee agency margins", rationale: "Addresses core pain point", supporting_refs: ["fact-q1"], status: "user_confirmed" }],
    target_users: [{ id: "su-1", segment: "Boutique digital agencies", needs: "Clear scope baselines", supporting_refs: ["fact-q1"], status: "user_confirmed" }],
    mvp_scope: [{ id: "mvp-1", item: "Scope baseline editor", boundary: "in_mvp", rationale: "Core MVP workflow", supporting_refs: ["res-f-1"] }],
    success_metrics: [{ id: "sm-1", metric: "Time to signed scope baseline", target_direction: "Decrease turnaround time", supporting_refs: ["fact-q1"] }],
    recommendations: [
      {
        id: "rec-1",
        area: "mvp_scope",
        title: "Prioritize scope baseline sign-off",
        recommendation: "Focus MVP on scope boundary sign-off before building invoicing.",
        rationale: "Directly addresses confirmed agency needs.",
        status: "grounded_in_confirmed",
        supporting_refs: ["fact-q1", "res-f-1"],
        needs_evidence: false,
        origin: "ai",
        edited_by_user: false,
        note: null,
      },
      {
        id: "rec-2",
        area: "differentiation",
        title: "Ungrounded expansion claim",
        recommendation: "Target 50% market penetration in year one.",
        rationale: "Aggressive growth target.",
        status: "unsupported",
        supporting_refs: [],
        needs_evidence: true,
        origin: "ai",
        edited_by_user: false,
        note: "Contains a numeric or statistical claim without verified source data; classified unsupported.",
      },
    ],
    risks: [{ id: "sr-1", risk: "Spreadsheet inertia", mitigation: "One-click template import", supporting_refs: ["res-f-1"] }],
    constraints: ["Browser-based client review without login"],
    open_decisions: [{ id: "od-1", question: "Checkbox vs e-signature in MVP?", impact: "Speed vs legal weight" }],
    limitations: ["Strategy recommendations are synthesized from your Project Brain, Discovery answers, and approved Research report."],
  },
  ...over,
});

const strategyState = (over: Record<string, unknown> = {}) => ({
  status: "draft",
  idea_ready: true,
  research_ready: true,
  approved_research_version: 1,
  current: strategyDoc(),
  approved_version: null,
  history: [{ version: 1, status: "draft", created_via: "generated", parent_version: null, created_at: "2026-04-12T10:00:00Z", updated_at: "2026-04-12T10:00:00Z", submitted_at: null, approved_at: null, content_hash: HASH_S1, recommendation_count: 2, unsupported_count: 1, error: null }],
  last_error: null,
  inputs_preview: null,
  discovery_status: "completed",
  lifecycle: { stage: "product", status: "not_started" },
  next_step: { key: "review_and_submit", label: "Review strategy recommendations and provenance, then submit for review" },
  can_generate: true,
  needs_supersede: true,
  can_submit: true,
  can_approve: false,
  limitations: ["Strategy recommendations are synthesized from your Project Brain, Discovery answers, and approved Research report."],
  ...over,
});

const prdDoc = (over: Record<string, unknown> = {}) => ({
  id: "pd-1",
  version: 1,
  status: "draft",
  created_via: "generated",
  parent_version: null,
  created_at: "2026-04-12T11:00:00Z",
  updated_at: "2026-04-12T11:00:00Z",
  submitted_at: null,
  approved_at: null,
  content_hash: HASH_P1,
  requirement_count: 2,
  approved_requirement_count: 0,
  proposed_requirement_count: 2,
  error: null,
  basis: { brain_version: 3, strategy_version: 1, research_version: 1 },
  approval_note: null,
  acknowledged_unverified: false,
  brain_revision: null,
  requirement_counts: { functional: 1, non_functional: 1, total: 2, proposed: 2, approved: 0, unlinked: 0, must_have: 2 },
  proposed_count: 2,
  unlinked_count: 0,
  editable: true,
  warnings: [{ code: "proposed_requirements", message: "2 requirement(s) are still marked 'proposed' and have not been individually approved." }],
  content: {
    strategy_basis: {
      strategy_version: 1,
      research_version: 1,
      product_vision: "Eliminate unbilled scope creep for boutique digital agencies.",
      value_proposition: "Turn discovery notes into enforceable scope baselines.",
      available_refs: [{ ref_id: "sg-1", kind: "strategy_goal", summary: "Protect fixed-fee agency margins" }],
    },
    problem_statement: "Boutique agencies lose margin when informal client requests expand fixed-fee project scope.",
    target_users: ["Boutique digital agency founders"],
    user_stories: [{ id: "US-1", persona: "Agency founder", action: "publish a clear scope baseline", benefit: "clients sign off on explicit boundaries", priority: "must_have", source_refs: ["sg-1"] }],
    functional_requirements: [
      {
        id: "FR-1",
        title: "Scope Baseline Editor",
        description: "Create and publish structured project scope baselines.",
        priority: "must_have",
        mvp_boundary: "in_mvp",
        status: "proposed",
        user_story_ids: ["US-1"],
        source_refs: ["sg-1"],
        acceptance_criteria: ["User can add in-scope deliverables and explicit exclusions."],
        edge_cases: ["Publishing an empty baseline returns a validation error."],
        dependencies: ["Authentication"],
        origin: "ai",
        edited_by_user: false,
        unlinked: false,
      },
    ],
    non_functional_requirements: [
      {
        id: "NFR-1",
        category: "security",
        title: "Tenant Isolation",
        description: "Isolate agency workspaces from other tenants.",
        priority: "must_have",
        mvp_boundary: "in_mvp",
        status: "proposed",
        source_refs: ["sg-1"],
        acceptance_criteria: ["Cross-tenant requests return HTTP 404."],
        origin: "ai",
        edited_by_user: false,
        unlinked: false,
      },
    ],
    mvp_boundaries: { in_mvp: ["Scope Baseline Editor"], post_mvp: ["Client billing portal"], out_of_scope: ["Payroll suite"] },
    dependencies: ["PostgreSQL"],
    risks: [{ id: "pr-1", risk: "Vague scope entries", mitigation: "Structured acceptance criteria prompts" }],
    open_questions: [{ id: "pq-1", question: "Is PDF export required in MVP?" }],
    limitations: ["PRD requirements are generated as proposed items from your approved Product Strategy and require explicit user review and approval."],
  },
  ...over,
});

const prdState = (over: Record<string, unknown> = {}) => ({
  status: "draft",
  idea_ready: true,
  strategy_ready: true,
  approved_strategy_version: 1,
  current: prdDoc(),
  approved_version: null,
  history: [{ version: 1, status: "draft", created_via: "generated", parent_version: null, created_at: "2026-04-12T11:00:00Z", updated_at: "2026-04-12T11:00:00Z", submitted_at: null, approved_at: null, content_hash: HASH_P1, requirement_count: 2, approved_requirement_count: 0, proposed_requirement_count: 2, error: null }],
  last_error: null,
  basis_preview: null,
  lifecycle: { stage: "product", status: "in_progress" },
  next_step: { key: "review_and_submit", label: "Review requirements, acceptance criteria, and MVP boundaries, then submit for review" },
  can_generate: true,
  needs_supersede: true,
  can_submit: true,
  can_approve: false,
  limitations: ["PRD requirements are generated as proposed items from your approved Product Strategy and require explicit user review and approval."],
  ...over,
});

describe("Phase 10 Navigation, Strategy, and PRD", () => {
  it("exposes Strategy and PRD in sidebar navigation without Phase 10 placeholder badges while keeping Competitors badged", async () => {
    mockApi({ ...base, "GET /projects/:id/strategy": { body: strategyState() } });
    renderApp("/projects/p1/strategy");
    await screen.findByRole("heading", { name: "Product Strategy" });
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: /^Strategy$/ })).not.toHaveTextContent("Phase 10");
    expect(within(nav).getByRole("link", { name: /^PRD$/ })).not.toHaveTextContent("Phase 10");
    expect(within(nav).getByRole("link", { name: /Competitors/ })).toHaveTextContent("Phase 10");
  });

  it("requires approved Research before generating Strategy", async () => {
    mockApi({
      ...base,
      "GET /projects/:id/strategy": {
        body: strategyState({ status: "not_started", current: null, research_ready: false, can_generate: false, inputs_preview: strategyInputs }),
      },
    });
    renderApp("/projects/p1/strategy");
    expect(await screen.findByText("Approve Research first")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Research" })).toHaveAttribute("href", "/projects/p1/research");
  });

  it("renders Strategy provenance, flags unsupported recommendations, and supports submit + approval with acknowledgement", async () => {
    let st = strategyState();
    const api = mockApi({
      ...base,
      "GET /projects/:id/strategy": () => ({ body: st }),
      "POST /projects/:id/strategy/versions/:v/submit": () => {
        st = strategyState({ status: "in_review", current: strategyDoc({ status: "in_review" }), can_submit: false, can_approve: true, lifecycle: { stage: "product", status: "needs_review" } });
        return { body: st };
      },
      "POST /projects/:id/strategy/versions/:v/approve": () => {
        st = strategyState({ status: "approved", approved_version: 1, current: strategyDoc({ status: "approved", approved_at: "2026-04-12T10:30:00Z", acknowledged_unverified: true }), can_submit: false, can_approve: false, lifecycle: { stage: "product", status: "in_progress" } });
        return { body: st };
      },
    });
    renderApp("/projects/p1/strategy");
    expect(await screen.findByText("Prioritize scope baseline sign-off")).toBeInTheDocument();
    expect(screen.getByText("Grounded in confirmed fact")).toBeInTheDocument();
    expect(screen.getByText("Unsupported — needs evidence")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Submit for review" }));
    const approveBtn = await screen.findByRole("button", { name: "Approve version 1" });
    await userEvent.click(approveBtn);

    const dialog = await screen.findByRole("dialog", { name: "Approve this strategy version" });
    const confirmBtn = within(dialog).getByRole("button", { name: "Approve strategy" });
    expect(confirmBtn).toBeDisabled();
    await userEvent.click(within(dialog).getByRole("checkbox"));
    expect(confirmBtn).toBeEnabled();
    await userEvent.click(confirmBtn);

    await waitFor(() => expect(api.last("POST", "/projects/p1/strategy/versions/1/approve")?.body).toEqual({
      content_hash: HASH_S1,
      acknowledge_unverified: true,
      note: null,
    }));
    expect(await screen.findByRole("link", { name: "Continue to PRD" })).toHaveAttribute("href", "/projects/p1/prd");
  });

  it("renders PRD requirements with stable IDs, supports approving requirements, and completes the Product stage on PRD approval", async () => {
    let st = prdState();
    const api = mockApi({
      ...base,
      "GET /projects/:id/prd": () => ({ body: st }),
      "POST /projects/:id/prd/versions/:v/requirements/status": () => {
        const updated = prdDoc({ content_hash: HASH_P2, proposed_count: 0, approved_requirement_count: 2, proposed_requirement_count: 0 });
        st = prdState({ current: updated });
        return { body: { document: updated, state: st } };
      },
      "POST /projects/:id/prd/versions/:v/submit": () => {
        st = prdState({ status: "in_review", current: prdDoc({ status: "in_review", content_hash: HASH_P2, proposed_count: 0 }), can_submit: false, can_approve: true, lifecycle: { stage: "product", status: "needs_review" } });
        return { body: st };
      },
      "POST /projects/:id/prd/versions/:v/approve": () => {
        st = prdState({ status: "approved", approved_version: 1, current: prdDoc({ status: "approved", content_hash: HASH_P2, proposed_count: 0, approved_at: "2026-04-12T12:00:00Z" }), can_submit: false, can_approve: false, lifecycle: { stage: "product", status: "complete" } });
        return { body: st };
      },
    });
    renderApp("/projects/p1/prd");
    expect(await screen.findByRole("heading", { name: "Product Requirements Document (PRD)" })).toBeInTheDocument();
    expect(screen.getByText("FR-1")).toBeInTheDocument();
    expect(screen.getByText("NFR-1")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Approve all requirements" }));
    await waitFor(() => expect(api.last("POST", "/projects/p1/prd/versions/1/requirements/status")?.body).toEqual({
      base_hash: HASH_P1,
      requirement_ids: ["FR-1", "NFR-1"],
      status: "approved",
    }));

    await userEvent.click(screen.getByRole("button", { name: "Submit for review" }));
    await userEvent.click(await screen.findByRole("button", { name: "Approve version 1" }));
    const dialog = await screen.findByRole("dialog", { name: "Approve this PRD version" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Approve PRD" }));

    await waitFor(() => expect(api.last("POST", "/projects/p1/prd/versions/1/approve")?.body).toEqual({
      content_hash: HASH_P2,
      acknowledge_unverified: false,
      note: null,
    }));
    expect(await screen.findByText("Product stage: complete")).toBeInTheDocument();
  });
});
