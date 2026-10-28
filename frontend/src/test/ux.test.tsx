import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { authed, project, renderApp } from "./helpers";
import { mockApi } from "./mockApi";

const base = { ...authed, "GET /projects/:id": { body: project() } };
const HASH_U1 = "u".repeat(64);
const HASH_U2 = "v".repeat(64);

const uxBasis = {
  research_version: 1,
  strategy_version: 1,
  prd_version: 1,
  personas_version: 1,
  journeys_version: 1,
  ia_version: 1,
  wireframes_version: 1,
  valid_req_ids: ["FR-1", "FR-2", "NFR-1"],
  valid_story_ids: ["US-1"],
  valid_evidence_refs: ["res-f-1", "sg-1"],
  confirmed_evidence_refs: ["sg-1"],
  valid_persona_ids: ["P-1"],
  valid_journey_ids: ["J-1"],
  valid_ia_node_ids: ["IA-1", "IA-2"],
  valid_wireframe_ids: ["WF-1"],
};

const readyPrereqs = {
  ready: true,
  missing: [],
  upstream_versions: { research: 1, strategy: 1, prd: 1, personas: 1, journeys: 1, ia: 1, wireframes: 1 },
};

describe("Phase 11 UX Workspaces (Personas, Journeys, IA, Wireframes, UX Review)", () => {
  it("exposes all 5 UX workspaces in navigation without Phase 11 placeholder badges while keeping Design System badged as Phase 12", async () => {
    mockApi({
      ...base,
      "GET /projects/:id/ux/personas": {
        body: {
          artifact_type: "personas",
          status: "not_started",
          prerequisites: readyPrereqs,
          is_stale: false,
          stale_reasons: [],
          current: null,
          approved_version: null,
          history: [],
          last_error: null,
          basis_preview: uxBasis,
          lifecycle: { stage: "ux", status: "not_started", ux_complete: false, pending_criteria: [] },
          next_step: { key: "start", label: "Generate personas from approved upstream artifacts" },
          can_generate: true,
          needs_supersede: false,
          can_submit: false,
          can_approve: false,
          limitations: ["Personas are synthesized from your approved Research, Strategy, and PRD."],
        },
      },
    });
    renderApp("/projects/p1/personas");
    await screen.findByRole("heading", { name: "Personas" });
    const nav = screen.getByRole("navigation", { name: "Primary" });
    for (const label of [/^Personas$/, /^User Journeys$/, /^Information Architecture$/, /^Wireframes$/, /^UX Review$/]) {
      expect(within(nav).getByRole("link", { name: label })).not.toHaveTextContent("Phase 11");
    }
    expect(within(nav).getByRole("link", { name: /Design System/ })).toHaveTextContent("Phase 12");
  });

  it("displays explicit prerequisite gates and workspace links when upstream artifacts are missing", async () => {
    mockApi({
      ...base,
      "GET /projects/:id/ux/journeys": {
        body: {
          artifact_type: "journeys",
          status: "not_started",
          prerequisites: {
            ready: false,
            missing: [{ artifact: "personas", label: "Personas", message: "Generate and approve Personas before starting this workspace.", workspace_path: "/projects/p1/personas" }],
            upstream_versions: { research: 1, strategy: 1, prd: 1, personas: null, journeys: null, ia: null, wireframes: null },
          },
          is_stale: false,
          stale_reasons: [],
          current: null,
          approved_version: null,
          history: [],
          last_error: null,
          basis_preview: null,
          lifecycle: { stage: "ux", status: "in_progress", ux_complete: false, pending_criteria: [] },
          next_step: { key: "fix_prerequisites", label: "Generate and approve Personas before starting this workspace.", workspace_path: "/projects/p1/personas" },
          can_generate: false,
          needs_supersede: false,
          can_submit: false,
          can_approve: false,
          limitations: ["User journeys model expected flows for PRD-supported goals."],
        },
      },
    });
    renderApp("/projects/p1/journeys");
    expect(await screen.findByText("Upstream prerequisites required")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Personas" })).toHaveAttribute("href", "/projects/p1/personas");
  });

  it("renders interactive low-fidelity wireframes with viewport switching and UI state previews", async () => {
    mockApi({
      ...base,
      "GET /projects/:id/ux/wireframes": {
        body: {
          artifact_type: "wireframes",
          status: "draft",
          prerequisites: readyPrereqs,
          is_stale: false,
          stale_reasons: [],
          approved_version: null,
          history: [],
          last_error: null,
          basis_preview: null,
          lifecycle: { stage: "ux", status: "in_progress", ux_complete: false, pending_criteria: [] },
          next_step: { key: "review_and_submit", label: "Review and edit items, then submit for review" },
          can_generate: true,
          needs_supersede: true,
          can_submit: true,
          can_approve: false,
          limitations: ["Wireframes are structured low-fidelity layout and state specifications."],
          current: {
            id: "wf-doc-1",
            version: 1,
            status: "draft",
            artifact_type: "wireframes",
            created_via: "generated",
            parent_version: null,
            created_at: "2026-04-12T12:00:00Z",
            updated_at: "2026-04-12T12:00:00Z",
            submitted_at: null,
            approved_at: null,
            content_hash: HASH_U1,
            item_count: 1,
            error: null,
            basis: { prd_version: 1, ia_version: 1 },
            approval_note: null,
            acknowledged_unverified: false,
            brain_revision: null,
            unverified_count: 0,
            critical_open_count: 0,
            review_counts: null,
            is_stale: false,
            stale_reasons: [],
            editable: true,
            warnings: [],
            content: {
              basis: uxBasis,
              limitations: ["Wireframes are structured low-fidelity layout and state specifications."],
              wireframes: [
                {
                  id: "WF-1",
                  page_name: "Scope Baseline Editor",
                  purpose: "Author and publish scope deliverables and exclusions.",
                  ia_node_id: "IA-2",
                  target_viewport: "responsive",
                  regions: [
                    {
                      region: "main",
                      heading: "Deliverables & Exclusions",
                      components: [
                        { id: "cmp-1", kind: "form", label: "Deliverable Form", content_role: "Add in-scope items", elements: ["Title input", "Save button"] },
                      ],
                    },
                  ],
                  primary_actions: ["Publish Baseline"],
                  secondary_actions: ["Preview"],
                  form_fields: [{ name: "Deliverable title", field_type: "text", required: true, validation_rule: "Required 3-200 chars" }],
                  states: {
                    loading: "Skeleton loader while fetching baseline",
                    empty: "Prompt to add your first scope deliverable",
                    error: "Inline alert if baseline cannot be saved",
                    success: "Published baseline confirmation banner",
                  },
                  responsive_behavior: {
                    desktop: "Two-column split layout",
                    tablet: "Stacked layout with sticky bar",
                    mobile: "Single-column mobile tabs",
                  },
                  accessibility_keyboard: ["Keyboard up/down reorder buttons"],
                  persona_ids: ["P-1"],
                  journey_ids: ["J-1"],
                  prd_requirement_ids: ["FR-1"],
                  origin: "ai",
                  edited_by_user: false,
                },
              ],
            },
          },
        },
      },
    });
    renderApp("/projects/p1/wireframes");
    expect(await screen.findByText("Scope Baseline Editor")).toBeInTheDocument();
    const canvas = screen.getByTestId("wf-canvas-WF-1");
    expect(canvas).toHaveAttribute("data-viewport", "desktop");
    expect(canvas).toHaveTextContent("Two-column split layout");

    // Switch viewport to Mobile
    await userEvent.click(screen.getByRole("button", { name: "Mobile" }));
    expect(canvas).toHaveAttribute("data-viewport", "mobile");
    expect(canvas).toHaveTextContent("Single-column mobile tabs");

    // Switch UI state preview to Empty state
    await userEvent.selectOptions(screen.getByLabelText("UI state preview"), "empty");
    expect(canvas).toHaveTextContent("Prompt to add your first scope deliverable");
  });

  it("requires resolving or accepting critical UX review findings with a rationale before completing the UX stage", async () => {
    const makeReviewState = (critOpen: number, status = "draft", hash = HASH_U1, uxStage = "in_progress") => ({
      artifact_type: "ux_review",
      status,
      prerequisites: readyPrereqs,
      is_stale: false,
      stale_reasons: [],
      approved_version: status === "approved" ? 1 : null,
      history: [],
      last_error: null,
      basis_preview: null,
      lifecycle: { stage: "ux", status: uxStage, ux_complete: uxStage === "complete", pending_criteria: [] },
      next_step: { key: "review_and_submit", label: "Review findings" },
      can_generate: true,
      needs_supersede: true,
      can_submit: status === "draft",
      can_approve: status === "in_review" && critOpen === 0,
      limitations: ["UX Review combines deterministic checks with AI review suggestions."],
      current: {
        id: "rev-1",
        version: 1,
        status,
        artifact_type: "ux_review",
        created_via: "generated",
        parent_version: null,
        created_at: "2026-04-12T12:30:00Z",
        updated_at: "2026-04-12T12:30:00Z",
        submitted_at: null,
        approved_at: null,
        content_hash: hash,
        item_count: 1,
        error: null,
        basis: { prd_version: 1 },
        approval_note: null,
        acknowledged_unverified: false,
        brain_revision: null,
        unverified_count: 0,
        critical_open_count: critOpen,
        review_counts: { total: 1, critical_open: critOpen, open: critOpen, needs_evidence: 0, accepted: critOpen === 0 ? 1 : 0, resolved: 0, deterministic: 1, ai: 0, user: 0 },
        is_stale: false,
        stale_reasons: [],
        editable: status !== "approved",
        warnings: [],
        content: {
          basis: uxBasis,
          summary: "All core requirements covered except one critical confirmation check.",
          limitations: ["UX Review combines deterministic checks with AI review suggestions."],
          findings: [
            {
              id: "UXF-1",
              severity: "critical",
              category: "error_recovery",
              affected_artifact: "wireframes",
              affected_version: 1,
              affected_item_id: "WF-1",
              title: "Missing confirmation before locking published scope baseline",
              reasoning: "Users could lock a baseline accidentally.",
              prd_requirement_ids: ["FR-1"],
              recommended_action: "Add pre-publish confirmation modal.",
              status: critOpen > 0 ? "open" : "accepted",
              resolution_note: critOpen > 0 ? null : "Accepted risk for MVP",
              origin: "deterministic",
              edited_by_user: critOpen === 0,
            },
          ],
        },
      },
    });

    let st = makeReviewState(1, "draft", HASH_U1);
    const api = mockApi({
      ...base,
      "GET /projects/:id/ux/ux_review": () => ({ body: st }),
      "PATCH /projects/:id/ux/ux_review/versions/:v/findings/:fid": () => {
        st = makeReviewState(0, "draft", HASH_U2);
        return { body: { document: st.current, state: st } };
      },
      "POST /projects/:id/ux/ux_review/versions/:v/submit": () => {
        st = makeReviewState(0, "in_review", HASH_U2, "needs_review");
        return { body: st };
      },
      "POST /projects/:id/ux/ux_review/versions/:v/approve": () => {
        st = makeReviewState(0, "approved", HASH_U2, "complete");
        return { body: st };
      },
    });

    renderApp("/projects/p1/ux-review");
    expect(await screen.findByText("Missing confirmation before locking published scope baseline")).toBeInTheDocument();
    expect(screen.getByText("Critical open: 1")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Accept risk" }));
    const dialog = await screen.findByRole("dialog", { name: "Accept risk for UXF-1" });
    await userEvent.type(within(dialog).getByLabelText("Why is this risk accepted?"), "Accepted risk for MVP");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save accepted" }));

    await waitFor(() => expect(api.last("PATCH", "/projects/p1/ux/ux_review/versions/1/findings/UXF-1")?.body).toEqual({
      base_hash: HASH_U1,
      status: "accepted",
      resolution_note: "Accepted risk for MVP",
    }));

    await userEvent.click(screen.getByRole("button", { name: "Submit for review" }));
    await userEvent.click(await screen.findByRole("button", { name: "Approve version 1" }));
    const appDialog = await screen.findByRole("dialog", { name: "Approve UX Review version 1" });
    await userEvent.click(within(appDialog).getByRole("button", { name: "Approve version" }));

    expect(await screen.findByText("UX stage: complete")).toBeInTheDocument();
  });
});
