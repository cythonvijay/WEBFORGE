import { api } from "../../lib/api";
import type {
  IaContent,
  JourneysContent,
  PersonasContent,
  UxArtifactState,
  UxArtifactType,
  UxDocument,
  UxEditResponse,
  UxReviewContent,
  WireframesContent,
} from "../../types/ux";

const base = (id: string, a: UxArtifactType) => `/projects/${id}/ux/${a}`;
const ver = (id: string, a: UxArtifactType, v: number) => `${base(id, a)}/versions/${v}`;

export const uxApi = {
  get: <C = unknown>(id: string, a: UxArtifactType) => api.get<UxArtifactState<C>>(base(id, a)),
  version: <C = unknown>(id: string, a: UxArtifactType, v: number) => api.get<UxDocument<C>>(ver(id, a, v)),
  generate: <C = unknown>(id: string, a: UxArtifactType, supersede: boolean) => api.post<UxArtifactState<C>>(`${base(id, a)}/generate`, { supersede }),
  submit: <C = unknown>(id: string, a: UxArtifactType, v: number, h: string) => api.post<UxArtifactState<C>>(`${ver(id, a, v)}/submit`, { base_hash: h }),
  approve: <C = unknown>(id: string, a: UxArtifactType, v: number, h: string, ack: boolean, note: string) =>
    api.post<UxArtifactState<C>>(`${ver(id, a, v)}/approve`, { content_hash: h, acknowledge_unverified: ack, note: note || null }),

  // Personas
  manualPersonas: (id: string, b: Record<string, unknown>) => api.post<UxArtifactState<PersonasContent>>(`/projects/${id}/ux/personas/manual`, b),
  addPersona: (id: string, v: number, h: string, b: Record<string, unknown>) =>
    api.post<UxEditResponse<PersonasContent>>(`${ver(id, "personas", v)}/items`, { base_hash: h, ...b }),
  patchPersona: (id: string, v: number, h: string, itemId: string, b: Record<string, unknown>) =>
    api.patch<UxEditResponse<PersonasContent>>(`${ver(id, "personas", v)}/items/${itemId}`, { base_hash: h, ...b }),
  deletePersona: (id: string, v: number, h: string, itemId: string) =>
    api.delete<UxEditResponse<PersonasContent>>(`${ver(id, "personas", v)}/items/${itemId}?base_hash=${h}`),

  // Journeys
  addJourney: (id: string, v: number, h: string, b: Record<string, unknown>) =>
    api.post<UxEditResponse<JourneysContent>>(`${ver(id, "journeys", v)}/items`, { base_hash: h, ...b }),
  patchJourney: (id: string, v: number, h: string, itemId: string, b: Record<string, unknown>) =>
    api.patch<UxEditResponse<JourneysContent>>(`${ver(id, "journeys", v)}/items/${itemId}`, { base_hash: h, ...b }),
  deleteJourney: (id: string, v: number, h: string, itemId: string) =>
    api.delete<UxEditResponse<JourneysContent>>(`${ver(id, "journeys", v)}/items/${itemId}?base_hash=${h}`),

  // IA
  addIaNode: (id: string, v: number, h: string, b: Record<string, unknown>) =>
    api.post<UxEditResponse<IaContent>>(`${ver(id, "ia", v)}/nodes`, { base_hash: h, ...b }),
  patchIaNode: (id: string, v: number, h: string, nodeId: string, b: Record<string, unknown>) =>
    api.patch<UxEditResponse<IaContent>>(`${ver(id, "ia", v)}/nodes/${nodeId}`, { base_hash: h, ...b }),
  deleteIaNode: (id: string, v: number, h: string, nodeId: string) =>
    api.delete<UxEditResponse<IaContent>>(`${ver(id, "ia", v)}/nodes/${nodeId}?base_hash=${h}`),

  // Wireframes
  addWireframe: (id: string, v: number, h: string, b: Record<string, unknown>) =>
    api.post<UxEditResponse<WireframesContent>>(`${ver(id, "wireframes", v)}/items`, { base_hash: h, ...b }),
  patchWireframe: (id: string, v: number, h: string, itemId: string, b: Record<string, unknown>) =>
    api.patch<UxEditResponse<WireframesContent>>(`${ver(id, "wireframes", v)}/items/${itemId}`, { base_hash: h, ...b }),
  deleteWireframe: (id: string, v: number, h: string, itemId: string) =>
    api.delete<UxEditResponse<WireframesContent>>(`${ver(id, "wireframes", v)}/items/${itemId}?base_hash=${h}`),

  // UX Review
  addFinding: (id: string, v: number, h: string, b: Record<string, unknown>) =>
    api.post<UxEditResponse<UxReviewContent>>(`${ver(id, "ux_review", v)}/findings`, { base_hash: h, ...b }),
  patchFinding: (id: string, v: number, h: string, findingId: string, b: Record<string, unknown>) =>
    api.patch<UxEditResponse<UxReviewContent>>(`${ver(id, "ux_review", v)}/findings/${findingId}`, { base_hash: h, ...b }),
  deleteFinding: (id: string, v: number, h: string, findingId: string) =>
    api.delete<UxEditResponse<UxReviewContent>>(`${ver(id, "ux_review", v)}/findings/${findingId}?base_hash=${h}`),
};
