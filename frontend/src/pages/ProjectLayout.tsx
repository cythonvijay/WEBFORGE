import { Outlet, useOutletContext, useParams } from "react-router-dom";
import { ErrorState, LoadingState } from "../components/feedback/States";
import { ApiError } from "../lib/api";
import { projectsApi } from "../features/projects/api";
import { useAsync } from "../lib/useAsync";
import type { Project } from "../types/project";

export interface ProjectContext { project: Project; reloadProject: () => void }
export const useProject = () => useOutletContext<ProjectContext>();

export default function ProjectLayout() {
  const { projectId = "" } = useParams();
  const q = useAsync(() => projectsApi.get(projectId), [projectId]);
  if (q.loading && !q.data) return <LoadingState label="Loading project…" />;
  if (q.error || !q.data) {
    const missing = q.error instanceof ApiError && q.error.kind === "not_found";
    return <ErrorState title={missing ? "Project not found" : "Something went wrong."}
      message={missing ? "This project doesn't exist or you don't have access to it." : q.error?.message ?? "We couldn't load this project."}
      onRetry={missing ? undefined : q.reload} backTo={{ to: "/projects", label: "Back to projects" }} />;
  }
  return <Outlet context={{ project: q.data, reloadProject: q.reload } satisfies ProjectContext} />;
}
