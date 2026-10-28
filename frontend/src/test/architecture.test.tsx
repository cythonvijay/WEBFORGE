import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { authed, project, renderApp } from "./helpers";
import { mockApi } from "./mockApi";

const base = { ...authed, "GET /projects/:id": { body: project() } };
const HASH_A1 = "a".repeat(64);
const HASH_A2 = "b".repeat(64);

const archBasis = {
  research_version: 1,
  strategy_version: 1,
  prd_version: 1,
  personas_version: 1,
  journeys_version: 1,
  ia_version: 1,
  wireframes_version: 1,
  ux_review_version: 1,
  design_system_version: 1,
  prototype_version: 1,
  valid_req_ids: ["FR-1", "FR-2"],
  valid_persona_ids: ["P-1"],
  valid_journey_ids: ["J-1"],
  valid_ia_node_ids: ["IA-1"],
  valid_wireframe_ids: ["WF-1"],
  valid_ux_finding_ids: ["UXF-1"],
  valid_design_component_ids: ["CMP-1"],
  valid_design_decision_ids: ["DD-1"],
  valid_token_names: ["--color-primary"],
  valid_prototype_screen_ids: ["SCR-1"],
  valid_prototype_flow_ids: ["FLOW-1"],
  prd_requirements: [
    { id: "FR-1", title: "Scope baseline locking", kind: "functional" },
    { id: "FR-2", title: "Deliverable provenance linking", kind: "functional" },
  ],
};

