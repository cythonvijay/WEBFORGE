import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { authed, project, renderApp } from "./helpers";
import { mockApi } from "./mockApi";

const base = { ...authed, "GET /projects/:id": { body: project() } };
const HASH_D1 = "d".repeat(64);

const designBasis = {
  research_version: 1,
  strategy_version: 1,
  prd_version: 1,
  personas_version: 1,
  journeys_version: 1,
  ia_version: 1,
  wireframes_version: 1,
  ux_review_version: 1,
  design_system_version: 1,
  valid_req_ids: ["FR-1", "FR-2"],
  valid_persona_ids: ["P-1"],
  valid_journey_ids: ["J-1"],
  valid_ia_node_ids: ["IA-1", "IA-2"],
  valid_wireframe_ids: ["WF-1", "WF-2"],
  valid_ux_finding_ids: ["UXF-1"],
  valid_component_ids: ["CMP-1"],
  valid_token_names: ["--color-primary"],
  token_preview: { "--color-primary": "#1E40AF" },
};

describe("Phase 12 Design System & Interactive Prototype", () => {
  it("exposes Design System and Prototype without Phase 12 placeholder badges while keeping Architecture badged as Phase 13", async () => {
    mockApi({
      ...base,
      "GET /projects/:id/design/design_system": {
        body: {
          artifact_type: "design_system",
          status: "not_started",
          prerequisites: { ready: true, missing: [], upstream_versions: {} },
          is_stale: false,
          stale_reasons: [],
          current: null,
          approved_version: null,
          history: [],
          last_error: null,
          basis_preview: designBasis,
          lifecycle: { stage: "design", status: "not_started", design_complete: false, pending_criteria: [] },
          next_step: { key: "start", label: "Generate design system from approved UX and PRD artifacts" },
          can_generate: true,
          needs_supersede: false,
          can_submit: false,
          can_approve: false,
          limitations: ["Design tokens, component specifications, and design decisions are synthesized from your approved PRD and UX artifacts."],
        },
      },
    });
    renderApp("/projects/p1/design-system");
    await screen.findByRole("heading", { name: "Design System" });
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: /^Design System$/ })).not.toHaveTextContent("Phase 12");
    expect(within(nav).getByRole("link", { name: /^Prototype$/ })).not.toHaveTextContent("Phase 12");
    expect(within(nav).getByRole("link", { name: /^Architecture$/ })).not.toHaveTextContent("Phase 13");
    expect(within(nav).getByRole("link", { name: /Frontend/ })).toHaveTextContent("Phase 13");
  });

  it("renders interactive prototype screen navigation, form validation, simulated dialogs, and screen index", async () => {
    mockApi({
      ...base,
      "GET /projects/:id/design/prototype": {
        body: {
          artifact_type: "prototype",
          status: "draft",
          prerequisites: { ready: true, missing: [], upstream_versions: {} },
          is_stale: false,
          stale_reasons: [],
          approved_version: null,
          history: [],
          last_error: null,
          basis_preview: null,
          lifecycle: { stage: "design", status: "in_progress", design_complete: false, pending_criteria: [] },
          next_step: { key: "review_and_submit", label: "Review and edit specifications" },
          can_generate: true,
          needs_supersede: true,
          can_submit: true,
          can_approve: false,
          limitations: ["Interactive Prototype is a simulated specification player."],
          current: {
            id: "proto-1",
            version: 1,
            status: "draft",
            artifact_type: "prototype",
            created_via: "generated",
            parent_version: null,
            created_at: "2026-04-12T14:00:00Z",
            updated_at: "2026-04-12T14:00:00Z",
            submitted_at: null,
            approved_at: null,
            content_hash: HASH_D1,
            item_count: 2,
            error: null,
            basis: { design_system_version: 1 },
            approval_note: null,
            acknowledged_unverified: false,
            brain_revision: null,
            unverified_count: 0,
            is_stale: false,
            stale_reasons: [],
            editable: true,
            warnings: [],
            content: {
              basis: designBasis,
              limitations: ["Interactive Prototype is a simulated specification player."],
              screens: [
                {
                  id: "SCR-1",
                  wireframe_id: "WF-1",
                  ia_node_id: "IA-1",
                  title: "Projects Dashboard",
                  route_path: "/projects",
                  purpose: "List agency projects.",
                  component_ids: ["CMP-1"],
                  regions: [{ region: "main", heading: "Projects Grid", components: [{ id: "c1", kind: "card_grid", label: "Cards", content_role: "Projects", elements: ["Card"] }] }],
                  form_fields: [],
                  interactions: [
                    {
                      id: "ix-1",
                      trigger_label: "Open Baseline Editor",
                      trigger_kind: "primary_button",
                      action_type: "navigate",
                      target_screen_id: "SCR-2",
                      dialog_title: null,
                      dialog_body: null,
                      resulting_state: "default",
                      simulation_note: "Navigates to SCR-2",
                    },
                  ],
                  states: { loading: "Loading projects…", empty: "No projects", error: "Error loading", success: "Saved" },
                  responsive_behavior: { desktop: "3-col grid", tablet: "2-col grid", mobile: "1-col stack" },
                  mock_data_note: "Sample projects loaded.",
                  journey_ids: ["J-1"],
                  prd_requirement_ids: ["FR-1"],
                  origin: "ai",
                  edited_by_user: false,
                },
                {
                  id: "SCR-2",
                  wireframe_id: "WF-2",
                  ia_node_id: "IA-2",
                  title: "Scope Baseline Editor",
                  route_path: "/projects/:id/baseline",
                  purpose: "Edit and publish scope items.",
                  component_ids: ["CMP-1"],
                  regions: [{ region: "main", heading: "Editor", components: [{ id: "c2", kind: "form", label: "Form", content_role: "Edit", elements: ["Input"] }] }],
                  form_fields: [
                    {
                      name: "deliverable_title",
                      label: "Deliverable title",
                      field_type: "text",
                      required: true,
                      placeholder: "Enter deliverable",
                      default_mock_value: "",
                      validation_rule: "Required 3-200 chars",
                    },
                  ],
                  interactions: [
                    {
                      id: "ix-2",
                      trigger_label: "Save Deliverable",
                      trigger_kind: "form_submit",
                      action_type: "submit_form",
                      target_screen_id: null,
                      dialog_title: null,
                      dialog_body: null,
                      resulting_state: "success",
                      simulation_note: "Validates form locally",
                    },
                    {
                      id: "ix-3",
                      trigger_label: "Publish Baseline",
                      trigger_kind: "primary_button",
                      action_type: "open_dialog",
                      target_screen_id: null,
                      dialog_title: "Confirm Baseline Lock",
                      dialog_body: "Locking Baseline v1 makes it read-only for client review.",
                      resulting_state: "default",
                      simulation_note: "Opens confirmation modal",
                    },
                  ],
                  states: { loading: "Saving…", empty: "No items", error: "Validation failed", success: "Deliverable saved to baseline!" },
                  responsive_behavior: { desktop: "Split view", tablet: "Stacked view", mobile: "Mobile tabs" },
                  mock_data_note: "Sample baseline draft.",
                  journey_ids: ["J-1"],
                  prd_requirement_ids: ["FR-1"],
                  origin: "ai",
                  edited_by_user: false,
                },
              ],
              flows: [
                {
                  id: "FLOW-1",
                  journey_id: "J-1",
                  title: "Create and Publish Scope Baseline",
                  start_screen_id: "SCR-1",
                  ordered_screen_ids: ["SCR-1", "SCR-2"],
                  happy_path_steps: ["Click Open Baseline Editor on SCR-1", "Fill Deliverable title and Save on SCR-2"],
                },
              ],
            },
          },
        },
      },
    });

    renderApp("/projects/p1/prototype");
    expect(await screen.findByTestId("proto-screen-SCR-1")).toBeInTheDocument();

    // Navigate from SCR-1 to SCR-2 via interactive trigger button
    await userEvent.click(screen.getByRole("button", { name: "Open Baseline Editor" }));
    expect(await screen.findByTestId("proto-screen-SCR-2")).toBeInTheDocument();

    // Submitting empty required form field shows inline validation error
    await userEvent.click(screen.getByRole("button", { name: "Save Deliverable" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Deliverable title is required");

    // Typing a value and submitting transitions to simulated success state
    await userEvent.type(screen.getByLabelText(/Deliverable title/), "Homepage design");
    await userEvent.click(screen.getByRole("button", { name: "Save Deliverable" }));
    expect(await screen.findByTestId("proto-state-view")).toHaveTextContent("Deliverable saved to baseline!");

    // Return to default layout and open simulated confirmation dialog
    await userEvent.click(screen.getByRole("button", { name: "Return to default layout" }));
    await userEvent.click(screen.getByRole("button", { name: "Publish Baseline" }));
    expect(await screen.findByRole("dialog", { name: /Confirm Baseline Lock/ })).toBeInTheDocument();
  });
});
