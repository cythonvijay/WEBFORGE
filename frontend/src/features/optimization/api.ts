import { api } from "../../lib/api";
import type {
  OptimizationArea,
  OptimizationAreaState,
  OptimizationDocument,
  OptimizationEditResponse,
  OptimizationOverviewState,
} from "../../types/optimization";

const base = (id: string) => `/projects/${id}/optimization`;
const areaBase = (id: string, area: OptimizationArea) => `${base(id)}/${area}`;
const ver = (id: string, area: OptimizationArea, v: number) => `${areaBase(id, area)}/versions/${v}`;

export const optimizationApi = {
  overview: (id: string) => api.get<OptimizationOverviewState>(base(id)),
  verification: (id: string) => api.get<OptimizationOverviewState["verification"]>(`${base(id)}/verification`),
  verifyHtml: (id: string, route_path: string, html_content: string) =>
    api.post<{
      route_path: string;
      status: string;
      title: string | null;
      meta_description: string | null;
      canonical: string | null;
      robots: string | null;
      h1_count: number;
      h1_texts: string[];
      findings: { code: string; severity: string; message: string }[];
    }>(`${base(id)}/verify-html`, { route_path, html_content }),

  getArea: (id: string, area: OptimizationArea) =>
    api.get<OptimizationAreaState>(areaBase(id, area)),
  getVersion: (id: string, area: OptimizationArea, v: number) =>
    api.get<OptimizationDocument>(ver(id, area, v)),
  generate: (id: string, area: OptimizationArea, supersede: boolean) =>
    api.post<OptimizationAreaState>(`${areaBase(id, area)}/generate`, { supersede }),
  initialize: (id: string, area: OptimizationArea, supersede: boolean) =>
    api.post<OptimizationAreaState>(`${areaBase(id, area)}/initialize`, { supersede }),
  putContent: (id: string, area: OptimizationArea, v: number, base_hash: string, content: unknown) =>
    api.put<OptimizationEditResponse>(ver(id, area, v), { base_hash, content }),
  patchSection: (id: string, area: OptimizationArea, v: number, base_hash: string, section: string, value: unknown) =>
    api.patch<OptimizationEditResponse>(`${ver(id, area, v)}/section`, { base_hash, section, value }),
  submit: (id: string, area: OptimizationArea, v: number, base_hash: string) =>
    api.post<OptimizationAreaState>(`${ver(id, area, v)}/submit`, { base_hash }),
  approve: (id: string, area: OptimizationArea, v: number, content_hash: string, acknowledge_unverified: boolean, note: string) =>
    api.post<OptimizationAreaState>(`${ver(id, area, v)}/approve`, {
      content_hash,
      acknowledge_unverified,
      note: note || null,
    }),
};
