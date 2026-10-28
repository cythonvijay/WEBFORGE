import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { TextAreaField } from "../../components/ui/Fields";
import type { DiscoveryQuestion, Draft } from "../../types/discovery";

const STATUS_TONE = { open: "neutral", answered: "success", skipped: "neutral", deferred: "warning" } as const;
const STATUS_LABEL = { open: "Open", answered: "Answered", skipped: "Skipped", deferred: "Deferred" } as const;

function Choice({ type, name, value, label, checked, disabled, onChange }: { type: "radio" | "checkbox"; name: string; value: string; label: string; checked: boolean; disabled: boolean; onChange: () => void }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 py-0.5">
      <input type={type} name={name} value={value} checked={checked} disabled={disabled} onChange={onChange} className="h-4 w-4" />
      <span>{label}</span>
    </label>
  );
}

export function QuestionList({ questions, drafts, errors, busy, onDraft, onSkip, onDefer }: {
  questions: DiscoveryQuestion[]; drafts: Record<string, Draft>; errors: Record<string, string>; busy: boolean;
  onDraft: (id: string, d: Draft) => void; onSkip: (id: string) => void; onDefer: (id: string) => void;
}) {
  const rounds = new Set(questions.map((q) => q.round)).size;
  let lastRound = 0;
  return (
    <div className="space-y-4">
      {questions.map((q) => {
        const d = drafts[q.id];
        const err = errors[q.id];
        const heading = rounds > 1 && q.round !== lastRound ? <h2 key={`r${q.round}`} className="pt-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Round {q.round}</h2> : null;
        lastRound = q.round;
        const meta = (
          <>
            <span className="ml-2 inline-flex gap-1 align-middle">
              <Badge tone={STATUS_TONE[q.status]}>{STATUS_LABEL[q.status]}</Badge>
              {q.required && <Badge>Required</Badge>}
            </span>
            <p className="mt-0.5 text-xs text-slate-600">Why we ask: {q.rationale}</p>
          </>
        );
        const choiceBody = (type: "radio" | "checkbox") => (
          <div className="mt-2">
            {q.qtype === "confirmation" ? (
              [["yes", "Yes", true], ["no", "No", false]].map(([k, label, val]) => (
                <Choice key={String(k)} type="radio" name={q.id} value={String(k)} label={String(label)} disabled={busy} checked={d === val} onChange={() => onDraft(q.id, val as boolean)} />
              ))
            ) : q.options.map((o) => (
              <Choice key={o.id} type={type} name={q.id} value={o.id} label={o.label} disabled={busy}
                checked={type === "radio" ? d === o.id : Array.isArray(d) && d.includes(o.id)}
                onChange={() => onDraft(q.id, type === "radio" ? o.id : (Array.isArray(d) && d.includes(o.id) ? d.filter((x) => x !== o.id) : [...(Array.isArray(d) ? d : []), o.id]))} />
            ))}
          </div>
        );
        return (
          <div key={q.id}>
            {heading}
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              {q.qtype === "free_text" ? (
                <>
                  <TextAreaField label={q.prompt} rows={3} value={typeof d === "string" ? d : ""} maxLength={q.max_length ?? undefined} disabled={busy}
                    onChange={(e) => onDraft(q.id, e.target.value)} error={err} />
                  <div>{meta}</div>
                </>
              ) : (
                <fieldset aria-invalid={!!err || undefined} aria-describedby={err ? `${q.id}-err` : undefined}>
                  <legend className="font-medium">{q.prompt}{meta}</legend>
                  {choiceBody(q.qtype === "multiple_choice" ? "checkbox" : "radio")}
                  {err && <p id={`${q.id}-err`} className="mt-1 text-xs text-red-700">{err}</p>}
                </fieldset>
              )}
              {(q.status !== "answered") && (
                <div className="mt-3 flex gap-2">
                  {!q.required && q.status !== "skipped" && <Button size="sm" disabled={busy} onClick={() => onSkip(q.id)} aria-label={`Skip: ${q.prompt}`}>Skip</Button>}
                  {q.status !== "deferred" && <Button size="sm" disabled={busy} onClick={() => onDefer(q.id)} aria-label={`Answer later: ${q.prompt}`}>Answer later</Button>}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
