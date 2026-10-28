import type { DocStatus } from "./strategy";
import type { OptimizationPrerequisitesStatus } from "./optimization";

type PrerequisiteCheck = OptimizationPrerequisitesStatus;

export type ComponentLayer = "frontend" | "backend" | "data" | "integration" | "infrastructure";
export type TrustZone =
  | "public_unauthenticated"
  | "authenticated_user"
  | "privileged_admin"
  | "internal_service"
  | "external_third_party";
export type ImplementationStatus = "proposed_target" | "verified_existing";
export type EntityDecisionStatus = "approved_scope" | "proposed" | "requires_review";
export type DecisionStatus = "proposed" | "accepted" | "requires_review";
export type DiagramType =
  | "system_context"
  | "component"
  | "data_relationship"
  | "request_flow"
  | "deployment";

export interface PrdRequirementSummary {
  id: string;
  title: string;
  kind: "functional" | "non_functional";
}

export interface ArchitectureBasisSummary {
  research_version: number;
  strategy_version: number;
  prd_version: number;
  personas_version: number;
  journeys_version: number;
  ia_version: number;
  wireframes_version: number;
  ux_review_version: number;
  design_system_version: number;
  prototype_version: number;
  valid_req_ids: string[];
  valid_persona_ids: string[];
  valid_journey_ids: string[];
  valid_ia_node_ids: string[];
  valid_wireframe_ids: string[];
  valid_ux_finding_ids: string[];
  valid_design_component_ids: string[];
  valid_design_decision_ids: string[];
  valid_token_names: string[];
  valid_prototype_screen_ids: string[];
  valid_prototype_flow_ids: string[];
  prd_requirements: PrdRequirementSummary[];
}

export interface TrustBoundaryRole {
  role: string;
  persona_ids: string[];
  trust_zone: TrustZone;
  allowed_capabilities: string[];
}

export interface ArchitectureComponent {
  id: string;
  name: string;
  layer: ComponentLayer;
  purpose: string;
  responsibilities: string[];
  communicates_with: string[];
  prd_requirement_ids: string[];
  design_refs: string[];
}

export interface ExternalIntegration {
  id: string;
  name: string;
  purpose: string;
  protocol_or_contract: string;
  failure_mode_and_fallback: string;
  implementation_status: ImplementationStatus;
  prd_requirement_ids: string[];
}

export interface SystemOverview {
  product_scope: string;
  system_boundaries: string[];
  user_roles_and_trust_boundaries: TrustBoundaryRole[];
  components: ArchitectureComponent[];
  external_integrations: ExternalIntegration[];
}

export interface FrontendModuleBoundary {
  id: string;
  module_name: string;
  route_or_feature_scope: string;
  component_id: string;
  prototype_screen_ids: string[];
  design_component_ids: string[];
  design_tokens_used: string[];
  prd_requirement_ids: string[];
}

export interface BackendModuleBoundary {
  id: string;
  module_name: string;
  service_responsibility: string;
  component_id: string;
  prd_requirement_ids: string[];
}

export interface ApplicationArchitecture {
  frontend_boundaries: FrontendModuleBoundary[];
  backend_modules: BackendModuleBoundary[];
  authentication_and_authorization: string;
  state_management_and_data_fetching: string;
  error_handling_and_logging: string;
  configuration_and_env_separation: string;
}

export interface DomainEntity {
  id: string;
  name: string;
  description: string;
  owning_component_id: string;
  key_fields: string[];
  access_boundary: string;
  retention_and_lifecycle: string;
  sensitive_data_handling: string;
  status: EntityDecisionStatus;
  prd_requirement_ids: string[];
}

export interface EntityRelationship {
  source_entity_id: string;
  target_entity_id: string;
  cardinality: "1:1" | "1:N" | "M:N";
  description: string;
}

export interface DataArchitecture {
  entities: DomainEntity[];
  relationships: EntityRelationship[];
  transaction_and_integrity_rules: string[];
  migration_strategy: string;
}

export interface ApiBoundarySpec {
  id: string;
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  path: string;
  summary: string;
  component_id: string;
  entity_ids: string[];
  auth_requirement: "public" | "authenticated" | "role_restricted" | "internal_service";
  request_contract: string;
  response_contract: string;
  validation_and_error_handling: string;
  pagination_and_filtering: string;
  implementation_status: ImplementationStatus;
  prototype_screen_ids: string[];
  prd_requirement_ids: string[];
}

