import { api } from "../../lib/api";
import type { DiscoveryState } from "../../types/discovery";

const base = (id: string) => `/projects/${id}/discovery`;

export const discoveryApi = {
  get: (id: string) => api.get<DiscoveryState>(base(id)),
  start: (id: string) => api.post<DiscoveryState>(base(id)),
  answer: (id: string, answers: { question_id: string; value: unknown }[]) => api.post<DiscoveryState>(`${base(id)}/answers`, { answers }),
  skip: (id: string, qid: string) => api.post<DiscoveryState>(`${base(id)}/questions/${qid}/skip`),
  defer: (id: string, qid: string) => api.post<DiscoveryState>(`${base(id)}/questions/${qid}/defer`),
  nextRound: (id: string) => api.post<DiscoveryState>(`${base(id)}/next-round`),
  review: (id: string) => api.post<DiscoveryState>(`${base(id)}/review`),
  complete: (id: string, acceptAssumptions: boolean) => api.post<DiscoveryState>(`${base(id)}/complete`, { accept_assumptions: acceptAssumptions }),
};
