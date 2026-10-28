import { useState } from "react";
import { ErrorState, LoadingState } from "../components/feedback/States";
import { Alert } from "../components/ui/Alert";
import { Badge } from "../components/ui/Badge";
import { LifecycleMap } from "../features/lifecycle/LifecycleMap";
import { DiscoveryCallout } from "../features/discovery/DiscoveryCallout";
import { IdeaReview } from "../features/overview/IdeaReview";
import { IntakePanel } from "../features/overview/IntakePanel";
import { CurrentWorkPanel, NextActionPanel, ProgressPanel, RecentChangesPanel, SystemStatePanel } from "../features/overview/OverviewPanels";
import { projectsApi } from "../features/projects/api";
import { useAsync } from "../lib/useAsync";
import type { StageStatus } from "../types/lifecycle";
import { useProject } from "./ProjectLayout";

export default function ProjectOverviewPage() {
  const { project } = useProject();
  const overview = useAsync(() => projectsApi.overview(project.id), [project.id]);
  const brain = useAsync(() => projectsApi.brain(project.id), [project.id]);
  const [reanalyze, setReanalyze] = useState(false);
  const [saved, setSaved] = useState<number | null>(null);

  const reloadAll = () => { overview.reload(); brain.reload(); };
  if ((overview.loading && !overview.data) || (brain.loading && !brain.data)) return <LoadingState label="Loading overview…" />;
  const err = overview.error ?? brain.error;
  if (err || !overview.data || !brain.data) return <ErrorState message={err?.message ?? "We couldn't load this project."} onRetry={reloadAll} />;

  const o = overview.data;
  const hasIdea = brain.data.brain.idea.raw.trim() !== "";
  const onSaved = (v: number) => { setSaved(v); setReanalyze(false); reloadAll(); };
  const setStage = async (stage: string, status: StageStatus) => { await projectsApi.setStage(project.id, stage, status); overview.reload(); };

  return (
    <div className="space-y-4">
      <header>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="min-w-0 text-xl font-semibold [overflow-wrap:anywhere]">{o.project.name}</h1>
          {o.project.status === "archived" && <Badge>Archived</Badge>}
        </div>
        {o.project.description && <p className="mt-0.5 text-slate-600 [overflow-wrap:anywhere]">{o.project.description}</p>}
      </header>

      {saved !== null && <Alert tone="success">Analysis saved as Project Brain v{saved}.</Alert>}

      <div className="grid gap-4 md:grid-cols-3">
        <div className="md:col-span-2"><ProgressPanel o={o} /></div>
        <NextActionPanel o={o} />
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {!hasIdea || reanalyze
            ? <IntakePanel projectId={project.id} initial={reanalyze ? brain.data.brain.idea.raw : ""} replacing={reanalyze} onSaved={onSaved} onCancel={reanalyze ? () => setReanalyze(false) : undefined} />
            : <IdeaReview data={brain.data} onReanalyze={() => setReanalyze(true)} />}
          {hasIdea && !reanalyze && <DiscoveryCallout projectId={project.id} key={saved ?? 0} />}
          <LifecycleMap stages={o.stages} onChangeStatus={setStage} />
        </div>
        <div className="space-y-4">
          <CurrentWorkPanel o={o} />
          <RecentChangesPanel o={o} />
          <SystemStatePanel o={o} />
        </div>
      </div>
    </div>
  );
}