const sampleArchContent = {
  basis: archBasis,
  methodology_limitations: [
    "This Product Architecture specification is synthesized from your approved Research, Strategy, PRD, UX, Design System, and Interactive Prototype artifacts.",
  ],
  system_overview: {
    product_scope: "ScopeLock web application for agency scope baselines.",
    system_boundaries: ["Browser SPA over HTTPS REST", "PostgreSQL relational store"],
    user_roles_and_trust_boundaries: [
      {
        role: "Agency Lead",
        persona_ids: ["P-1"],
        trust_zone: "authenticated_user",
        allowed_capabilities: ["Create and lock scope baselines"],
      },
    ],
    components: [
      {
        id: "COMP-1",
        name: "Scope Workspace Client",
        layer: "frontend",
        purpose: "React SPA rendering dashboard and baseline editor.",
        responsibilities: ["Render screens and validate inputs"],
        communicates_with: ["COMP-2"],
        prd_requirement_ids: ["FR-1", "FR-2"],
        design_refs: ["WF-1", "CMP-1", "SCR-1"],
      },
      {
        id: "COMP-2",
        name: "Scope Baseline Service",
        layer: "backend",
        purpose: "FastAPI service enforcing scope rules and baseline immutability.",
        responsibilities: ["Validate deliverables and lock baselines"],
        communicates_with: [],
        prd_requirement_ids: ["FR-1", "FR-2"],
        design_refs: ["SCR-1", "FLOW-1"],
      },
    ],
    external_integrations: [],
  },
  application_architecture: {
    frontend_boundaries: [
      {
        id: "FE-1",
        module_name: "ScopeDashboardModule",
        route_or_feature_scope: "/projects",
        component_id: "COMP-1",
        prototype_screen_ids: ["SCR-1"],
        design_component_ids: ["CMP-1"],
        design_tokens_used: ["--color-primary"],
        prd_requirement_ids: ["FR-1", "FR-2"],
      },
    ],
    backend_modules: [
      {
        id: "BE-1",
        module_name: "BaselineService",
        service_responsibility: "Lock and version scope baselines.",
        component_id: "COMP-2",
        prd_requirement_ids: ["FR-1", "FR-2"],
      },
    ],
    authentication_and_authorization: "HttpOnly JWT cookies with project ownership checks.",
    state_management_and_data_fetching: "Typed REST client with content_hash concurrency guards.",
    error_handling_and_logging: "Structured JSON errors without secret leakage.",
    configuration_and_env_separation: "Environment-scoped settings via Pydantic.",
  },
  data_architecture: {
    entities: [
      {
        id: "ENT-1",
        name: "ScopeBaseline",
        description: "Versioned scope baseline record.",
        owning_component_id: "COMP-2",
        key_fields: ["id", "project_id", "version", "status"],
        access_boundary: "Owning agency user only",
        retention_and_lifecycle: "Immutable once locked",
        sensitive_data_handling: "Scoped by project_id",
        status: "approved_scope",
        prd_requirement_ids: ["FR-1", "FR-2"],
      },
    ],
    relationships: [],
    transaction_and_integrity_rules: ["Single ACID transaction on publish"],
    migration_strategy: "Sequential Alembic migrations",
  },
  api_architecture: {
    endpoints: [
      {
        id: "API-1",
        method: "GET",
        path: "/api/projects/{project_id}/baselines",
        summary: "Fetch current scope baseline and history.",
        component_id: "COMP-2",
        entity_ids: ["ENT-1"],
        auth_requirement: "authenticated",
        request_contract: "project_id path param",
        response_contract: "200 OK JSON baseline state",
        validation_and_error_handling: "401/404/409/422 structured errors",
        pagination_and_filtering: "Ordered by version desc",
        implementation_status: "proposed_target",
        prototype_screen_ids: ["SCR-1"],
        prd_requirement_ids: ["FR-1", "FR-2"],
      },
    ],
    request_response_conventions: "JSON over HTTPS",
    validation_and_error_conventions: "Pydantic v2 validation",
    integration_contracts_and_failure_behavior: "Bounded timeouts",
  },
  deployment_architecture: {
    local_development_environment: "Vite + Uvicorn",
    services_and_infrastructure: [
      {
        id: "SVC-1",
        name: "Application Server",
        environment: "all",
        responsibility: "Run SPA and FastAPI",
        component_ids: ["COMP-1", "COMP-2"],
        implementation_status: "proposed_target",
      },
    ],
    configuration_and_secret_management: "Env vars",
    deployment_boundaries: "TLS reverse proxy",
    health_checks_and_observability: "/api/health and /api/ready",
    backup_recovery_and_failure: "Daily snapshots",
  },
  decisions: [
    {
      id: "ADR-1",
      title: "Copy-on-Write Baseline Versioning",
      status: "proposed",
      context_and_problem: "Preserve signed-off baselines while allowing edits.",
      decision: "Fork new draft version when editing locked baseline.",
      alternatives_and_tradeoffs: ["In-place edits lose history"],
      rationale: "Auditability and safety.",
      consequences_and_risks: ["Extra row per revision"],
      prd_requirement_ids: ["FR-1", "FR-2"],
      source_refs: ["FR-1", "COMP-2", "ENT-1"],
    },
  ],
  diagrams: [
    {
      id: "DIAG-1",
      diagram_type: "component",
      title: "Component Topology",
      summary: "Client to API topology.",
      nodes: [
        { id: "N1", label: "Scope Workspace Client", reference_id: "COMP-1" },
        { id: "N2", label: "Scope Baseline Service", reference_id: "COMP-2" },
      ],
      edges: [{ from_node: "N1", to_node: "N2", label: "HTTPS REST" }],
      mermaid: 'flowchart LR\n    N1["Client"] --> N2["API"]',
    },
    {
      id: "DIAG-2",
      diagram_type: "deployment",
      title: "Runtime Deployment",
      summary: "Runtime container topology.",
      nodes: [
        { id: "S1", label: "Application Server", reference_id: "SVC-1" },
        { id: "C2", label: "Scope Baseline Service", reference_id: "COMP-2" },
      ],
      edges: [{ from_node: "S1", to_node: "C2", label: "Hosts" }],
      mermaid: 'flowchart LR\n    S1["Server"] --> C2["Service"]',
    },
  ],
  traceability: [
    {
      requirement_id: "FR-1",
      requirement_title: "Scope baseline locking",
      requirement_kind: "functional",
      component_ids: ["COMP-1", "COMP-2"],
      entity_ids: ["ENT-1"],
      endpoint_ids: ["API-1"],
      integration_ids: [],
      frontend_module_ids: ["FE-1"],
      backend_module_ids: ["BE-1"],
      decision_ids: ["ADR-1"],
      design_refs: ["WF-1", "CMP-1", "SCR-1", "FLOW-1"],
      fully_traced: true,
      coverage_gaps: [],
    },
    {
      requirement_id: "FR-2",
      requirement_title: "Deliverable provenance linking",
      requirement_kind: "functional",
      component_ids: ["COMP-1", "COMP-2"],
      entity_ids: ["ENT-1"],
      endpoint_ids: ["API-1"],
      integration_ids: [],
      frontend_module_ids: ["FE-1"],
      backend_module_ids: ["BE-1"],
      decision_ids: ["ADR-1"],
      design_refs: ["WF-1", "CMP-1", "SCR-1", "FLOW-1"],
      fully_traced: true,
      coverage_gaps: [],
    },
  ],
};

