import { ProgressBar } from "../../components/ui/ProgressBar";
import { changeLabel, formatDateTime, stageLabel, timeAgo } from "../../lib/utils";
import type { Overview } from "../../types/lifecycle";

const Panel = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section aria-label={title} className="rounded-lg border border-slate-200 bg-white p-4">
    <h2 className="mb-2 text-sm font-semibold">{title}</h2>
    {children}
  </section>
);

export function ProgressPanel({ o }: { o: Overview }) {
  return (
    <Panel title="Project progress">
      <ProgressBar value={o.progress} label="Project progress" />
      <p className="mt-2 text-slate-600">{o.completed.length} of {o.stages.length} stages complete</p>
    </Panel>
  );
}

export function NextActionPanel({ o }: { o: Overview }) {
  const next = o.next_action ? o.stages.find((s) => s.stage === o.next_action) : undefined;
  return (
    <Panel title="Next action">
      {next ? <p className="text-base font-medium">{next.status === "in_progress" ? "Continue" : next.status === "needs_review" ? "Review" : "Start"} {stageLabel(next.stage)}</p>
        : <p className="text-slate-600">No next action available.</p>}
    </Panel>
  );
}

export function CurrentWorkPanel({ o }: { o: Overview }) {
  const groups: [string, string[]][] = [["In progress", o.in_progress], ["Needs review", o.needs_review], ["Blocked", o.blocked]];
  const any = groups.some(([, l]) => l.length);
  return (
    <Panel title="Current work">
      {!any ? <p className="text-slate-600">No stages are in progress, in review or blocked.</p> : (
        <dl className="space-y-1.5">
          {groups.filter(([, l]) => l.length).map(([label, l]) => (
            <div key={label}><dt className="text-xs text-slate-500">{label}</dt><dd>{l.map(stageLabel).join(", ")}</dd></div>
          ))}
        </dl>
      )}
    </Panel>
  );
}

export function RecentChangesPanel({ o }: { o: Overview }) {
  return (
    <Panel title="Recent changes">
      {o.recent_changes.length === 0 ? <p className="text-slate-600">No recent changes yet.</p> : (
        <ul className="space-y-1.5">
          {o.recent_changes.map((c) => (
            <li key={c.version} className="flex items-baseline justify-between gap-2">
              <span>{changeLabel(c.change_type)} <span className="text-xs text-slate-500">· v{c.version}</span></span>
              <span className="whitespace-nowrap text-xs text-slate-500" title={formatDateTime(c.created_at)}>{timeAgo(c.created_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export function SystemStatePanel({ o }: { o: Overview }) {
  return (
    <Panel title="System state">
      <dl className="grid grid-cols-[7rem_1fr] gap-y-1">
        <dt className="text-slate-500">Brain version</dt><dd>{o.recent_changes[0] ? `v${o.recent_changes[0].version}` : "—"}</dd>
        <dt className="text-slate-500">Last updated</dt><dd>{formatDateTime(o.project.updated_at)}</dd>
        <dt className="text-slate-500">Created</dt><dd>{formatDateTime(o.project.created_at)}</dd>
      </dl>
      <p className="mt-2 text-xs text-slate-500">Build, deployment and monitoring are not connected yet.</p>
    </Panel>
  );
}
