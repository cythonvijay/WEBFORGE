import { api } from "../../lib/api";
import type { RecArea, RecStatus, StrategyDocument, StrategyEditResponse, StrategyState } from "../../types/strategy";

const base = (id: string) => `/projects/${id}/strategy`;
const ver = (id: string, v: number) => `${base(id)}/versions/${v}`;

export interface OverviewBody {
  product_vision?: string;
  value_proposition?: string;
  differentiation?: string;
  business_model?: string;
  constraints?: string[];
}

export interface RecommendationBody {
  area: RecArea;
  title: string;
  recommendation: string;
  rationale: string;
  status: RecStatus;
  supporting_refs: string[];
  needs_evidence: boolean;
}

export const strategyApi = {
  get: (id: string) => api.get<StrategyState>(base(id)),
  version: (id: string, v: number) => api.get<StrategyDocument>(ver(id, v)),
  generate: (id: string, supersede: boolean) => api.post<StrategyState>(`${base(id)}/generate`, { supersede }),
  patchOverview: (id: string, v: number, h: string, b: OverviewBody) => api.patch<StrategyEditResponse>(`${ver(id, v)}/overview`, { base_hash: h, ...b }),
  addRecommendation: (id: string, v: number, h: string, b: RecommendationBody) => api.post<StrategyEditResponse>(`${ver(id, v)}/recommendations`, { base_hash: h, ...b }),
  patchRecommendation: (id: string, v: number, h: string, rid: string, b: Partial<RecommendationBody>) => api.patch<StrategyEditResponse>(`${ver(id, v)}/recommendations/${rid}`, { base_hash: h, ...b }),
  deleteRecommendation: (id: string, v: number, h: string, rid: string) => api.delete<StrategyEditResponse>(`${ver(id, v)}/recommendations/${rid}?base_hash=${h}`),
  submit: (id: string, v: number, h: string) => api.post<StrategyState>(`${ver(id, v)}/submit`, { base_hash: h }),
  approve: (id: string, v: number, h: string, ack: boolean, note: string) => api.post<StrategyState>(`${ver(id, v)}/approve`, { content_hash: h, acknowledge_unverified: ack, note: note || null }),
};
