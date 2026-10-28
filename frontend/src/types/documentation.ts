export type ExportMode = "official" | "preview";
export type ExportFormat = "zip" | "markdown" | "json";
export type FindingSeverity = "blocking_error" | "warning" | "info";

export interface ArtifactProvenanceEntry {
  artifact_key: string;
  label: string;
  phase: string;
  stage: string;
  workspace_path: string;
  required_for_official: boolean;
  present: boolean;
  approved_version: number | null;
  selected_version: number | null;
  selected_status: string;
  open_draft_version: number | null;
  content_hash: string | null;
  hash_verified: boolean;
  approved_at: string | null;
  updated_at: string | null;
  stale: boolean;
  staleness_reasons: string[];
  included_in_export: boolean;
  omission_reason: string | null;
}

export interface ExportValidationFinding {
  code: string;
  severity: FindingSeverity;
  section: string;
  title: string;
  message: string;
  remediation: string;
  workspace_path: string | null;
}

export interface ValidationSummary {
  ready_for_official_export: boolean;
  blocking_error_count: number;
  warning_count: number;
  info_count: number;
  findings: ExportValidationFinding[];
}

export interface IncludedSection {
  filename: string;
  title: string;
  source_artifacts: string;
}

export interface OmittedSection {
  filename: string;
  title: string;
  reason: string;
}

export interface ExportIntegrity {
  verified: boolean;
  manifest_hash_match: boolean;
  bundle_hash_match: boolean;
  matches_current_sources: boolean;
  stored_snapshot_fingerprint: string | null;
  current_snapshot_fingerprint: string | null;
  manifest_sha256: string;
  recomputed_manifest_sha256: string;
  bundle_sha256: string;
  recomputed_bundle_sha256: string;
}

export interface DocumentationExportSummary {
  id: string;
  project_id: string;
  version: number;
  export_mode: ExportMode;
  status: "completed" | "superseded" | "failed";
  manifest_sha256: string;
  bundle_sha256: string;
  document_count: number;
  document_filenames: string[];
  included_sections: IncludedSection[];
  omitted_sections: OmittedSection[];
  validation_summary: ValidationSummary;
  export_note: string | null;
  brain_revision: number | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  integrity: ExportIntegrity;
}

export interface DocumentationExportDetail extends DocumentationExportSummary {
  manifest: Record<string, unknown>;
  documents: Record<string, string>;
  source_snapshot: Record<string, unknown>;
}

export interface SupportedFormatInfo {
  format: ExportFormat;
  label: string;
  content_type: string;
  extension: string;
  description: string;
}

export interface DocumentationWorkspaceState {
  project: {
    id: string;
    name: string;
    description: string;
  };
  stage_key: string;
  stage_status: string;
  depends_on: string[];
  unmet_dependencies: string[];
  completion_check: {
    complete: boolean;
    blocking_reasons: string[];
  };
  snapshot_fingerprint: string;
  brain_version: number;
  artifact_inventory: ArtifactProvenanceEntry[];
  included_sections: IncludedSection[];
  omitted_sections: OmittedSection[];
  validation_summary: ValidationSummary;
  preview_manifest_sha256: string;
  preview_bundle_sha256: string;
  current_official_export: DocumentationExportSummary | null;
  export_history: DocumentationExportSummary[];
  supported_formats: SupportedFormatInfo[];
  unsupported_formats_note: string;
}

export interface DocumentationPreviewResponse {
  export_mode: ExportMode;
  include_drafts_or_stale: boolean;
  official_approved_bundle: boolean;
  snapshot_fingerprint: string;
  brain_version: number;
  artifact_inventory: ArtifactProvenanceEntry[];
  included_sections: IncludedSection[];
  omitted_sections: OmittedSection[];
  validation_summary: ValidationSummary;
  manifest: Record<string, unknown>;
  manifest_sha256: string;
  bundle_sha256: string;
  bundle_size_bytes: number;
  documents: Record<string, string>;
}

export interface GenerateExportResponse {
  export: DocumentationExportDetail;
  workspace: DocumentationWorkspaceState;
}
