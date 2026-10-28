import { Alert } from "../../components/ui/Alert";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { formatDateTime, safeHttpUrl } from "../../lib/utils";
import type { Brief, BriefItem, ReportSummary, Source } from "../../types/research";
import { STATUS } from "./labels";

const Item = ({ i }: { i: BriefItem }) => (
  <li className="[overflow-wrap:anywhere]">{i.text} <Badge tone={i.status === "user_confirmed" ? "success" : "warning"}>{i.status === "user_confirmed" ? "Confirmed by you" : "AI-proposed, unconfirmed"}</Badge></li>
);
const Plain = ({ title, items }: { title: string; items: string[] }) => items.length ? (
  <div><h3 className="text-xs font-medium text-slate-500">{title}</h3><ul className="mt-0.5 list-disc space-y-0.5 pl-5">{items.map((x) => <li key={x} className="[overflow-wrap:anywhere]">{x}</li>)}</ul></div>
) : null;
const Items = ({ title, items }: { title: string; items: BriefItem[] }) => items.length ? (
  <div><h3 className="text-xs font-medium text-slate-500">{title}</h3><ul className="mt-0.5 list-disc space-y-1 pl-5">{items.map((i, n) => <Item key={n} i={i} />)}</ul></div>
) : null;

export function BriefPanel({ brief, preview }: { brief: Brief; preview?: boolean }) {
  return (
    <section aria-labelledby="brief-h" className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
      <div><h2 id="brief-h" className="text-base font-semibold">Research brief</h2>
        <p className="text-xs text-slate-500">{preview ? "Built from your Project Brain. Objectives and questions are added when the report is generated." : "Facts come from your Project Brain; objectives, questions and scope were proposed by the AI."}</p></div>
      {brief.missing_inputs.length > 0 && (
        <Alert tone="warning" title="Missing or unconfirmed inputs"><ul className="list-disc pl-5">{brief.missing_inputs.map((m) => <li key={m}>{m}</li>)}</ul></Alert>
      )}
      {brief.product_summary && <div><h3 className="text-xs font-medium text-slate-500">Product</h3><p>{brief.product_summary}</p></div>}
      {brief.problem && <div><h3 className="text-xs font-medium text-slate-500">Problem</h3><ul><Item i={brief.problem} /></ul></div>}
      <Items title="Target users" items={brief.target_users} />
      <Items title="Business goals" items={brief.business_goals} />
      <Items title="Confirmed requirements" items={brief.confirmed_requirements} />
      <Items title="Constraints" items={brief.constraints} />
      <Plain title="Important unknowns" items={brief.unknowns} />
      <Plain title="Research objectives" items={brief.objectives} />
      <Plain title="Research questions" items={brief.research_questions} />
      <Plain title="In scope" items={brief.scope_in} />
      <Plain title="Out of scope" items={brief.scope_out} />
    </section>
  );
}

export function SourcesPanel({ sources, canEdit, busy, onAdd, onEdit, onDelete }: { sources: Source[]; canEdit: boolean; busy: boolean; onAdd: () => void; onEdit: (s: Source) => void; onDelete: (s: Source) => void }) {
  return (
    <section aria-labelledby="sources-h" className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between gap-2"><h2 id="sources-h" className="text-base font-semibold">Sources</h2>
        {canEdit && <Button size="sm" disabled={busy} onClick={onAdd}>Add source</Button>}</div>
      {sources.length === 0 ? <p className="text-slate-600">No sources attached. Nothing in this report is backed by a source yet. Add sources you have examined to support findings.</p> : (
        <ul className="space-y-2">{sources.map((s) => (
          <li key={s.id} className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0"><a href={safeHttpUrl(s.url)} target="_blank" rel="noopener noreferrer" className="text-blue-700 underline [overflow-wrap:anywhere]">{s.title}</a>
              <p className="text-xs text-slate-500">{s.publisher ? `${s.publisher} · ` : ""}{s.examined ? `Examined by you${s.accessed_on ? ` on ${s.accessed_on}` : ""}` : "Not examined"}</p></div>
            {canEdit && <div className="flex gap-1"><Button size="sm" disabled={busy} onClick={() => onEdit(s)} aria-label={`Edit source ${s.id}`}>Edit</Button>
              <Button size="sm" variant="ghost" className="text-red-700" disabled={busy} onClick={() => onDelete(s)} aria-label={`Delete source ${s.id}`}>Delete</Button></div>}
          </li>))}</ul>
      )}
    </section>
  );
}

export function HistoryPanel({ history, viewing, onView }: { history: ReportSummary[]; viewing: number | null; onView: (v: number) => void }) {
  return (
    <section aria-labelledby="history-h" className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="history-h" className="mb-2 text-base font-semibold">Report history</h2>
      {history.length === 0 ? <p className="text-slate-600">No versions yet.</p> : (
        <ul className="space-y-2">{history.map((h) => (
          <li key={h.version} className="flex flex-wrap items-center justify-between gap-2">
            <div><span className="font-medium">Version {h.version}</span> <Badge tone={STATUS[h.status].tone}>{STATUS[h.status].label}</Badge>
              <p className="text-xs text-slate-500">{h.finding_count} findings · {h.source_count} sources · {h.approved_at ? `approved ${formatDateTime(h.approved_at)}` : `updated ${formatDateTime(h.updated_at)}`}{h.parent_version ? ` · based on v${h.parent_version}` : ""}</p></div>
            <Button size="sm" disabled={viewing === h.version} onClick={() => onView(h.version)} aria-label={`View version ${h.version}`}>View</Button>
          </li>))}</ul>
      )}
    </section>
  );
}
