import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { documentationApi } from "../features/documentation/api";
import { ApiError } from "../lib/api";
import type {
  DocumentationExportDetail,
  DocumentationPreviewResponse,
  DocumentationWorkspaceState,
  ExportIntegrity,
} from "../types/documentation";

export default function DocumentationPage() {
  const { projectId = "" } = useParams<{ projectId: string }>();
  const [workspace, setWorkspace] = useState<DocumentationWorkspaceState | null>(null);
  const [preview, setPreview] = useState<DocumentationPreviewResponse | null>(null);
  const [selectedExport, setSelectedExport] = useState<DocumentationExportDetail | null>(null);
  const [includeDraftsOrStale, setIncludeDraftsOrStale] = useState(false);
  const [activeDocTab, setActiveDocTab] = useState<string>("README.md");
  const [exportNote, setExportNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusBanner, setStatusBanner] = useState<string | null>(null);
  const [verifiedMap, setVerifiedMap] = useState<Record<string, ExportIntegrity>>({});

  const loadWorkspaceAndPreview = useCallback(
    async (draftToggle: boolean) => {
      if (!projectId) return;
      setLoading(true);
      setError(null);
      try {
        const [ws, prev] = await Promise.all([
          documentationApi.getWorkspace(projectId),
          documentationApi.preview(projectId, draftToggle),
        ]);
        setWorkspace(ws);
        setPreview(prev);
        const docKeys = Object.keys(prev.documents || {});
        if (docKeys.length > 0 && !docKeys.includes(activeDocTab) && activeDocTab !== "MANIFEST.json") {
          setActiveDocTab(docKeys[0]);
        }
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load Documentation & Export workspace.");
      } finally {
        setLoading(false);
      }
    },
    [projectId, activeDocTab],
  );

  useEffect(() => {
    void loadWorkspaceAndPreview(includeDraftsOrStale);
  }, [projectId]);

  const handleToggleDraftPreview = async (checked: boolean) => {
    setIncludeDraftsOrStale(checked);
    setBusyAction("preview");
    setError(null);
    try {
      const prev = await documentationApi.preview(projectId, checked);
      setPreview(prev);
      setSelectedExport(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to refresh preview.");
    } finally {
      setBusyAction(null);
    }
  };

  const handleGenerateExport = async (mode: "official" | "preview") => {
    if (!workspace) return;
    setBusyAction(`generate-${mode}`);
    setError(null);
    setStatusBanner(null);
    try {
      const res = await documentationApi.generate(projectId, {
        mode,
        include_drafts_or_stale: mode === "preview" ? includeDraftsOrStale : false,
        export_note: exportNote.trim() || null,
        expected_snapshot_fingerprint: workspace.snapshot_fingerprint,
      });
      setWorkspace(res.workspace);
      setSelectedExport(res.export);
      setExportNote("");
      setStatusBanner(
        mode === "official"
          ? `Official Documentation Bundle v${res.export.version} generated (SHA-256: ${res.export.bundle_sha256.slice(0, 16)}...). Stage 'documentation' is now complete.`
          : `Preview Documentation Bundle v${res.export.version} saved (Non-official preview; does not complete the documentation stage).`,
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Export generation failed.");
    } finally {
      setBusyAction(null);
    }
  };

  const handleInspectExport = async (exportId: string) => {
    setBusyAction(`inspect-${exportId}`);
    setError(null);
    try {
      const detail = await documentationApi.getExport(projectId, exportId);
      setSelectedExport(detail);
      const keys = Object.keys(detail.documents || {});
      if (keys.length > 0) setActiveDocTab(keys[0]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load export details.");
    } finally {
      setBusyAction(null);
    }
  };

  const handleVerifyExport = async (exportId: string) => {
    setBusyAction(`verify-${exportId}`);
    setError(null);
    try {
      const res = await documentationApi.verifyExport(projectId, exportId);
      setVerifiedMap((prev) => ({ ...prev, [exportId]: res.integrity }));
      setStatusBanner(
        res.integrity.verified
          ? `Export v${res.version} passed cryptographic SHA-256 verification (${res.integrity.matches_current_sources ? "current with latest project artifacts" : "stale against newer upstream edits"}).`
          : `Export v${res.version} FAILED SHA-256 integrity verification.`,
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Verification request failed.");
    } finally {
      setBusyAction(null);
    }
  };

  if (loading && !workspace) {
    return (
      <div className="p-6 text-sm text-slate-400" data-testid="documentation-loading">
        Loading Documentation &amp; Export workspace…
      </div>
    );
  }

  if (!workspace) {
    return (
      <div className="p-6">
        <div className="rounded border border-rose-500/40 bg-rose-950/30 p-4 text-sm text-rose-200">
          {error || "Documentation workspace unavailable."}
        </div>
      </div>
    );
  }

  const activeDocs = selectedExport ? selectedExport.documents : preview?.documents || {};
  const activeManifest = selectedExport ? selectedExport.manifest : preview?.manifest || {};
  const docFilenames = [...Object.keys(activeDocs), "MANIFEST.json"];
  const findings = workspace.validation_summary.findings || [];
  const blockingFindings = findings.filter((f) => f.severity === "blocking_error");
  const warningFindings = findings.filter((f) => f.severity === "warning");
  const infoFindings = findings.filter((f) => f.severity === "info");
  const activeExportForDownload = selectedExport || workspace.current_official_export || workspace.export_history[0] || null;

  return (
    <div className="space-y-6 p-6 text-slate-100" data-testid="documentation-workspace">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-white">Documentation &amp; Specification Export</h1>
            <span
              data-testid="documentation-stage-status"
              className={`rounded-full px-3 py-0.5 text-xs font-medium uppercase tracking-wider ${
                workspace.stage_status === "complete"
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                  : workspace.stage_status === "needs_review"
                    ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                    : "bg-slate-800 text-slate-300 border border-slate-700"
              }`}
            >
              Stage: {workspace.stage_status}
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-400">
            Phase 17 final lifecycle stage — Assemble, validate, preview, and export deterministic UTF-8 Markdown &amp; JSON
            product specification bundles derived strictly from persisted, hash-verified project artifacts.
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Brain Revision: <code className="text-slate-300">v{workspace.brain_version}</code> · Snapshot Fingerprint:{" "}
            <code className="text-slate-300">{workspace.snapshot_fingerprint.slice(0, 20)}…</code> · Scope note: Project
            specification exports are distinct from Phase 15 operator database backups (<code>scripts/db_ops.py</code>).
          </p>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          data-testid="documentation-error-banner"
          className="rounded-lg border border-rose-500/40 bg-rose-950/40 p-4 text-sm text-rose-200"
        >
          {error}
        </div>
      )}

      {statusBanner && (
        <div
          data-testid="documentation-status-banner"
          className="rounded-lg border border-emerald-500/40 bg-emerald-950/40 p-4 text-sm text-emerald-200"
        >
          {statusBanner}
        </div>
      )}

      {/* Stage Readiness & Official Export Gate Banner */}
      <div
        data-testid="documentation-readiness-panel"
        className={`rounded-lg border p-4 ${
          workspace.validation_summary.ready_for_official_export
            ? "border-emerald-500/40 bg-emerald-950/20"
            : "border-amber-500/40 bg-amber-950/20"
        }`}
      >
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-white">
              {workspace.validation_summary.ready_for_official_export
                ? "Ready for Official Documentation Export"
                : "Official Documentation Export Blocked — Remediation Required"}
            </h2>
            <p className="mt-1 text-xs text-slate-300">
              Official exports require all 14 source specifications (Research, Strategy, PRD, UX Personas/Journeys/IA/Wireframes/Review,
              Design System, Prototype, Architecture, SEO, Analytics, Performance) to be approved, current, hash-verified, and free of
              blocking validation errors. Previews and file downloads alone never mark the <code>documentation</code> stage complete.
            </p>
          </div>
          <div className="flex items-center gap-3 text-xs">
            <span className="rounded bg-rose-500/20 px-2.5 py-1 font-medium text-rose-300">
              Blocking Errors: {workspace.validation_summary.blocking_error_count}
            </span>
            <span className="rounded bg-amber-500/20 px-2.5 py-1 font-medium text-amber-300">
              Warnings: {workspace.validation_summary.warning_count}
            </span>
            <span className="rounded bg-sky-500/20 px-2.5 py-1 font-medium text-sky-300">
              Disclosures: {workspace.validation_summary.info_count}
            </span>
          </div>
        </div>

        {!workspace.completion_check.complete && workspace.completion_check.blocking_reasons.length > 0 && (
          <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-amber-200" data-testid="completion-blocking-reasons">
            {workspace.completion_check.blocking_reasons.map((reason, idx) => (
              <li key={idx}>{reason}</li>
            ))}
          </ul>
        )}
      </div>

      {/* Generate Export & Download Controls */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
            1. Generate &amp; Persist Documentation Bundle
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Generating an <strong>Official Export</strong> validates all 14 source artifacts, records an immutable{" "}
            <code>DocumentationExport</code> row and <code>ProjectBrain.documentation_spec</code> pointer, and marks the{" "}
            <code>documentation</code> stage <code>complete</code>.
          </p>
          <div className="mt-3 space-y-3">
            <div>
              <label htmlFor="export-note-input" className="block text-xs font-medium text-slate-300">
                Export Release / Audit Note (optional)
              </label>
              <input
                id="export-note-input"
                data-testid="export-note-input"
                type="text"
                value={exportNote}
                onChange={(e) => setExportNote(e.target.value)}
                placeholder="e.g., Phase 17 release candidate specification bundle"
                className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-white placeholder-slate-500"
              />
            </div>
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                data-testid="generate-official-export-btn"
                disabled={
                  !workspace.validation_summary.ready_for_official_export ||
                  workspace.unmet_dependencies.length > 0 ||
                  busyAction !== null
                }
                onClick={() => void handleGenerateExport("official")}
                className="rounded bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {busyAction === "generate-official"
                  ? "Generating Official Bundle…"
                  : "Generate Official Export & Complete Stage"}
              </button>
              <button
                type="button"
                data-testid="generate-preview-export-btn"
                disabled={busyAction !== null}
                onClick={() => void handleGenerateExport("preview")}
                className="rounded border border-slate-600 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700 disabled:opacity-40"
              >
                {busyAction === "generate-preview"
                  ? "Saving Preview Bundle…"
                  : "Save Preview Bundle (Non-Official)"}
              </button>
            </div>
          </div>
        </div>

        {/* Download Formats Panel */}
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
            2. Download Persisted Bundle Formats
          </h2>
          {activeExportForDownload ? (
            <div className="mt-2 space-y-3" data-testid="export-download-controls">
              <div className="flex items-center justify-between text-xs text-slate-300">
                <span>
                  Target Bundle:{" "}
                  <strong>
                    v{activeExportForDownload.version} ({activeExportForDownload.export_mode.toUpperCase()})
                  </strong>
                </span>
                <span className="font-mono text-slate-400">
                  ZIP SHA-256: {activeExportForDownload.bundle_sha256.slice(0, 16)}…
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                {workspace.supported_formats.map((fmt) => (
                  <a
                    key={fmt.format}
                    data-testid={`download-format-${fmt.format}`}
                    href={documentationApi.downloadUrl(projectId, activeExportForDownload.id, fmt.format)}
                    className="inline-flex items-center gap-1.5 rounded border border-indigo-500/40 bg-indigo-950/50 px-3 py-1.5 text-xs font-medium text-indigo-200 hover:bg-indigo-900/60"
                  >
                    Download {fmt.label}
                  </a>
                ))}
              </div>
              <p className="text-[11px] text-slate-400" data-testid="unsupported-formats-disclosure">
                {workspace.unsupported_formats_note}
              </p>
            </div>
          ) : (
            <p className="mt-2 text-xs text-slate-400">
              No persisted export bundle has been generated yet. Generate an Official or Preview bundle on the left to enable
              deterministic <code>.zip</code>, consolidated <code>.md</code>, and validated <code>.json</code> downloads.
            </p>
          )}
        </div>
      </div>

      {/* Required Artifact Provenance & Staleness Inventory */}
      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
          3. Source Artifact Provenance, Approval &amp; Staleness Inventory (14 Artifacts)
        </h2>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-xs" data-testid="artifact-inventory-table">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="py-2 pr-3">Artifact</th>
                <th className="py-2 px-3">Phase / Stage</th>
                <th className="py-2 px-3">Selected Version</th>
                <th className="py-2 px-3">Approval Status</th>
                <th className="py-2 px-3">Staleness</th>
                <th className="py-2 px-3">SHA-256 Provenance</th>
                <th className="py-2 px-3">Bundle Status</th>
                <th className="py-2 pl-3">Workspace</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {workspace.artifact_inventory.map((item) => (
                <tr key={item.artifact_key} data-testid={`inventory-row-${item.artifact_key}`}>
                  <td className="py-2 pr-3 font-medium text-white">{item.label}</td>
                  <td className="py-2 px-3 text-slate-400">
                    {item.phase} · <code>{item.stage}</code>
                  </td>
                  <td className="py-2 px-3 font-mono text-slate-200">
                    {item.selected_version ? `v${item.selected_version}` : "—"}
                    {item.open_draft_version && item.open_draft_version !== item.selected_version && (
                      <span className="ml-1.5 rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] text-amber-300">
                        open draft v{item.open_draft_version}
                      </span>
                    )}
                  </td>
                  <td className="py-2 px-3">
                    <span
                      className={`rounded px-2 py-0.5 text-[11px] font-medium ${
                        item.selected_status === "approved"
                          ? "bg-emerald-500/20 text-emerald-300"
                          : item.selected_status === "missing"
                            ? "bg-rose-500/20 text-rose-300"
                            : "bg-amber-500/20 text-amber-300"
                      }`}
                    >
                      {item.selected_status}
                    </span>
                  </td>
                  <td className="py-2 px-3">
                    {item.stale ? (
                      <span
                        className="rounded bg-rose-500/20 px-2 py-0.5 text-[11px] font-medium text-rose-300"
                        title={item.staleness_reasons.join("; ")}
                      >
                        STALE
                      </span>
                    ) : (
                      <span className="rounded bg-slate-800 px-2 py-0.5 text-[11px] text-slate-300">CURRENT</span>
                    )}
                  </td>
                  <td className="py-2 px-3 font-mono text-[11px] text-slate-300">
                    {item.content_hash ? (
                      <span>
                        {item.content_hash.slice(0, 12)}…{" "}
                        {item.hash_verified ? (
                          <span className="text-emerald-400" title="SHA-256 verified">
                            ✓
                          </span>
                        ) : (
                          <span className="text-rose-400" title="Hash mismatch">
                            ✗
                          </span>
                        )}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="py-2 px-3">
                    {item.included_in_export ? (
                      <span className="text-emerald-300">Included</span>
                    ) : (
                      <span className="text-rose-300" title={item.omission_reason || ""}>
                        Omitted
                      </span>
                    )}
                  </td>
                  <td className="py-2 pl-3">
                    <Link to={item.workspace_path} className="text-indigo-400 hover:underline">
                      Open →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Validation Findings & Remediation */}
      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4" data-testid="validation-findings-panel">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
          4. Pre-Export Validation Findings ({findings.length})
        </h2>
        {findings.length === 0 ? (
          <p className="mt-2 text-xs text-emerald-300">
            All provenance, completeness, traceability, and security checks passed with 0 findings.
          </p>
        ) : (
          <div className="mt-3 space-y-2">
            {[...blockingFindings, ...warningFindings, ...infoFindings].map((f, i) => (
              <div
                key={`${f.code}-${f.section}-${i}`}
                data-testid={`validation-finding-${f.code}`}
                className={`rounded border p-3 text-xs ${
                  f.severity === "blocking_error"
                    ? "border-rose-500/40 bg-rose-950/30 text-rose-200"
                    : f.severity === "warning"
                      ? "border-amber-500/40 bg-amber-950/30 text-amber-200"
                      : "border-sky-500/30 bg-sky-950/20 text-sky-200"
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-semibold">
                    [{f.severity.toUpperCase()}] {f.title} (<code>{f.code}</code>)
                  </span>
                  {f.workspace_path && (
                    <Link to={f.workspace_path} className="font-medium underline">
                      Remediate in {f.section} →
                    </Link>
                  )}
                </div>
                <p className="mt-1 opacity-90">{f.message}</p>
                <p className="mt-1 text-[11px] opacity-75">Remediation: {f.remediation}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Included & Omitted Bundle Sections */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-emerald-300">
            Included Bundle Documents ({workspace.included_sections.length + 1})
          </h3>
          <ul className="mt-2 space-y-1.5 text-xs text-slate-300" data-testid="included-sections-list">
            {workspace.included_sections.map((sec) => (
              <li key={sec.filename} className="flex items-center justify-between">
                <span>
                  <code>{sec.filename}</code> — {sec.title}
                </span>
                <span className="text-slate-500">[{sec.source_artifacts}]</span>
              </li>
            ))}
            <li className="flex items-center justify-between">
              <span>
                <code>MANIFEST.json</code> — Machine-Readable Provenance &amp; SHA-256 Digest Manifest
              </span>
              <span className="text-slate-500">[all]</span>
            </li>
          </ul>
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-amber-300">
            Omitted / Unavailable Sections ({workspace.omitted_sections.length})
          </h3>
          {workspace.omitted_sections.length === 0 ? (
            <p className="mt-2 text-xs text-slate-400">
              All 13 canonical Markdown documents and <code>MANIFEST.json</code> are included.
            </p>
          ) : (
            <ul className="mt-2 space-y-1.5 text-xs text-amber-200" data-testid="omitted-sections-list">
              {workspace.omitted_sections.map((om) => (
                <li key={om.filename}>
                  <code>{om.filename}</code> ({om.title}): {om.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Interactive Document & MANIFEST.json Preview */}
      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4" data-testid="documentation-preview-viewer">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-3">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
              5. Bundle Document &amp; Manifest Inspector{" "}
              {selectedExport
                ? `(Viewing Persisted Export v${selectedExport.version} — ${selectedExport.export_mode.toUpperCase()})`
                : includeDraftsOrStale
                  ? "(Live Preview — Includes Draft/Stale Artifacts [NON-OFFICIAL])"
                  : "(Live Preview — Official Approved Artifacts Only)"}
            </h2>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <label className="inline-flex cursor-pointer items-center gap-2 text-slate-300">
              <input
                type="checkbox"
                data-testid="toggle-include-drafts"
                checked={includeDraftsOrStale}
                onChange={(e) => void handleToggleDraftPreview(e.target.checked)}
              />
              <span>Include unapproved draft / stale artifacts in preview (Non-Official)</span>
            </label>
            {selectedExport && (
              <button
                type="button"
                onClick={() => setSelectedExport(null)}
                className="rounded border border-slate-700 px-2.5 py-1 text-slate-300 hover:bg-slate-800"
              >
                Return to Live Preview
              </button>
            )}
          </div>
        </div>

        {/* File Tabs */}
        <div className="mt-3 flex flex-wrap gap-1.5 border-b border-slate-800 pb-3">
          {docFilenames.map((fname) => (
            <button
              key={fname}
              type="button"
              data-testid={`preview-tab-${fname}`}
              onClick={() => setActiveDocTab(fname)}
              className={`rounded px-2.5 py-1 font-mono text-xs ${
                activeDocTab === fname
                  ? "bg-indigo-600 text-white"
                  : "bg-slate-800/80 text-slate-300 hover:bg-slate-800"
              }`}
            >
              {fname}
            </button>
          ))}
        </div>

        {/* Active File Content */}
        <div className="mt-3">
          {activeExportForDownload && (
            <div className="mb-2 flex justify-end">
              <a
                data-testid="download-single-file-link"
                href={documentationApi.fileDownloadUrl(projectId, activeExportForDownload.id, activeDocTab)}
                className="text-xs text-indigo-400 hover:underline"
              >
                Download {activeDocTab} from Export v{activeExportForDownload.version} →
              </a>
            </div>
          )}
          <pre
            data-testid="preview-document-content"
            className="max-h-[480px] overflow-auto rounded border border-slate-800 bg-slate-950 p-4 font-mono text-xs leading-relaxed text-slate-200"
          >
            {activeDocTab === "MANIFEST.json"
              ? JSON.stringify(activeManifest, null, 2)
              : activeDocs[activeDocTab] || "Select a document tab above to inspect its generated Markdown."}
          </pre>
        </div>
      </div>

      {/* Persisted Export History & SHA-256 Verification */}
      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4" data-testid="export-history-panel">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
          6. Persisted Export History &amp; Integrity Verification ({workspace.export_history.length})
        </h2>
        {workspace.export_history.length === 0 ? (
          <p className="mt-2 text-xs text-slate-400">No persisted documentation exports yet.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-xs" data-testid="export-history-table">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400">
                  <th className="py-2 pr-3">Version</th>
                  <th className="py-2 px-3">Mode</th>
                  <th className="py-2 px-3">Status</th>
                  <th className="py-2 px-3">Source Alignment</th>
                  <th className="py-2 px-3">Bundle SHA-256</th>
                  <th className="py-2 px-3">Note</th>
                  <th className="py-2 pl-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {workspace.export_history.map((exp) => {
                  const integ = verifiedMap[exp.id] || exp.integrity;
                  return (
                    <tr key={exp.id} data-testid={`export-history-row-v${exp.version}`}>
                      <td className="py-2 pr-3 font-mono font-semibold text-white">v{exp.version}</td>
                      <td className="py-2 px-3">
                        <span
                          className={`rounded px-2 py-0.5 text-[11px] font-medium uppercase ${
                            exp.export_mode === "official"
                              ? "bg-emerald-500/20 text-emerald-300"
                              : "bg-amber-500/20 text-amber-300"
                          }`}
                        >
                          {exp.export_mode}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-slate-300">{exp.status}</td>
                      <td className="py-2 px-3">
                        {integ.matches_current_sources ? (
                          <span className="rounded bg-emerald-500/20 px-2 py-0.5 text-[11px] text-emerald-300">
                            Current with sources
                          </span>
                        ) : (
                          <span className="rounded bg-amber-500/20 px-2 py-0.5 text-[11px] text-amber-300">
                            Stale — upstream changed
                          </span>
                        )}
                      </td>
                      <td className="py-2 px-3 font-mono text-[11px] text-slate-300">
                        {exp.bundle_sha256.slice(0, 16)}…{" "}
                        {integ.verified ? (
                          <span className="text-emerald-400">✓ verified</span>
                        ) : (
                          <span className="text-rose-400">✗ mismatch</span>
                        )}
                      </td>
                      <td className="py-2 px-3 text-slate-400">{exp.export_note || "—"}</td>
                      <td className="py-2 pl-3">
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            data-testid={`inspect-export-v${exp.version}`}
                            onClick={() => void handleInspectExport(exp.id)}
                            className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-[11px] text-slate-200 hover:bg-slate-700"
                          >
                            Inspect
                          </button>
                          <button
                            type="button"
                            data-testid={`verify-export-v${exp.version}`}
                            onClick={() => void handleVerifyExport(exp.id)}
                            className="rounded border border-emerald-500/40 bg-emerald-950/40 px-2 py-1 text-[11px] text-emerald-200 hover:bg-emerald-900/50"
                          >
                            Verify SHA-256
                          </button>
                          <a
                            href={documentationApi.downloadUrl(projectId, exp.id, "zip")}
                            className="rounded border border-indigo-500/40 bg-indigo-950/40 px-2 py-1 text-[11px] text-indigo-200 hover:bg-indigo-900/50"
                          >
                            .zip
                          </a>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