export interface ApiArchitecture {
  endpoints: ApiBoundarySpec[];
  request_response_conventions: string;
  validation_and_error_conventions: string;
  integration_contracts_and_failure_behavior: string;
}

export interface DeploymentServiceSpec {
  id: string;
  name: string;
  environment: "local_dev" | "staging" | "production" | "all";
  responsibility: string;
  component_ids: string[];
  implementation_status: "proposed_target" | "verified_current";
}

export interface DeploymentArchitecture {
  local_development_environment: string;
  services_and_infrastructure: DeploymentServiceSpec[];
  configuration_and_secret_management: string;
  deployment_boundaries: string;
  health_checks_and_observability: string;
  backup_recovery_and_failure: string;
}

export interface ArchitectureDecision {
  id: string;
  title: string;
  status: DecisionStatus;
  context_and_problem: string;
  decision: string;
  alternatives_and_tradeoffs: string[];
  rationale: string;
  consequences_and_risks: string[];
  prd_requirement_ids: string[];
  source_refs: string[];
}

export interface DiagramNode {
  id: string;
  label: string;
  reference_id: string;
}

export interface DiagramEdge {
  from_node: string;
  to_node: string;
  label: string;
}

export interface ArchitectureDiagram {
  id: string;
  diagram_type: DiagramType;
  title: string;
  summary: string;
  nodes: DiagramNode[];
  edges: DiagramEdge[];
  mermaid: string;
}

export interface TraceabilityRow {
  requirement_id: string;
  requirement_title: string;
  requirement_kind: "functional" | "non_functional";
  component_ids: string[];
  entity_ids: string[];
  endpoint_ids: string[];
  integration_ids: string[];
  frontend_module_ids: string[];
  backend_module_ids: string[];
  decision_ids: string[];
  design_refs: string[];
  fully_traced: boolean;
  coverage_gaps: string[];
}

export interface ArchitectureCompleteness {
  complete_traceability: boolean;
  uncovered_requirements: string[];
  unreferenced_components: string[];
  requires_review_decisions: string[];
  proposed_decisions: string[];
  requires_review_entities: string[];
  total_requirements: number;
  traced_requirements: number;
}

export interface ArchitectureContent {
  basis: ArchitectureBasisSummary;
  system_overview: SystemOverview;
  application_architecture: ApplicationArchitecture;
  data_architecture: DataArchitecture;
  api_architecture: ApiArchitecture;
  deployment_architecture: DeploymentArchitecture;
  decisions: ArchitectureDecision[];
  diagrams: ArchitectureDiagram[];
  traceability: TraceabilityRow[];
  methodology_limitations: string[];
}

export interface ArchitectureVersionSummary {
  version: number;
  status: DocStatus;
  created_via: string;
  parent_version: number | null;
  created_at: string | null;
  updated_at: string | null;
  submitted_at: string | null;
  approved_at: string | null;
  content_hash: string | null;
  item_count: number;
  error: string | null;
}

export interface ArchitectureDocument extends ArchitectureVersionSummary {
  id: string;
  content: ArchitectureContent | null;
  basis: Record<string, unknown>;
  approval_note: string | null;
  acknowledged_unverified: boolean;
  brain_revision: number | null;
  unverified_count: number;
  completeness: ArchitectureCompleteness | null;
  is_stale: boolean;
  stale_reasons: string[];
  editable: boolean;
  warnings: { code: string; message: string }[];
}

export interface ArchitectureState {
  status: DocStatus | "not_started";
  prerequisites: PrerequisiteCheck;
  is_stale: boolean;
  stale_reasons: string[];
  current: ArchitectureDocument | null;
  approved_version: number | null;
  history: ArchitectureVersionSummary[];
  last_error: string | null;
  basis_preview: ArchitectureBasisSummary | null;
  lifecycle: {
    stage: "architecture";
    status: string;
    architecture_complete: boolean;
    pending_criteria: string[];
    downstream_stages: Record<string, string>;
  };
  next_step: { key: string; label: string; workspace_path?: string };
  can_generate: boolean;
  needs_supersede: boolean;
  can_submit: boolean;
  can_approve: boolean;
  limitations: string[];
}

export interface ArchitectureEditResponse {
  document: ArchitectureDocument;
  state: ArchitectureState;
}
