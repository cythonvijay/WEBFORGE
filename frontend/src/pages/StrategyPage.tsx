import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorState, LoadingState } from "../components/feedback/States";
import { Alert } from "../components/ui/Alert";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { TextAreaField, TextField } from "../components/ui/Fields";
import { ConfirmDialog, messagesOf } from "../features/research/Dialogs";
import { STATUS } from "../features/research/labels";
import { strategyApi, type OverviewBody, type RecommendationBody } from "../features/strategy/api";
import { ApiError } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import { formatDateTime } from "../lib/utils";
import type { RecArea, RecStatus, StrategyDocument, StrategyEditResponse, StrategyInputs, StrategyRecommendation, StrategyState } from "../types/strategy";
import { useProject } from "./ProjectLayout";

const REC_STATUS_LABELS: Record<RecStatus, { label: string; tone: "success" | "info" | "warning" | "error" | "neutral" }> = {
  grounded_in_confirmed: { label: "Grounded in confirmed fact", tone: "success" },
  supported_by_research: { label: "Supported by research", tone: "info" },
  ai_suggestion: { label: "AI suggestion", tone: "warning" },
  hypothesis: { label: "Hypothesis", tone: "warning" },
  unsupported: { label: "Unsupported — needs evidence", tone: "error" },
};

const REC_AREAS: Record<RecArea, string> = {
  vision: "Product vision",
  goals: "Goals",
  target_users: "Target users",
  value_proposition: "Value proposition",
  differentiation: "Differentiation",
  business_model: "Business model",
  mvp_scope: "MVP scope",
  success_metrics: "Success metrics",
  risks: "Risks",
};

type Notice = { tone: "error" | "warning" | "success"; title: string; body?: string };
type Modal =
  | { kind: "overview" }
  | { kind: "rec"; rec?: StrategyRecommendation }
  | { kind: "delete-rec"; rec: StrategyRecommendation }
  | { kind: "regenerate" }
  | { kind: "approve" }
  | null;

function describe(e: unknown): Notice {
  if (e instanceof ApiError) {
    if (e.status === 503) return { tone: "warning", title: "AI analysis is not configured yet.", body: "Nothing was changed. Configure an AI provider to generate strategy." };
    if (e.status === 502) return { tone: "error", title: "WebForge couldn't produce a valid product strategy.", body: `${e.message} Nothing was changed. You can try again.` };
    return { tone: "error", title: e.message };
  }
  return { tone: "error", title: "Something went wrong." };
}

