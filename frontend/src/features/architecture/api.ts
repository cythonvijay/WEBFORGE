import { api } from "../../lib/api";
import type {
  ArchitectureDocument,
  ArchitectureEditResponse,
  ArchitectureState,
} from "../../types/architecture";

const base = (id: string) => `/projects/${id}/architecture`;
const ver = (id: string, v: number) => `${base(id)}/versions/${v}`;

export const architectureApi = {
  get: (id: string) => api.get<ArchitectureState>(base(id)),
  version: (id: string, v: number) => api.get<ArchitectureDocument>(ver(id, v)),
  generate: (id: string, supersede: boolean) =>
    api.post<ArchitectureState>(`${base(id)}/generate`, { supersede }),
  submit: (id: string, v: number, h: string) =>
    api.post<ArchitectureState>(`${ver(id, v)}/submit`, { base_hash: h }),
  approve: (id: string, v: number, h: string, ack: boolean, note: string) =>
    api.post<ArchitectureState>(`${ver(id, v)}/approve`, {
      content_hash: h,
      acknowledge_unverified: ack,
      note: note || null,
    }),

  patchOverview: (id: string, v: number, h: string, b: Record<string, unknown>) =>
    api.patch<ArchitectureEditResponse>(`${ver(id, v)}/overview`, { base_hash: h, ...b }),
  addComponent: (id: string, v: number, h: string, b: Record<string, unknown>) =>
    api.post<ArchitectureEditResponse>(`${ver(id, v)}/components`, { base_hash: h, ...b }),
  patchComponent: (id: string, v: number, h: string, compId: string, b: Record<string, unknown>) =>
    api.patch<ArchitectureEditResponse>(`${ver(id, v)}/components/${compId}`, { base_hash: h, ...b }),
  deleteComponent: (id: string, v: number, h: string, compId: string) =>
    api.delete<ArchitectureEditResponse>(`${ver(id, v)}/components/${compId}?base_hash=${encodeURIComponent(h)}`),

  patchApplication: (id: string, v: number, h: string, b: Record<string, unknown>) =>
    api.patch<ArchitectureEditResponse>(`${ver(id, v)}/application`, { base_hash: h, ...b }),

  addEntity: (id: string, v: number, h: string, b: Record<string, unknown>) =>
    api.post<ArchitectureEditResponse>(`${ver(id, v)}/entities`, { base_hash: h, ...b }),
  patchEntity: (id: string, v: number, h: string, entId: string, b: Record<string, unknown>) =>
    api.patch<ArchitectureEditResponse>(`${ver(id, v)}/entities/${entId}`, { base_hash: h, ...b }),

  addEndpoint: (id: string, v: number, h: string, b: Record<string, unknown>) =>
    api.post<ArchitectureEditResponse>(`${ver(id, v)}/endpoints`, { base_hash: h, ...b }),
  patchEndpoint: (id: string, v: number, h: string, apiId: string, b: Record<string, unknown>) =>
    api.patch<ArchitectureEditResponse>(`${ver(id, v)}/endpoints/${apiId}`, { base_hash: h, ...b }),

  patchDeployment: (id: string, v: number, h: string, b: Record<string, unknown>) =>
    api.patch<ArchitectureEditResponse>(`${ver(id, v)}/deployment`, { base_hash: h, ...b }),

  addDecision: (id: string, v: number, h: string, b: Record<string, unknown>) =>
    api.post<ArchitectureEditResponse>(`${ver(id, v)}/decisions`, { base_hash: h, ...b }),
  patchDecision: (id: string, v: number, h: string, adrId: string, b: Record<string, unknown>) =>
    api.patch<ArchitectureEditResponse>(`${ver(id, v)}/decisions/${adrId}`, { base_hash: h, ...b }),

  addDiagram: (id: string, v: number, h: string, b: Record<string, unknown>) =>
    api.post<ArchitectureEditResponse>(`${ver(id, v)}/diagrams`, { base_hash: h, ...b }),
  patchDiagram: (id: string, v: number, h: string, diagId: string, b: Record<string, unknown>) =>
    api.patch<ArchitectureEditResponse>(`${ver(id, v)}/diagrams/${diagId}`, { base_hash: h, ...b }),
};
