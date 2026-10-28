import { api } from "../../lib/api";
import type { MvpBoundary, NfrCategory, PrdDocument, PrdEditResponse, PrdState, Priority, ReqStatus } from "../../types/prd";

const base = (id: string) => `/projects/${id}/prd`;
const ver = (id: string, v: number) => `${base(id)}/versions/${v}`;

export interface FunctionalReqBody {
  title: string;
  description: string;
  priority: Priority;
  mvp_boundary: MvpBoundary;
  status: ReqStatus;
  user_story_ids: string[];
  source_refs: string[];
  acceptance_criteria: string[];
  edge_cases: string[];
  dependencies: string[];
}

export interface NonFunctionalReqBody {
  category: NfrCategory;
  title: string;
  description: string;
  priority: Priority;
  mvp_boundary: MvpBoundary;
  status: ReqStatus;
  source_refs: string[];
  acceptance_criteria: string[];
}

export const prdApi = {
  get: (id: string) => api.get<PrdState>(base(id)),
  version: (id: string, v: number) => api.get<PrdDocument>(ver(id, v)),
  generate: (id: string, supersede: boolean) => api.post<PrdState>(`${base(id)}/generate`, { supersede }),
  addFunctionalReq: (id: string, v: number, h: string, b: FunctionalReqBody) => api.post<PrdEditResponse>(`${ver(id, v)}/functional-requirements`, { base_hash: h, ...b }),
  patchFunctionalReq: (id: string, v: number, h: string, reqId: string, b: Partial<FunctionalReqBody>) => api.patch<PrdEditResponse>(`${ver(id, v)}/functional-requirements/${reqId}`, { base_hash: h, ...b }),
  deleteFunctionalReq: (id: string, v: number, h: string, reqId: string) => api.delete<PrdEditResponse>(`${ver(id, v)}/functional-requirements/${reqId}?base_hash=${h}`),
  addNonFunctionalReq: (id: string, v: number, h: string, b: NonFunctionalReqBody) => api.post<PrdEditResponse>(`${ver(id, v)}/non-functional-requirements`, { base_hash: h, ...b }),
  setRequirementStatus: (id: string, v: number, h: string, ids: string[], status: ReqStatus) => api.post<PrdEditResponse>(`${ver(id, v)}/requirements/status`, { base_hash: h, requirement_ids: ids, status }),
  submit: (id: string, v: number, h: string) => api.post<PrdState>(`${ver(id, v)}/submit`, { base_hash: h }),
  approve: (id: string, v: number, h: string, ack: boolean, note: string) => api.post<PrdState>(`${ver(id, v)}/approve`, { content_hash: h, acknowledge_unverified: ack, note: note || null }),
};
