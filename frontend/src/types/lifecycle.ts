import type { Project } from "./project";

export type StageStatus = "not_started" | "in_progress" | "needs_review" | "complete" | "blocked";

export interface StageInfo {
  stage: string;
  status: StageStatus;
  depends_on: string[];
  unmet_dependencies: string[];
}

export interface RecentChange {
  version: number;
  change_type: string;
  created_at: string;
}

export interface Overview {
  project: Project;
  stages: StageInfo[];
  progress: number;
  completed: string[];
  in_progress: string[];
  needs_review: string[];
  blocked: string[];
  next_action: string | null;
  recent_changes: RecentChange[];
}
