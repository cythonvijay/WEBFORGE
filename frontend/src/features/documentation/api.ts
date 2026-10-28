import { api } from "../../lib/api";
import type {
  DocumentationExportDetail,
  DocumentationExportSummary,
  DocumentationPreviewResponse,
  DocumentationWorkspaceState,
  ExportFormat,
  ExportIntegrity,
  ExportMode,
  GenerateExportResponse,
} from "../../types/documentation";

const base = (projectId: string) => `/projects/${projectId}/documentation`;

export const documentationApi = {
  getWorkspace: (projectId: string) =>
    api.get<DocumentationWorkspaceState>(base(projectId)),

  preview: (projectId: string, include_drafts_or_stale: boolean) =>
    api.post<DocumentationPreviewResponse>(`${base(projectId)}/preview`, {
      include_drafts_or_stale,
    }),

  generate: (
    projectId: string,
    payload: {
      mode: ExportMode;
      include_drafts_or_stale?: boolean;
      export_note?: string | null;
      expected_snapshot_fingerprint?: string | null;
    },
  ) =>
    api.post<GenerateExportResponse>(`${base(projectId)}/generate`, {
      mode: payload.mode,
      include_drafts_or_stale: Boolean(payload.include_drafts_or_stale),
      export_note: payload.export_note || null,
      expected_snapshot_fingerprint: payload.expected_snapshot_fingerprint || null,
    }),

  listExports: (projectId: string) =>
    api.get<{
      project_id: string;
      current_snapshot_fingerprint: string;
      exports: DocumentationExportSummary[];
    }>(`${base(projectId)}/exports`),

  getExport: (projectId: string, exportId: string) =>
    api.get<DocumentationExportDetail>(`${base(projectId)}/exports/${exportId}`),

  verifyExport: (projectId: string, exportId: string) =>
    api.post<{
      export_id: string;
      version: number;
      export_mode: ExportMode;
      status: string;
      integrity: ExportIntegrity;
    }>(`${base(projectId)}/exports/${exportId}/verify`, {}),

  downloadUrl: (projectId: string, exportId: string, format: ExportFormat = "zip") =>
    `/api${base(projectId)}/exports/${exportId}/download?format=${encodeURIComponent(format)}`,

  fileDownloadUrl: (projectId: string, exportId: string, filename: string) =>
    `/api${base(projectId)}/exports/${exportId}/files/${encodeURIComponent(filename)}`,
};
