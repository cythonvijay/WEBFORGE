import type { StageStatus } from "./lifecycle";
import type { DocStatus } from "./strategy";
import type { ViewportKind, WireframeRegion, WireframeResponsive, WireframeStates } from "./ux";

export type DesignArtifactType = "design_system" | "prototype";
export type ComponentCategory = "buttons_links" | "inputs_controls" | "validation_feedback" | "navigation" | "containers_dialogs" | "tables_lists" | "states";
export type ComponentState = "default" | "hover" | "focus" | "active" | "disabled" | "loading" | "error" | "success" | "empty";
export type DecisionStatus = "proposed" | "reviewed" | "approved";
export type TriggerKind = "primary_button" | "secondary_button" | "nav_link" | "form_submit" | "row_action";
export type InteractionAction = "navigate" | "open_dialog" | "submit_form" | "set_state";
export type UiStateKind = "default" | "loading" | "empty" | "error" | "success";

export interface DesignBasisSummary {
  research_version: number;
  strategy_version: number;
  prd_version: number;
  personas_version: number;
  journeys_version: number;
  ia_version: number;
  wireframes_version: number;
  ux_review_version: number;
  design_system_version: number | null;
  valid_req_ids: string[];
  valid_persona_ids: string[];
  valid_journey_ids: string[];
  valid_ia_node_ids: string[];
  valid_wireframe_ids: string[];
  valid_ux_finding_ids: string[];
  valid_component_ids: string[];
  valid_token_names: string[];
  token_preview: Record<string, string>;
}

export interface ColorToken {
  token: string;
  role: string;
  hex_value: string;
  usage: string;
  contrast_note: string;
}

export interface TypographyToken {
  token: string;
  role: string;
  font_family: string;
  font_size: string;
  line_height: string;
  font_weight: string;
}

export interface SpacingToken {
  token: string;
  value: string;
  usage: string;
}

export interface GridAndBreakpoints {
  columns: number;
  gutter: string;
  max_width: string;
  desktop: string;
  tablet: string;
  mobile: string;
}

export interface SurfaceTokens {
  radii: string[];
  borders: string[];
  elevation_shadows: string[];
}

export interface DesignFoundations {
  color_tokens: ColorToken[];
  typography_scale: TypographyToken[];
  spacing_scale: SpacingToken[];
  grid_breakpoints: GridAndBreakpoints;
  surface_tokens: SurfaceTokens;
  icon_guidelines: string[];
  accessibility_notes: string[];
}

export interface ComponentSpec {
  id: string;
  name: string;
  category: ComponentCategory;
  purpose: string;
  variants: string[];
  states: ComponentState[];
  design_tokens_used: string[];
  responsive_behavior: string;
  accessibility_notes: string;
  wireframe_ids: string[];
  prd_requirement_ids: string[];
  origin: "ai" | "user";
  edited_by_user: boolean;
}

export interface DesignDecision {
  id: string;
  title: string;
  chosen_value_or_rule: string;
  rationale: string;
  supporting_refs: string[];
  assumptions: string[];
  unresolved_questions: string[];
  status: DecisionStatus;
  origin: "ai" | "user";
  edited_by_user: boolean;
  note: string | null;
}

export interface DesignSystemContent {
  basis: DesignBasisSummary;
  foundations: DesignFoundations;
  components: ComponentSpec[];
  decisions: DesignDecision[];
  limitations: string[];
}

export interface PrototypeFormField {
  name: string;
  label: string;
  field_type: "text" | "textarea" | "select" | "checkbox" | "radio" | "date" | "number";
  required: boolean;
  placeholder: string;
  default_mock_value: string;
  validation_rule: string;
}

export interface PrototypeInteraction {
  id: string;
  trigger_label: string;
  trigger_kind: TriggerKind;
  action_type: InteractionAction;
  target_screen_id: string | null;
  dialog_title: string | null;
  dialog_body: string | null;
  resulting_state: UiStateKind;
  simulation_note: string;
}

export interface PrototypeScreen {
  id: string;
  wireframe_id: string;
  ia_node_id: string;
  title: string;
  route_path: string;
  purpose: string;
  component_ids: string[];
  regions: WireframeRegion[];
  form_fields: PrototypeFormField[];
  interactions: PrototypeInteraction[];
  states: WireframeStates;
  responsive_behavior: WireframeResponsive;
  mock_data_note: string;
  journey_ids: string[];
  prd_requirement_ids: string[];
  origin: "ai" | "user";
  edited_by_user: boolean;
}

export interface PrototypeFlow {
  id: string;
  journey_id: string;
  title: string;
  start_screen_id: string;
  ordered_screen_ids: string[];
  happy_path_steps: string[];
}

export interface PrototypeContent {
  basis: DesignBasisSummary;
  screens: PrototypeScreen[];
  flows: PrototypeFlow[];
  limitations: string[];
}

export interface DesignSummary {
  version: number;
  status: Exclude<DocStatus, "not_started">;
  artifact_type: DesignArtifactType;
  created_via: string;
  parent_version: number | null;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  approved_at: string | null;
  content_hash: string | null;
  item_count: number;
  error: string | null;
}

export interface DesignDocument<C = unknown> extends DesignSummary {
  id: string;
  content: C | null;
  basis: Record<string, unknown>;
  approval_note: string | null;
  acknowledged_unverified: boolean;
  brain_revision: number | null;
  unverified_count: number;
  is_stale: boolean;
  stale_reasons: string[];
  editable: boolean;
  warnings: { code: string; message: string }[];
}

export interface DesignArtifactState<C = unknown> {
  artifact_type: DesignArtifactType;
  status: DocStatus;
  prerequisites: {
    ready: boolean;
    missing: { artifact: string; label: string; message: string; workspace_path: string }[];
    upstream_versions: Record<string, number | null>;
  };
  is_stale: boolean;
  stale_reasons: string[];
  current: DesignDocument<C> | null;
  approved_version: number | null;
  history: DesignSummary[];
  last_error: string | null;
  basis_preview: DesignBasisSummary | null;
  lifecycle: {
    stage: "design";
    status: StageStatus;
    design_complete: boolean;
    pending_criteria: string[];
  };
  next_step: { key: string; label: string; workspace_path?: string };
  can_generate: boolean;
  needs_supersede: boolean;
  can_submit: boolean;
  can_approve: boolean;
  limitations: string[];
}

export interface DesignEditResponse<C = unknown> {
  document: DesignDocument<C>;
  state: DesignArtifactState<C>;
}
