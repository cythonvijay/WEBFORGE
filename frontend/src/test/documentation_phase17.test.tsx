import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { authed, project, renderApp } from "./helpers";
import { mockApi } from "./mockApi";

const base = { ...authed, "GET /projects/:id": { body: project() } };
const HASH_64 = "a".repeat(64);
const BUNDLE_SHA = "b".repeat(64);
const MANIFEST_SHA = "c".repeat(64);

const sampleWorkspaceReady = {
  project: {
    id: "p1",
    name: "ScopeLock",
    description: "Agency Scope Baseline Platform",
  },
  stage_key: "documentation",
  stage_status: "in_progress",
  depends_on: ["architecture"],
  unmet_dependencies: [],
  completion_check: {
    complete: false,
    blocking_reasons: [
      "No official documentation bundle has been generated yet (previews alone do not complete the documentation stage).",
    ],
  },
  snapshot_fingerprint: HASH_64,
  brain_version: 14,
  artifact_inventory: [
    {
      artifact_key: "research",
      label: "User & Market Research",
      phase: "Phase 9",
      stage: "research",
      workspace_path: "/projects/p1/research",
      required_for_official: true,
      present: true,
      approved_version: 1,
      selected_version: 1,
      selected_status: "approved",
      open_draft_version: null,
      content_hash: HASH_64,
      hash_verified: true,
      approved_at: "2026-10-28T00:00:00Z",
      updated_at: "2026-10-28T00:00:00Z",
      stale: false,
      staleness_reasons: [],
      included_in_export: true,
      omission_reason: null,
    },
    {
      artifact_key: "architecture",
      label: "Product Architecture",
      phase: "Phase 13",
      stage: "architecture",
      workspace_path: "/projects/p1/architecture",
      required_for_official: true,
      present: true,
      approved_version: 1,
      selected_version: 1,
      selected_status: "approved",
      open_draft_version: null,
      content_hash: HASH_64,
      hash_verified: true,
      approved_at: "2026-10-28T00:00:00Z",
      updated_at: "2026-10-28T00:00:00Z",
      stale: false,
      staleness_reasons: [],
      included_in_export: true,
      omission_reason: null,
    },
  ],
  included_sections: [
    { filename: "README.md", title: "Project Summary, Scope & Bundle Inventory", source_artifacts: "project, brain" },
    { filename: "01-research.md", title: "User & Market Research", source_artifacts: "research" },
    { filename: "06-architecture.md", title: "Product Architecture & ADRs", source_artifacts: "architecture" },
  ],
  omitted_sections: [],
  validation_summary: {
    ready_for_official_export: true,
    blocking_error_count: 0,
    warning_count: 0,
    info_count: 1,
    findings: [
      {
        code: "PRELIMINARY_RESEARCH_MODE",
        severity: "info",
        section: "research",
        title: "Research report was generated in preliminary mode",
        message: "Synthesized from user-confirmed discovery facts without live web crawling.",
        remediation: "Disclosed in 01-research.md and MANIFEST.json.",
        workspace_path: "/projects/p1/research",
      },
    ],
  },
  preview_manifest_sha256: MANIFEST_SHA,
  preview_bundle_sha256: BUNDLE_SHA,
  current_official_export: null,
  export_history: [],
  supported_formats: [
    {
      format: "zip",
      label: "Markdown Documentation Bundle (.zip)",
      content_type: "application/zip",
      extension: ".zip",
      description: "Complete UTF-8 Markdown documentation archive.",
    },
    {
      format: "markdown",
      label: "Consolidated Specification (.md)",
      content_type: "text/markdown; charset=utf-8",
      extension: ".md",
      description: "Single consolidated Markdown document.",
    },
    {
      format: "json",
      label: "Validated Project Specification (.json)",
      content_type: "application/json; charset=utf-8",
      extension: ".json",
      description: "Machine-readable JSON bundle.",
    },
  ],
  unsupported_formats_note:
    "PDF export is intentionally not enabled in Phase 17 so WebForge never emits a fake .pdf containing raw HTML/Markdown.",
};

const samplePreviewResponse = {
  export_mode: "official",
  include_drafts_or_stale: false,
  official_approved_bundle: true,
  snapshot_fingerprint: HASH_64,
  brain_version: 14,
  artifact_inventory: sampleWorkspaceReady.artifact_inventory,
  included_sections: sampleWorkspaceReady.included_sections,
  omitted_sections: [],
  validation_summary: sampleWorkspaceReady.validation_summary,
  manifest: {
    schema_version: "webforge.documentation_export.v1",
    export_mode: "official",
    official_approved_bundle: true,
  },
  manifest_sha256: MANIFEST_SHA,
  bundle_sha256: BUNDLE_SHA,
  bundle_size_bytes: 12480,
  documents: {
    "README.md": "# ScopeLock — WebForge Product Specification & Documentation Bundle\n\nOfficial approved specification.",
    "01-research.md": "# 01 — User & Market Research: ScopeLock\n\nApproved Research v1.",
    "06-architecture.md": "# 06 — Product Architecture & ADRs: ScopeLock\n\nApproved Architecture v1.",
  },
};

