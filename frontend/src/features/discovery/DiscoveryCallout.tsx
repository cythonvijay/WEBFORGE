import { Link } from "react-router-dom";
import { useAsync } from "../../lib/useAsync";
import { discoveryApi } from "./api";

const COPY: Record<string, { text: (o: number) => string; cta: string }> = {
  not_started: { text: () => "Answer a few focused questions so WebForge understands the decisions behind your idea.", cta: "Start discovery" },
  failed: { text: () => "The last attempt to generate questions failed. Nothing was changed.", cta: "Retry discovery" },
  generating: { text: () => "Questions are being generated.", cta: "Open discovery" },
  awaiting_answers: { text: (o) => (o ? `${o} question${o === 1 ? "" : "s"} waiting for your answer.` : "All questions are resolved. Review the summary when you're ready."), cta: "Continue discovery" },
  ready_for_review: { text: () => "Your summary is ready. Confirm it to complete discovery.", cta: "Review summary" },
  completed: { text: () => "Discovery is complete. Proceed to Research, Strategy and PRD.", cta: "View summary" },
};

/** Shown on the overview once an idea exists. Renders nothing if discovery can't be loaded: it must never break the overview. */
export function DiscoveryCallout({ projectId }: { projectId: string }) {
  const q = useAsync(() => discoveryApi.get(projectId), [projectId]);
  if (!q.data || q.error) return null;
  const copy = COPY[q.data.status];
  return (
    <section aria-label="Discovery" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white p-4">
      <div>
        <h2 className="text-sm font-semibold">Discovery</h2>
        <p className="text-slate-600">{copy.text(q.data.counts.open)}</p>
      </div>
      <Link to={`/projects/${projectId}/discovery`} className="inline-flex h-9 items-center rounded-md border border-slate-300 bg-white px-3.5 text-sm font-medium hover:bg-slate-50">{copy.cta}</Link>
    </section>
  );
}
