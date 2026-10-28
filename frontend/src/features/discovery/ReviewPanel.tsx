import { Alert } from "../../components/ui/Alert";
import type { DiscoverySummary } from "../../types/discovery";

const SOURCE: Record<string, string> = { ai_suggested: "AI-suggested", user_declared: "Declared by you", unanswered_question: "From an unanswered question" };
const show = (v: unknown) => (Array.isArray(v) ? v.join(", ") : typeof v === "boolean" ? (v ? "Yes" : "No") : String(v));

function Section({ title, hint, children, empty }: { title: string; hint?: string; children?: React.ReactNode; empty?: string }) {
  return (
    <section aria-label={title}>
      <h2 className="text-sm font-semibold">{title}</h2>
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
      <div className="mt-1.5">{children ?? <p className="text-slate-500">{empty}</p>}</div>
    </section>
  );
}

export function ReviewPanel({ summary }: { summary: DiscoverySummary }) {
  const refs = (list: DiscoverySummary["unanswered"]) => list.length ? <ul className="list-disc space-y-0.5 pl-5">{list.map((q) => <li key={q.id}>{q.question}{q.required && <span className="text-xs text-slate-500"> (required)</span>}</li>)}</ul> : undefined;
  return (
    <div className="space-y-5 rounded-lg border border-slate-200 bg-white p-5">
      <Alert tone="info">This summary reflects what you told WebForge. It is discovery clarification only, not market validation or research.</Alert>
      <Section title="Confirmed by you" empty="Nothing has been confirmed yet.">
        {summary.confirmed.length ? <dl className="space-y-2">{summary.confirmed.map((f) => <div key={f.question_id}><dt className="text-xs text-slate-500">{f.question}</dt><dd>{show(f.answer)}</dd></div>)}</dl> : undefined}
      </Section>
      <Section title="Proposed by AI, awaiting your approval" hint="Interpretations from your idea description. They are not facts until you confirm them." empty="No unconfirmed proposals.">
        {summary.proposed.length ? <div className="space-y-2">{summary.proposed.map((p) => <div key={p.label}><h3 className="text-xs text-slate-500">{p.label}</h3><ul className="list-disc pl-5">{p.items.map((i) => <li key={i}>{i}</li>)}</ul></div>)}</div> : undefined}
      </Section>
      <Section title="Unresolved assumptions" hint="Treated as unverified." empty="No assumptions recorded.">
        {summary.assumptions.length ? <ul className="space-y-1">{summary.assumptions.map((a) => <li key={a.id}>{a.text} <span className="text-xs text-slate-500">· {SOURCE[a.source]}, {a.status}</span></li>)}</ul> : undefined}
      </Section>
      <Section title="Unanswered questions" empty="None.">{refs(summary.unanswered)}</Section>
      <Section title="Deferred for later" empty="None.">{refs(summary.deferred)}</Section>
      {summary.skipped.length > 0 && <Section title="Skipped">{refs(summary.skipped)}</Section>}
    </div>
  );
}