describe("Phase 17 Documentation & Export Workspace", () => {
  it("renders artifact inventory, validation disclosures, preview tabs, and generates an official export", async () => {
    const completedExport = {
      id: "exp-1",
      project_id: "p1",
      version: 1,
      export_mode: "official",
      status: "completed",
      manifest_sha256: MANIFEST_SHA,
      bundle_sha256: BUNDLE_SHA,
      document_count: 3,
      document_filenames: ["README.md", "01-research.md", "06-architecture.md", "MANIFEST.json"],
      included_sections: sampleWorkspaceReady.included_sections,
      omitted_sections: [],
      validation_summary: sampleWorkspaceReady.validation_summary,
      export_note: "Phase 17 release candidate",
      brain_revision: 15,
      created_by: "u1",
      created_at: "2026-10-28T01:00:00Z",
      updated_at: "2026-10-28T01:00:00Z",
      integrity: {
        verified: true,
        manifest_hash_match: true,
        bundle_hash_match: true,
        matches_current_sources: true,
        stored_snapshot_fingerprint: HASH_64,
        current_snapshot_fingerprint: HASH_64,
        manifest_sha256: MANIFEST_SHA,
        recomputed_manifest_sha256: MANIFEST_SHA,
        bundle_sha256: BUNDLE_SHA,
        recomputed_bundle_sha256: BUNDLE_SHA,
      },
      manifest: samplePreviewResponse.manifest,
      documents: samplePreviewResponse.documents,
      source_snapshot: { snapshot_fingerprint: HASH_64 },
    };

    mockApi({
      ...base,
      "GET /projects/:id/documentation": { body: sampleWorkspaceReady },
      "POST /projects/:id/documentation/preview": { body: samplePreviewResponse },
      "POST /projects/:id/documentation/generate": {
        body: {
          export: completedExport,
          workspace: {
            ...sampleWorkspaceReady,
            stage_status: "complete",
            completion_check: { complete: true, blocking_reasons: [] },
            current_official_export: completedExport,
            export_history: [completedExport],
          },
        },
      },
    });

    renderApp("/projects/p1/documentation");

    expect(await screen.findByTestId("documentation-workspace")).toBeInTheDocument();
    expect(screen.getByTestId("documentation-stage-status")).toHaveTextContent("Stage: in_progress");
    expect(screen.getByTestId("inventory-row-research")).toHaveTextContent("User & Market Research");
    expect(screen.getByTestId("inventory-row-architecture")).toHaveTextContent("Product Architecture");
    expect(screen.getByTestId("validation-finding-PRELIMINARY_RESEARCH_MODE")).toBeInTheDocument();

    // Switch preview tab to 06-architecture.md
    await userEvent.click(screen.getByTestId("preview-tab-06-architecture.md"));
    expect(screen.getByTestId("preview-document-content")).toHaveTextContent("Approved Architecture v1.");

    // Generate official export
    await userEvent.type(screen.getByTestId("export-note-input"), "Phase 17 release candidate");
    await userEvent.click(screen.getByTestId("generate-official-export-btn"));

    expect(await screen.findByTestId("documentation-status-banner")).toHaveTextContent(
      "Official Documentation Bundle v1 generated",
    );
    expect(screen.getByTestId("documentation-stage-status")).toHaveTextContent("Stage: complete");
    expect(screen.getByTestId("download-format-zip")).toHaveAttribute(
      "href",
      "/api/projects/p1/documentation/exports/exp-1/download?format=zip",
    );
  });

  it("disables official export generation when blocking validation errors exist", async () => {
    const blockedWorkspace = {
      ...sampleWorkspaceReady,
      validation_summary: {
        ready_for_official_export: false,
        blocking_error_count: 1,
        warning_count: 0,
        info_count: 0,
        findings: [
          {
            code: "OPEN_DRAFT_EXISTS",
            severity: "blocking_error",
            section: "seo",
            title: "Open unapproved draft exists for SEO Specification (v2)",
            message: "SEO Specification has an unapproved draft v2 open.",
            remediation: "Approve SEO v2 in /projects/p1/seo.",
            workspace_path: "/projects/p1/seo",
          },
        ],
      },
    };

    mockApi({
      ...base,
      "GET /projects/:id/documentation": { body: blockedWorkspace },
      "POST /projects/:id/documentation/preview": {
        body: { ...samplePreviewResponse, official_approved_bundle: false },
      },
    });

    renderApp("/projects/p1/documentation");

    expect(await screen.findByTestId("validation-finding-OPEN_DRAFT_EXISTS")).toBeInTheDocument();
    expect(screen.getByTestId("generate-official-export-btn")).toBeDisabled();
    expect(screen.getByTestId("generate-preview-export-btn")).not.toBeDisabled();
  });
});
