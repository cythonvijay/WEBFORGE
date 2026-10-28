import { api } from "../../lib/api";
import type {
  DesignArtifactState,
  DesignArtifactType,
  DesignDocument,
  DesignEditResponse,
  DesignSystemContent,
  PrototypeContent,
} from "../../types/design";

const base = (id: string, a: DesignArtifactType) => `/projects/${id}/design/${a}`;
const ver = (id: string, a: DesignArtifactType, v: number) => `${base(id, a)}/versions/${v}`;

export const designApi = {
  get: <C = unknown>(id: string, a: DesignArtifactType) => api.get<DesignArtifactState<C>>(base(id, a)),
  version: <C = unknown>(id: string, a: DesignArtifactType, v: number) => api.get<DesignDocument<C>>(ver(id, a, v)),
  generate: <C = unknown>(id: string, a: DesignArtifactType, supersede: boolean) => api.post<DesignArtifactState<C>>(`${base(id, a)}/generate`, { supersede }),
  submit: <C = unknown>(id: string, a: DesignArtifactType, v: number, h: string) => api.post<DesignArtifactState<C>>(`${ver(id, a, v)}/submit`, { base_hash: h }),
  approve: <C = unknown>(id: string, a: DesignArtifactType, v: number, h: string, ack: boolean, note: string) =>
    api.post<DesignArtifactState<C>>(`${ver(id, a, v)}/approve`, { content_hash: h, acknowledge_unverified: ack, note: note || null }),

  // Design System
  patchFoundations: (id: string, v: number, h: string, b: Record<string, unknown>) =>
    api.patch<DesignEditResponse<DesignSystemContent>>(`${ver(id, "design_system", v)}/foundations`, { base_hash: h, ...b }),
  patchComponent: (id: string, v: number, h: string, cmpId: string, b: Record<string, unknown>) =>
    api.patch<DesignEditResponse<DesignSystemContent>>(`${ver(id, "design_system", v)}/components/${cmpId}`, { base_hash: h, ...b }),
  patchDecision: (id: string, v: number, h: string, decId: string, b: Record<string, unknown>) =>
    api.patch<DesignEditResponse<DesignSystemContent>>(`${ver(id, "design_system", v)}/decisions/${decId}`, { base_hash: h, ...b }),

  // Prototype
  patchScreen: (id: string, v: number, h: string, scrId: string, b: Record<string, unknown>) =>
    api.patch<DesignEditResponse<PrototypeContent>>(`${ver(id, "prototype", v)}/screens/${scrId}`, { base_hash: h, ...b }),
  patchFlow: (id: string, v: number, h: string, flowId: string, b: Record<string, unknown>) =>
    api.patch<DesignEditResponse<PrototypeContent>>(`${ver(id, "prototype", v)}/flows/${flowId}`, { base_hash: h, ...b }),
};
