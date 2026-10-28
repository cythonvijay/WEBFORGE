import { api } from "../../lib/api";
import type { Citation, EditResponse, Evidence, Report, ResearchState, Topic } from "../../types/research";

const base = (id: string) => `/projects/${id}/research`;
const rep = (id: string, v: number) => `${base(id)}/reports/${v}`;

export interface FindingBody { topic: Topic; statement: string; detail: string | null; evidence: Evidence; citations: Citation[]; follow_up: boolean }
export interface SourceBody { title: string; url: string; publisher: string | null; accessed_on: string | null; examined: boolean; note: string | null }

export const researchApi = {
  get: (id: string) => api.get<ResearchState>(base(id)),
  report: (id: string, v: number) => api.get<Report>(rep(id, v)),
  generate: (id: string, supersede: boolean) => api.post<ResearchState>(`${base(id)}/generate`, { supersede }),
  addFinding: (id: string, v: number, h: string, b: FindingBody) => api.post<EditResponse>(`${rep(id, v)}/findings`, { base_hash: h, ...b }),
  patchFinding: (id: string, v: number, h: string, fid: string, b: Partial<FindingBody>) => api.patch<EditResponse>(`${rep(id, v)}/findings/${fid}`, { base_hash: h, ...b }),
  deleteFinding: (id: string, v: number, h: string, fid: string) => api.delete<EditResponse>(`${rep(id, v)}/findings/${fid}?base_hash=${h}`),
  followUp: (id: string, v: number, h: string, ids: string[], on: boolean) => api.post<EditResponse>(`${rep(id, v)}/follow-up`, { base_hash: h, finding_ids: ids, follow_up: on }),
  addSource: (id: string, v: number, h: string, b: SourceBody) => api.post<EditResponse>(`${rep(id, v)}/sources`, { base_hash: h, ...b }),
  patchSource: (id: string, v: number, h: string, sid: string, b: Partial<SourceBody>) => api.patch<EditResponse>(`${rep(id, v)}/sources/${sid}`, { base_hash: h, ...b }),
  deleteSource: (id: string, v: number, h: string, sid: string) => api.delete<EditResponse>(`${rep(id, v)}/sources/${sid}?base_hash=${h}`),
  submit: (id: string, v: number, h: string) => api.post<ResearchState>(`${rep(id, v)}/submit`, { base_hash: h }),
  approve: (id: string, v: number, h: string, ack: boolean, note: string) => api.post<ResearchState>(`${rep(id, v)}/approve`, { content_hash: h, acknowledge_unverified: ack, note: note || null }),
};