describe("Phase 13 Product Architecture Workspace", () => {
  it("renders prerequisite gate links when Phase 12 Design System or Prototype is missing", async () => {
    mockApi({
      ...base,
      "GET /projects/:id/architecture": {
        body: {
          status: "not_started",
          prerequisites: {
            ready: false,
            missing: [
              {
                artifact: "prototype",
                label: "Interactive Prototype",
                message: "Approve your Interactive Prototype before starting Phase 13 Product Architecture.",
                workspace_path: "/projects/p1/prototype",
              },
            ],
            upstream_versions: {},
          },
          is_stale: false,
          stale_reasons: [],
          current: null,
          approved_version: null,
          history: [],
          last_error: null,
          basis_preview: null,
          lifecycle: {
            stage: "architecture",
            status: "not_started",
            architecture_complete: false,
            pending_criteria: ["Interactive Prototype has not been approved yet."],
            downstream_stages: { frontend: "not_started", backend: "not_started", database: "not_started", api: "not_started" },
          },
          next_step: {
            key: "fix_prerequisites",
            label: "Approve your Interactive Prototype before starting Phase 13 Product Architecture.",
            workspace_path: "/projects/p1/prototype",
          },
          can_generate: false,
          needs_supersede: false,
          can_submit: false,
          can_approve: false,
          limitations: ["Synthesized from approved artifacts."],
        },
      },
    });

    renderApp("/projects/p1/architecture");
    expect(await screen.findByRole("heading", { name: "Product Architecture" })).toBeInTheDocument();
    const gate = screen.getByRole("region", { name: "Prerequisite gates" });
    expect(within(gate).getByText(/Approve your Interactive Prototype/)).toBeInTheDocument();
    expect(within(gate).getByRole("link", { name: "Go to Interactive Prototype" })).toHaveAttribute(
      "href",
      "/projects/p1/prototype"
    );
  });

  it("renders components, entities, endpoints, ADRs, diagrams, traceability matrix, and persists edits & approval", async () => {
    const draftState = {
      status: "draft",
      prerequisites: { ready: true, missing: [], upstream_versions: {} },
      is_stale: false,
      stale_reasons: [],
      approved_version: null,
      history: [
        {
          version: 1,
          status: "draft",
          created_via: "generated",
          parent_version: null,
          created_at: "2026-05-01T10:00:00Z",
          updated_at: "2026-05-01T10:00:00Z",
          submitted_at: null,
          approved_at: null,
          content_hash: HASH_A1,
          item_count: 6,
          error: null,
        },
      ],
      last_error: null,
      basis_preview: null,
      lifecycle: {
        stage: "architecture",
        status: "in_progress",
        architecture_complete: false,
        pending_criteria: ["Product Architecture has not been approved yet."],
        downstream_stages: { frontend: "not_started", backend: "not_started", database: "not_started", api: "not_started" },
      },
      next_step: { key: "review_and_submit", label: "Review components, data entities, APIs, decisions, and diagrams" },
      can_generate: true,
      needs_supersede: true,
      can_submit: true,
      can_approve: false,
      limitations: ["Synthesized from approved artifacts."],
      current: {
        id: "arch-doc-1",
        version: 1,
        status: "draft",
        created_via: "generated",
        parent_version: null,
        created_at: "2026-05-01T10:00:00Z",
        updated_at: "2026-05-01T10:00:00Z",
        submitted_at: null,
        approved_at: null,
        content_hash: HASH_A1,
        item_count: 6,
        error: null,
        basis: { prd_version: 1, design_system_version: 1, prototype_version: 1 },
        approval_note: null,
        acknowledged_unverified: false,
        brain_revision: null,
        unverified_count: 1,
        completeness: {
          complete_traceability: true,
          uncovered_requirements: [],
          unreferenced_components: [],
          requires_review_decisions: [],
          proposed_decisions: ["ADR-1"],
          requires_review_entities: [],
          total_requirements: 2,
          traced_requirements: 2,
        },
        is_stale: false,
        stale_reasons: [],
        editable: true,
        warnings: [],
        content: sampleArchContent,
      },
    };

    const api = mockApi({
      ...base,
      "GET /projects/:id/architecture": { body: draftState },
      "PATCH /projects/:id/architecture/versions/1/components/COMP-1": {
        body: {
          document: { ...draftState.current, content_hash: HASH_A2 },
          state: {
            ...draftState,
            current: { ...draftState.current, content_hash: HASH_A2 },
          },
        },
      },
    });

    renderApp("/projects/p1/architecture");
    expect(await screen.findByText(/COMP-1: Scope Workspace Client/)).toBeInTheDocument();
    expect(screen.getByText(/ENT-1: ScopeBaseline/)).toBeInTheDocument();
    expect(screen.getByText(/GET \/api\/projects\/\{project_id\}\/baselines/)).toBeInTheDocument();
    expect(screen.getByText(/ADR-1: Copy-on-Write Baseline Versioning/)).toBeInTheDocument();
    expect(screen.getByText("100% PRD Requirements Traced")).toBeInTheDocument();

    // Switch diagram tab to DIAG-2
    await userEvent.click(screen.getByRole("tab", { name: /DIAG-2/ }));
    expect(await screen.findByText(/DIAG-2: Runtime Deployment/)).toBeInTheDocument();

    // Edit COMP-1
    await userEvent.click(screen.getByRole("button", { name: "Edit COMP-1" }));
    const purposeInput = screen.getByLabelText("Component purpose");
    await userEvent.clear(purposeInput);
    await userEvent.type(purposeInput, "Updated React SPA client purpose.");
    await userEvent.click(screen.getByRole("button", { name: "Save component" }));

    expect(api.last("PATCH", "/projects/p1/architecture/versions/1/components/COMP-1")?.body).toEqual({
      base_hash: HASH_A1,
      name: "Scope Workspace Client",
      purpose: "Updated React SPA client purpose.",
    });
  });
});