function InputsPanel({ inputs, preview }: { inputs: StrategyInputs; preview?: boolean }) {
  return (
    <section aria-labelledby="strategy-inputs-h" className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
      <div>
        <h2 id="strategy-inputs-h" className="text-base font-semibold">Strategy inputs & provenance</h2>
        <p className="text-xs text-slate-500">
          {preview ? "Built from your Project Brain, Discovery answers, and approved Research report." : "Facts confirmed by you are separated from AI suggestions, unresolved assumptions, and research findings."}
        </p>
      </div>
      {inputs.missing_inputs.length > 0 && (
        <Alert tone="warning" title="Missing or unconfirmed inputs">
          <ul className="list-disc pl-5">{inputs.missing_inputs.map((m) => <li key={m}>{m}</li>)}</ul>
        </Alert>
      )}
      {inputs.confirmed_facts.length > 0 && (
        <div>
          <h3 className="text-xs font-medium text-slate-500">Confirmed by you ({inputs.confirmed_facts.length})</h3>
          <ul className="mt-1 space-y-1 text-sm">
            {inputs.confirmed_facts.map((x) => (
              <li key={x.ref_id} className="flex flex-wrap items-center gap-1.5">
                <Badge tone="success">{x.ref_id}</Badge>
                <span>{x.text}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {inputs.ai_suggestions.length > 0 && (
        <div>
          <h3 className="text-xs font-medium text-slate-500">AI suggestions — unconfirmed ({inputs.ai_suggestions.length})</h3>
          <ul className="mt-1 space-y-1 text-sm">
            {inputs.ai_suggestions.map((x) => (
              <li key={x.ref_id} className="flex flex-wrap items-center gap-1.5">
                <Badge tone="warning">{x.ref_id}</Badge>
                <span>{x.text}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {inputs.unresolved_assumptions.length > 0 && (
        <div>
          <h3 className="text-xs font-medium text-slate-500">Unresolved assumptions ({inputs.unresolved_assumptions.length})</h3>
          <ul className="mt-1 space-y-1 text-sm">
            {inputs.unresolved_assumptions.map((x) => (
              <li key={x.ref_id} className="flex flex-wrap items-center gap-1.5">
                <Badge tone="neutral">{x.ref_id}</Badge>
                <span>{x.text}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {inputs.research_findings.length > 0 && (
        <div>
          <h3 className="text-xs font-medium text-slate-500">Approved Research findings ({inputs.research_findings.length})</h3>
          <ul className="mt-1 space-y-1 text-sm">
            {inputs.research_findings.map((x) => (
              <li key={x.ref_id} className="flex flex-wrap items-center gap-1.5">
                <Badge tone="info">{x.ref_id}</Badge>
                <span>{x.text}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export default function StrategyPage() {
  const { project } = useProject();
  const pid = project.id;
  const load = useAsync(() => strategyApi.get(pid), [pid]);
  const [override, setOverride] = useState<StrategyState>();
  const [viewing, setViewing] = useState<number | null>(null);
  const viewed = useAsync(() => (viewing ? strategyApi.version(pid, viewing) : Promise.resolve(null)), [pid, viewing]);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef<string | null>(null);
  const [modal, setModal] = useState<Modal>(null);
  const state = override ?? load.data;

  async function run<T>(key: string, fn: () => Promise<T>, onDone: (r: T) => void, refreshOnError = false) {
    if (busyRef.current) return;
    busyRef.current = key; setBusy(key); setNotice(null);
    try { onDone(await fn()); }
    catch (e) {
      setNotice(describe(e));
      if (refreshOnError || (e instanceof ApiError && e.kind === "conflict")) strategyApi.get(pid).then(setOverride).catch(() => undefined);
    } finally { busyRef.current = null; setBusy(null); }
  }

  async function act<T>(fn: () => Promise<T>, onDone: (r: T) => void) {
    if (busyRef.current) throw new Error("Another action is in progress.");
    busyRef.current = "dialog"; setBusy("dialog");
    try { onDone(await fn()); setModal(null); }
    catch (e) { if (e instanceof ApiError && e.kind === "conflict") strategyApi.get(pid).then(setOverride).catch(() => undefined); throw e; }
    finally { busyRef.current = null; setBusy(null); }
  }

  if (load.loading && !state) return <LoadingState label="Loading product strategy…" />;
  if (!state) return <ErrorState message={load.error?.message ?? "We couldn't load product strategy."} onRetry={load.reload} />;

  const doc: StrategyDocument | null = viewing ? (viewed.data ?? null) : state.current;
  const readOnly = !!viewing;
  const canEdit = !readOnly && !!doc && ["draft", "in_review", "approved"].includes(doc.status);
  const content = doc?.content ?? null;
  const hash = doc?.content_hash ?? "";
  const applyEdit = (r: StrategyEditResponse) => {
    setOverride(r.state);
    setNotice(r.document.version !== doc?.version ? { tone: "success", title: `Saved as a new draft, version ${r.document.version}.`, body: "The approved version is unchanged. The new version needs approval again." } : null);
  };
  const generate = (supersede: boolean) => run("generate", () => strategyApi.generate(pid, supersede), (s) => { setOverride(s); setViewing(null); }, true);
  const startLabel = state.status === "not_started" ? "Generate Product Strategy" : state.status === "failed" ? "Retry generating Strategy" : "Regenerate Strategy";

  return (
    <div className="max-w-4xl space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Product Strategy</h1>
        <p className="mt-0.5 text-slate-600">Synthesize product vision, positioning, MVP boundaries, and traceable recommendations from your Brain, Discovery, and approved Research.</p>
        <div className="mt-2 flex flex-wrap items-center gap-1.5" aria-label="Strategy status">
          <Badge tone={STATUS[(doc?.status ?? state.status) as keyof typeof STATUS].tone}>{STATUS[(doc?.status ?? state.status) as keyof typeof STATUS].label}</Badge>
          {doc && <Badge>Version {doc.version}</Badge>}
          <Badge tone={state.lifecycle.status === "complete" ? "success" : "neutral"}>Product stage: {state.lifecycle.status.replace("_", " ")}</Badge>
          {state.approved_version !== null && <Badge tone="success">Approved version: {state.approved_version}</Badge>}
        </div>
      </header>

      <Alert tone="warning" title="Traceable strategy: recommendations are proposals until verified">
        <ul className="list-disc pl-5">{state.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </Alert>
      {notice && <Alert tone={notice.tone} title={notice.title}>{notice.body}</Alert>}
      {state.status === "failed" && state.last_error && !notice && <Alert tone="error" title="The last attempt failed">{state.last_error} Nothing was changed.</Alert>}

      {viewing && (
        <Alert tone="info" title={`Viewing version ${viewing} (read-only)`}>
          <Button size="sm" onClick={() => setViewing(null)}>Back to the current strategy</Button>
        </Alert>
      )}

      {!doc && !viewing && (
        <section className="rounded-lg border border-slate-200 bg-white p-5">
          {!state.idea_ready ? (
            <>
              <h2 className="font-semibold">Describe your idea first</h2>
              <p className="mt-1 text-slate-600">Product Strategy builds on your product idea and approved Research report.</p>
              <Link to={`/projects/${pid}/overview`} className="mt-4 inline-flex h-9 items-center rounded-md border border-slate-300 bg-white px-3.5 text-sm font-medium hover:bg-slate-50">Go to Overview</Link>
            </>
          ) : !state.research_ready ? (
            <>
              <h2 className="font-semibold">Approve Research first</h2>
              <p className="mt-1 text-slate-600">Product Strategy requires an approved Research report so recommendations can trace back to reviewed findings.</p>
              <Link to={`/projects/${pid}/research`} className="mt-4 inline-flex h-9 items-center rounded-md border border-slate-300 bg-white px-3.5 text-sm font-medium hover:bg-slate-50">Go to Research</Link>
            </>
          ) : (
            <>
              <h2 className="font-semibold">No product strategy yet</h2>
              <p className="mt-1 text-slate-600">WebForge will synthesize your Project Brain, Discovery answers, and approved Research v{state.approved_research_version} into an editable strategy.</p>
              <div className="mt-4">
                <Button variant="primary" loading={busy === "generate"} disabled={!!busy || !state.can_generate} onClick={() => void generate(false)}>
                  {busy === "generate" ? "Generating…" : startLabel}
                </Button>
              </div>
            </>
          )}
        </section>
      )}
      {!doc && !viewing && state.inputs_preview && <InputsPanel inputs={state.inputs_preview} preview />}

      {doc && content && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {canEdit && doc.status === "approved" && (
              <p className="text-xs text-slate-600">This version is approved and immutable. Editing creates version {(state.history[0]?.version ?? doc.version) + 1} as a new draft.</p>
            )}
            {!readOnly && doc.status === "draft" && (
              <Button variant="primary" disabled={!!busy || !state.can_submit} loading={busy === "submit"} onClick={() => void run("submit", () => strategyApi.submit(pid, doc.version, hash), setOverride)}>
                Submit for review
              </Button>
            )}
            {!readOnly && doc.status === "in_review" && (
              <Button variant="primary" disabled={!!busy || !state.can_approve} onClick={() => setModal({ kind: "approve" })}>
                Approve version {doc.version}
              </Button>
            )}
            {!readOnly && (
              <Button disabled={!!busy || !state.can_generate} loading={busy === "generate"} onClick={() => (state.needs_supersede ? setModal({ kind: "regenerate" }) : void generate(false))}>
                {busy === "generate" ? "Generating…" : "Regenerate Strategy"}
              </Button>
            )}
            {doc.status === "approved" && (
              <Link to={`/projects/${pid}/prd`} className="inline-flex h-9 items-center rounded-md border border-slate-300 bg-white px-3.5 text-sm font-medium hover:bg-slate-50">
                Continue to PRD
              </Link>
            )}
          </div>

          {doc.status === "approved" && (
            <Alert tone="success" title={`Version ${doc.version} approved${doc.approved_at ? ` on ${formatDateTime(doc.approved_at)}` : ""}`}>
              {doc.acknowledged_unverified ? "Approved with acknowledged AI/unverified recommendations. " : ""}{doc.approval_note}
            </Alert>
          )}
          {doc.warnings.length > 0 && !readOnly && (
            <Alert tone="warning" title="Strategy warnings">
              <ul className="list-disc pl-5">{doc.warnings.map((w) => <li key={w.code}>{w.message}</li>)}</ul>
            </Alert>
          )}

          <InputsPanel inputs={content.inputs} />

          <section aria-labelledby="strategy-core-h" className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
            <div className="flex items-center justify-between gap-2">
              <h2 id="strategy-core-h" className="text-base font-semibold">Positioning & business model</h2>
              {canEdit && <Button size="sm" disabled={!!busy} onClick={() => setModal({ kind: "overview" })}>Edit positioning</Button>}
            </div>
            <dl className="space-y-2 text-sm">
              <div><dt className="text-xs font-medium text-slate-500">Product vision</dt><dd>{content.product_vision}</dd></div>
              <div><dt className="text-xs font-medium text-slate-500">Value proposition</dt><dd>{content.value_proposition}</dd></div>
              <div><dt className="text-xs font-medium text-slate-500">Differentiation</dt><dd>{content.differentiation}</dd></div>
              <div><dt className="text-xs font-medium text-slate-500">Business model</dt><dd>{content.business_model}</dd></div>
            </dl>
          </section>

          <section aria-labelledby="strategy-recs-h" className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <h2 id="strategy-recs-h" className="text-base font-semibold">Strategy recommendations</h2>
              {canEdit && <Button size="sm" disabled={!!busy} onClick={() => setModal({ kind: "rec" })}>Add recommendation</Button>}
            </div>
            <ul className="space-y-2">
              {content.recommendations.map((r) => (
                <li key={r.id} className="rounded-lg border border-slate-200 bg-white p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-semibold">{r.title}</span>
                      <Badge>{REC_AREAS[r.area]}</Badge>
                      <Badge tone={REC_STATUS_LABELS[r.status].tone}>{REC_STATUS_LABELS[r.status].label}</Badge>
                      {r.needs_evidence && <Badge tone="error">Needs evidence</Badge>}
                    </div>
                    {canEdit && (
                      <div className="flex gap-1">
                        <Button size="sm" disabled={!!busy} onClick={() => setModal({ kind: "rec", rec: r })} aria-label={`Edit recommendation ${r.id}`}>Edit</Button>
                        <Button size="sm" variant="ghost" className="text-red-700" disabled={!!busy} onClick={() => setModal({ kind: "delete-rec", rec: r })} aria-label={`Delete recommendation ${r.id}`}>Delete</Button>
                      </div>
                    )}
                  </div>
                  <p className="mt-1.5 text-sm">{r.recommendation}</p>
                  <p className="mt-1 text-xs text-slate-600">Rationale: {r.rationale}</p>
                  {r.supporting_refs.length > 0 && (
                    <p className="mt-1 text-xs text-slate-500">Supporting inputs: {r.supporting_refs.join(", ")}</p>
                  )}
                  {r.note && <p className="mt-1 text-xs text-amber-800">{r.note}</p>}
                </li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="strategy-mvp-h" className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 id="strategy-mvp-h" className="mb-2 text-base font-semibold">Goals, Target Users & MVP Scope</h2>
            <div className="space-y-3 text-sm">
              <div>
                <h3 className="text-xs font-medium text-slate-500">Goals</h3>
                <ul className="mt-1 list-disc pl-5">{content.goals.map((g) => <li key={g.id}>{g.goal} — <span className="text-slate-600">{g.rationale}</span></li>)}</ul>
              </div>
              <div>
                <h3 className="text-xs font-medium text-slate-500">Target users</h3>
                <ul className="mt-1 list-disc pl-5">{content.target_users.map((u) => <li key={u.id}><strong>{u.segment}:</strong> {u.needs}</li>)}</ul>
              </div>
              <div>
                <h3 className="text-xs font-medium text-slate-500">MVP scope boundaries</h3>
                <ul className="mt-1 space-y-1">
                  {content.mvp_scope.map((m) => (
                    <li key={m.id} className="flex flex-wrap items-center gap-1.5">
                      <Badge tone={m.boundary === "in_mvp" ? "success" : m.boundary === "post_mvp" ? "info" : "neutral"}>{m.boundary.replace("_", " ")}</Badge>
                      <span>{m.item}</span>
                      <span className="text-xs text-slate-500">({m.rationale})</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="text-xs font-medium text-slate-500">Success metrics</h3>
                <ul className="mt-1 list-disc pl-5">{content.success_metrics.map((s) => <li key={s.id}>{s.metric}: {s.target_direction}</li>)}</ul>
              </div>
              <div>
                <h3 className="text-xs font-medium text-slate-500">Risks & open decisions</h3>
                <ul className="mt-1 list-disc pl-5">
                  {content.risks.map((rk) => <li key={rk.id}>Risk: {rk.risk} (Mitigation: {rk.mitigation})</li>)}
                  {content.open_decisions.map((d) => <li key={d.id}>Open decision: {d.question} ({d.impact})</li>)}
                </ul>
              </div>
            </div>
          </section>
        </>
      )}

      <section aria-labelledby="strategy-history-h" className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 id="strategy-history-h" className="mb-2 text-base font-semibold">Strategy history</h2>
        {state.history.length === 0 ? <p className="text-slate-600">No versions yet.</p> : (
          <ul className="space-y-2">
            {state.history.map((h) => (
              <li key={h.version} className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="font-medium">Version {h.version}</span> <Badge tone={STATUS[h.status].tone}>{STATUS[h.status].label}</Badge>
                  <p className="text-xs text-slate-500">{h.recommendation_count} recommendations · {h.unsupported_count} unsupported</p>
                </div>
                <Button size="sm" disabled={viewing === h.version} onClick={() => setViewing(h.version)} aria-label={`View version ${h.version}`}>View</Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {modal?.kind === "overview" && doc && content && (
        <OverviewDialog content={content} onClose={() => setModal(null)}
          onSubmit={(b) => act(() => strategyApi.patchOverview(pid, doc.version, hash, b), applyEdit)} />
      )}
      {modal?.kind === "rec" && doc && content && (
        <RecDialog rec={modal.rec} inputs={content.inputs} onClose={() => setModal(null)}
          onSubmit={(b) => act(() => (modal.rec ? strategyApi.patchRecommendation(pid, doc.version, hash, modal.rec.id, b) : strategyApi.addRecommendation(pid, doc.version, hash, b)), applyEdit)} />
      )}
      {modal?.kind === "delete-rec" && doc && (
        <ConfirmDialog title="Delete recommendation?" confirmLabel="Delete recommendation" onClose={() => setModal(null)}
          body={<p>“{modal.rec.title}” will be removed from this strategy version.</p>}
          onConfirm={() => act(() => strategyApi.deleteRecommendation(pid, doc.version, hash, modal.rec.id), applyEdit)} />
      )}
      {modal?.kind === "regenerate" && (
        <ConfirmDialog title="Regenerate strategy?" confirmLabel="Regenerate" onClose={() => setModal(null)}
          body={<p>A new version will be generated. The current draft stays in history as superseded.</p>}
          onConfirm={() => act(() => strategyApi.generate(pid, true), (s) => { setOverride(s); setViewing(null); })} />
      )}
      {modal?.kind === "approve" && doc && (
        <StrategyApproveDialog unverified={doc.unverified_count} onClose={() => setModal(null)}
          onSubmit={(ack, note) => act(() => strategyApi.approve(pid, doc.version, hash, ack, note), setOverride)} />
      )}
    </div>
  );
}

function OverviewDialog({ content, onSubmit, onClose }: { content: { product_vision: string; value_proposition: string; differentiation: string; business_model: string }; onSubmit: (b: OverviewBody) => Promise<void>; onClose: () => void }) {
  const [vision, setVision] = useState(content.product_vision);
  const [vp, setVp] = useState(content.value_proposition);
  const [diff, setDiff] = useState(content.differentiation);
  const [bm, setBm] = useState(content.business_model);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  return (
    <Dialog title="Edit positioning & business model" onClose={onClose}>
      <form noValidate className="space-y-3" onSubmit={async (e) => { e.preventDefault(); setBusy(true); setErrors([]); try { await onSubmit({ product_vision: vision.trim(), value_proposition: vp.trim(), differentiation: diff.trim(), business_model: bm.trim() }); } catch (err) { setErrors(messagesOf(err)); setBusy(false); } }}>
        {errors.length > 0 && <Alert tone="error">{errors.map((m) => <p key={m}>{m}</p>)}</Alert>}
        <TextAreaField label="Product vision" rows={2} value={vision} onChange={(e) => setVision(e.target.value)} />
        <TextAreaField label="Value proposition" rows={2} value={vp} onChange={(e) => setVp(e.target.value)} />
        <TextAreaField label="Differentiation" rows={2} value={diff} onChange={(e) => setDiff(e.target.value)} />
        <TextAreaField label="Business model" rows={2} value={bm} onChange={(e) => setBm(e.target.value)} />
        <div className="flex justify-end gap-2"><Button onClick={onClose} disabled={busy}>Cancel</Button><Button type="submit" variant="primary" loading={busy}>Save positioning</Button></div>
      </form>
    </Dialog>
  );
}

function RecDialog({ rec, inputs, onSubmit, onClose }: { rec?: StrategyRecommendation; inputs: StrategyInputs; onSubmit: (b: RecommendationBody) => Promise<void>; onClose: () => void }) {
  const [area, setArea] = useState<RecArea>(rec?.area ?? "mvp_scope");
  const [title, setTitle] = useState(rec?.title ?? "");
  const [recommendation, setRecommendation] = useState(rec?.recommendation ?? "");
  const [rationale, setRationale] = useState(rec?.rationale ?? "");
  const [status, setStatus] = useState<RecStatus>(rec?.status ?? "ai_suggestion");
  const [refs, setRefs] = useState<string[]>(rec?.supporting_refs ?? []);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const allRefs = [...inputs.confirmed_facts, ...inputs.ai_suggestions, ...inputs.unresolved_assumptions, ...inputs.research_findings];

  return (
    <Dialog title={rec ? `Edit recommendation ${rec.id}` : "Add recommendation"} onClose={onClose}>
      <form noValidate className="space-y-3" onSubmit={async (e) => { e.preventDefault(); setBusy(true); setErrors([]); try { await onSubmit({ area, title: title.trim(), recommendation: recommendation.trim(), rationale: rationale.trim(), status, supporting_refs: refs, needs_evidence: status === "unsupported" || refs.length === 0 }); } catch (err) { setErrors(messagesOf(err)); setBusy(false); } }}>
        {errors.length > 0 && <Alert tone="error">{errors.map((m) => <p key={m}>{m}</p>)}</Alert>}
        <label className="block"><span className="mb-1 block text-xs font-medium text-slate-700">Area</span>
          <select value={area} onChange={(e) => setArea(e.target.value as RecArea)} className="h-9 w-full rounded-md border border-slate-300 bg-white px-2 text-sm">
            {(Object.keys(REC_AREAS) as RecArea[]).map((a) => <option key={a} value={a}>{REC_AREAS[a]}</option>)}
          </select>
        </label>
        <TextField label="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <TextAreaField label="Recommendation" rows={3} value={recommendation} onChange={(e) => setRecommendation(e.target.value)} />
        <TextAreaField label="Rationale" rows={2} value={rationale} onChange={(e) => setRationale(e.target.value)} />
        <label className="block"><span className="mb-1 block text-xs font-medium text-slate-700">Provenance status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value as RecStatus)} className="h-9 w-full rounded-md border border-slate-300 bg-white px-2 text-sm">
            {(Object.keys(REC_STATUS_LABELS) as RecStatus[]).map((s) => <option key={s} value={s}>{REC_STATUS_LABELS[s].label}</option>)}
          </select>
        </label>
        <fieldset className="space-y-1">
          <legend className="text-xs font-medium text-slate-700">Supporting inputs</legend>
          <div className="max-h-32 overflow-y-auto space-y-1 rounded border border-slate-200 p-2 text-xs">
            {allRefs.map((item) => (
              <label key={item.ref_id} className="flex items-center gap-2">
                <input type="checkbox" checked={refs.includes(item.ref_id)} onChange={(e) => setRefs(e.target.checked ? [...refs, item.ref_id] : refs.filter((x) => x !== item.ref_id))} />
                <span>[{item.ref_id}] {item.text}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <div className="flex justify-end gap-2"><Button onClick={onClose} disabled={busy}>Cancel</Button><Button type="submit" variant="primary" loading={busy}>{rec ? "Save recommendation" : "Add recommendation"}</Button></div>
      </form>
    </Dialog>
  );
}

function StrategyApproveDialog({ unverified, onSubmit, onClose }: { unverified: number; onSubmit: (ack: boolean, note: string) => Promise<void>; onClose: () => void }) {
  const [ack, setAck] = useState(false);
  const [note, setNote] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  return (
    <Dialog title="Approve this strategy version" onClose={onClose}>
      <form noValidate className="space-y-3" onSubmit={async (e) => { e.preventDefault(); setBusy(true); setErrors([]); try { await onSubmit(ack, note); } catch (err) { setErrors(messagesOf(err)); setBusy(false); } }}>
        {errors.length > 0 && <Alert tone="error">{errors.map((m) => <p key={m}>{m}</p>)}</Alert>}
        <p>Approving records this exact Strategy version in your Project Brain and unlocks PRD generation.</p>
        {unverified > 0 && (
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-0.5 h-4 w-4" checked={ack} onChange={(e) => setAck(e.target.checked)} />
            <span>I understand that {unverified} recommendation{unverified === 1 ? " is an" : "s are"} AI suggestion, hypothesis, or unsupported claim.</span>
          </label>
        )}
        <TextAreaField label="Approval note (optional)" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        <div className="flex justify-end gap-2">
          <Button onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" variant="primary" loading={busy} disabled={unverified > 0 && !ack}>Approve strategy</Button>
        </div>
      </form>
    </Dialog>
  );
}
