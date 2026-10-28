import { api } from "../../lib/api";
import type { Overview, StageStatus } from "../../types/lifecycle";
import type { BrainResponse, IntakeResponse, Project, ProjectStatus } from "../../types/project";

export const projectsApi = {
  list: () => api.get<Project[]>("/projects"),
  get: (id: string) => api.get<Project>(`/projects/${id}`),
  create: (b: { name: string; description: string }) => api.post<Project>("/projects", b),
  update: (id: string, b: Partial<{ name: string; description: string; status: ProjectStatus }>) => api.patch<Project>(`/projects/${id}`, b),
  remove: (id: string) => api.delete(`/projects/${id}`),
  overview: (id: string) => api.get<Overview>(`/projects/${id}/overview`),
  brain: (id: string) => api.get<BrainResponse>(`/projects/${id}/brain`),
  intake: (id: string, idea: string) => api.post<IntakeResponse>(`/projects/${id}/intake`, { idea }),
  setStage: (id: string, stage: string, status: StageStatus) => api.put<{ stage: string; status: StageStatus }>(`/projects/${id}/stages/${stage}`, { status }),
};
