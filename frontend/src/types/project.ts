export type ProjectStatus = "active" | "archived";

export interface Project {
  id: string;
  name: string;
  description: string;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
}

export interface Idea {
  raw: string;
  product_name: string;
  product_type: string;
  problem: string;
  features: string[];
  assumptions: string[];
  open_questions: string[];
}

/** Only sections the UI reads are typed; the backend schema has more. */
export interface ProjectBrain {
  idea: Idea;
  target_users: unknown[];
  goals: unknown[];
}

export interface BrainResponse {
  version: number;
  brain: ProjectBrain;
}

export interface IntakeResult {
  product_name: string;
  product_type: string;
  problem: string;
  target_users: string[];
  goals: string[];
  features: string[];
  assumptions: string[];
  questions: string[];
}

export interface IntakeResponse {
  version: number;
  result: IntakeResult;
}
