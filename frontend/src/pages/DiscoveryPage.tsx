import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ErrorState, LoadingState } from "../components/feedback/States";
import { Alert } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { discoveryApi } from "../features/discovery/api";
import { draftFromAnswer, isPending, validateDraft } from "../features/discovery/drafts";
import { QuestionList } from "../features/discovery/QuestionList";
import { ReviewPanel } from "../features/discovery/ReviewPanel";
import { ApiError } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import type { DiscoveryQuestion, DiscoveryState, Draft } from "../types/discovery";
import { useProject } from "./ProjectLayout";

type Notice = { tone: "error" | "warning" | "success"; title: string; body?: string };

function describe(e: unknown): Notice {
  if (e instanceof ApiError) {
    if (e.status === 503) return { tone: "warning", title: "AI analysis is not configured yet.", body: "Nothing was changed and your saved answers are safe. Configure an AI provider to continue." };
    if (e.status === 502) return { tone: "error", title: "WebForge couldn't use the AI response.", body: `${e.message} Nothing was changed and your saved answers are safe. You can try again.` };
    return { tone: "error", title: e.message };
  }
  return { tone: "error", title: "Something went wrong." };
}

const valueOf = (q: DiscoveryQuestion, d: Draft) => (q.qtype === "free_text" && typeof d === "string" ? d.trim() : d);

export default function DiscoveryPage() {
  const { project } = useProject();
  const navigate = useNavigate();
  const overviewPath = `/projects/${project.id}/overview`;
  const load = useAsync(() => discoveryApi.get(project.id), [project.id]);
  const [override, setOverride] = useState<DiscoveryState>();
  const [edits, setDrafts] = useState<Record<string, Draft>>({}); // only what the user changed and has not saved yet
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef<string | null>(null); // synchronous guard: a double click can't send two requests
  const [editing, setEditing] = useState(false);
  const [accept, setAccept] = useState(false);
  const state = override ?? load.data;

  async function run(key: string, fn: () => Promise<DiscoveryState>, opts: { refreshOnError?: boolean; onDone?: (s: DiscoveryState) => void } = {}) {
    if (busyRef.current) return;
    busyRef.current = key; setBusy(key); setNotice(null);
    try {
      const s = await fn();
      setOverride(s); setErrors({});
      opts.onDone?.(s);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "validation" && Array.isArray(e.detail)) {
        const map: Record<string, string> = {};
        for (const d of e.detail as { loc?: unknown[]; msg?: string }[]) { const id = String(d.loc?.[d.loc.length - 1] ?? ""); if (id) map[id] = d.msg ?? "Invalid answer."; }
        setErrors(map); setNotice({ tone: "error", title: "Some answers need attention." });
      } else {
        setNotice(describe(e));
        if (opts.refreshOnError) discoveryApi.get(project.id).then(setOverride).catch(() => undefined);
      }
    } finally { busyRef.current = null; setBusy(null); }
  }

  if (load.loading && !state) return <LoadingState label="Loading discovery…" />;
  if (!state) return <ErrorState message={load.error?.message ?? "We couldn't load discovery."} onRetry={load.reload} />;

  // What each field shows: the user's unsaved edit if there is one, otherwise the saved server answer (no empty first paint).
  const drafts: Record<string, Draft> = Object.fromEntries(state.questions.map((q) => [q.id, q.id in edits ? edits[q.id] : draftFromAnswer(q)]));
  const pending = state.questions.filter((q) => isPending(q, drafts[q.id]));
  const save = (thenLeave = false) => {
    const errs: Record<string, string> = {}, items: { question_id: string; value: unknown }[] = [];
    for (const q of pending) { const e = validateDraft(q, drafts[q.id]); if (e) errs[q.id] = e; else items.push({ question_id: q.id, value: valueOf(q, drafts[q.id]) }); }
    setErrors(errs);
    if (Object.keys(errs).length) return setNotice({ tone: "error", title: "Some answers need attention." });
    if (!items.length) return thenLeave ? navigate(overviewPath) : undefined;
    void run("save", () => discoveryApi.answer(project.id, items), {
      onDone: (s) => {
        setDrafts((d) => Object.fromEntries(Object.entries(d).filter(([id]) => !items.some((i) => i.question_id === id)))); // saved: show the server value again
        if (thenLeave) navigate(overviewPath);
      },
    });
  };
  const generate = (key: string, fn: () => Promise<DiscoveryState>) => run(key, fn, { refreshOnError: true });
  const questionList = (qs: DiscoveryQuestion[]) => (
    <QuestionList questions={qs} drafts={drafts} errors={errors} busy={!!busy}
      onDraft={(id, d) => { setDrafts((p) => ({ ...p, [id]: d })); setErrors((p) => { const { [id]: _, ...rest } = p; return rest; }); }}
      onSkip={(id) => void run("skip", () => discoveryApi.skip(project.id, id))}
      onDefer={(id) => void run("defer", () => discoveryApi.defer(project.id, id))} />
  );
  const c = state.counts;
  const outstanding = state.outstanding_questions.length;
  const startButton = (label: string) => (
    <Button variant="primary" loading={busy === "start"} disabled={!!busy} onClick={() => void generate("start", () => discoveryApi.start(project.id))}>
      {busy === "start" ? "Preparing questions…" : label}
    </Button>
  );

  return (
    <div className="max-w-3xl space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Discovery</h1>
        <p className="mt-0.5 text-slate-600">Let's clarify the decisions that will shape your product.</p>
        {c.total > 0 && (
          <p className="mt-2 text-sm text-slate-600" aria-label="Discovery progress">
            Round {state.round} of {state.max_rounds} · {c.answered} answered · {c.skipped} skipped · {c.deferred} deferred · {c.open} open
          </p>
        )}
      </header>

      {notice && <Alert tone={notice.tone} title={notice.title}>{notice.body}</Alert>}

      {state.status === "not_started" && (
        <section className="rounded-lg border border-slate-200 bg-white p-5">
          {state.idea_ready ? (
            <>
              <h2 className="font-semibold">Start with a few focused questions</h2>
              <p className="mt-1 text-slate-600">WebForge reads your idea and asks only what would change the product's direction. You can skip or answer later, and come back any time.</p>
              <div className="mt-4">{startButton("Start discovery")}</div>
            </>
          ) : (
            <>
              <h2 className="font-semibold">Describe your idea first</h2>
              <p className="mt-1 text-slate-600">Discovery builds on your product idea, and none has been analyzed yet.</p>
              <Link to={overviewPath} className="mt-4 inline-flex h-9 items-center rounded-md border border-slate-300 bg-white px-3.5 text-sm font-medium hover:bg-slate-50">Go to Overview</Link>
            </>
          )}
        </section>
      )}

      {state.status === "failed" && (
        <section className="rounded-lg border border-slate-200 bg-white p-5">
          <h2 className="font-semibold">Questions couldn't be generated</h2>
          <p className="mt-1 text-slate-600">{state.last_error ?? "The last attempt failed."} Nothing was changed.</p>
          <div className="mt-4">{startButton("Retry")}</div>
        </section>
      )}

      {state.status === "generating" && (
        <Alert tone="success" title="Questions are being generated.">This can take a moment. If it was interrupted, refresh to continue.
          <div className="mt-2"><Button size="sm" onClick={() => { setOverride(undefined); load.reload(); }}>Refresh</Button></div>
        </Alert>
      )}

      {state.status === "awaiting_answers" && (
        <>
          {questionList(state.questions)}
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" loading={busy === "save"} disabled={!!busy || pending.length === 0} onClick={() => save()}>{busy === "save" ? "Saving…" : "Save answers"}</Button>
            <Button disabled={!!busy} onClick={() => save(true)}>Save and finish later</Button>
            {state.can_generate_next_round && <Button disabled={!!busy || pending.length > 0} loading={busy === "next"} onClick={() => void generate("next", () => discoveryApi.nextRound(project.id))}>{busy === "next" ? "Preparing questions…" : "Generate more questions"}</Button>}
            {state.can_review && <Button disabled={!!busy || pending.length > 0} onClick={() => void run("review", () => discoveryApi.review(project.id))}>Review summary</Button>}
          </div>
          {pending.length > 0 && <p className="text-xs text-slate-500">You have unsaved answers. Save them before generating more questions or reviewing.</p>}
          {c.open > 0 && <p className="text-xs text-slate-500">{state.next_step.label}.</p>}
        </>
      )}

      {(state.status === "ready_for_review" || state.status === "completed") && state.summary && (
        <>
          {state.status === "completed" && <Alert tone="success" title="Discovery completed.">{state.next_step.note}</Alert>}
          <ReviewPanel summary={state.summary} />
        </>
      )}

      {state.status === "ready_for_review" && (
        <>
          <div>
            <Button onClick={() => setEditing((e) => !e)} aria-expanded={editing}>{editing ? "Hide answers" : "Edit answers"}</Button>
          </div>
          {editing && (
            <div className="space-y-3">
              {questionList(state.questions)}
              <Button variant="primary" loading={busy === "save"} disabled={!!busy || pending.length === 0} onClick={() => save()}>{busy === "save" ? "Saving…" : "Save answers"}</Button>
            </div>
          )}
          <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold">Complete discovery</h2>
            {outstanding > 0 && (
              <label className="flex items-start gap-2">
                <input type="checkbox" className="mt-0.5 h-4 w-4" checked={accept} onChange={(e) => setAccept(e.target.checked)} />
                <span>Complete with documented assumptions. {outstanding} question{outstanding === 1 ? " is" : "s are"} unanswered or deferred and will be recorded as unverified assumptions.</span>
              </label>
            )}
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" loading={busy === "complete"} disabled={!!busy || pending.length > 0 || (outstanding > 0 && !accept)}
                onClick={() => void run("complete", () => discoveryApi.complete(project.id, accept))}>{busy === "complete" ? "Completing…" : "Complete discovery"}</Button>
              {state.can_generate_next_round && <Button disabled={!!busy || pending.length > 0} loading={busy === "next"} onClick={() => void generate("next", () => discoveryApi.nextRound(project.id))}>{busy === "next" ? "Preparing questions…" : "Generate more questions"}</Button>}
            </div>
            {pending.length > 0 && <p className="text-xs text-slate-500">Save your edited answers before completing.</p>}
          </div>
        </>
      )}

      {state.status === "completed" && (
        <Link to={overviewPath} className="inline-flex h-9 items-center rounded-md border border-slate-300 bg-white px-3.5 text-sm font-medium hover:bg-slate-50">Return to project overview</Link>
      )}
    </div>
  );
}
