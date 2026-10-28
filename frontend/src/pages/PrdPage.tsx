import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorState, LoadingState } from "../components/feedback/States";
import { Alert } from "../components/ui/Alert";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { TextAreaField, TextField } from "../components/ui/Fields";
import { prdApi, type FunctionalReqBody } from "../features/prd/api";
import { ConfirmDialog, messagesOf } from "../features/research/Dialogs";
import { STATUS } from "../features/research/labels";
import { ApiError } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import { formatDateTime } from "../lib/utils";
import type { FunctionalRequirement, MvpBoundary, PrdDocument, PrdEditResponse, PrdState, Priority } from "../types/prd";
import { useProject } from "./ProjectLayout";

const PRIORITY_LABELS: Record<Priority, { label: string; tone: "error" | "warning" | "info" | "neutral" }> = {
  must_have: { label: "Must have", tone: "error" },
  should_have: { label: "Should have", tone: "warning" },
  could_have: { label: "Could have", tone: "info" },
  wont_have: { label: "Won't have", tone: "neutral" },
};

const BOUNDARY_LABELS: Record<MvpBoundary, { label: string; tone: "success" | "info" | "neutral" }> = {
  in_mvp: { label: "In MVP", tone: "success" },
  post_mvp: { label: "Post-MVP", tone: "info" },
  out_of_scope: { label: "Out of scope", tone: "neutral" },
};

type Notice = { tone: "error" | "warning" | "success"; title: string; body?: string };
type Modal =
  | { kind: "fr"; req?: FunctionalRequirement }
  | { kind: "delete-fr"; req: FunctionalRequirement }
  | { kind: "regenerate" }
  | { kind: "approve" }
  | null;

function describe(e: unknown): Notice {
  if (e instanceof ApiError) {
    if (e.status === 503) return { tone: "warning", title: "AI analysis is not configured yet.", body: "Nothing was changed. Configure an AI provider to generate the PRD." };
    if (e.status === 502) return { tone: "error", title: "WebForge couldn't produce a valid PRD.", body: `${e.message} Nothing was changed. You can try again.` };
    return { tone: "error", title: e.message };
  }
  return { tone: "error", title: "Something went wrong." };
}

export default function PrdPage() {
  const { project } = useProject();
  const pid = project.id;
  const load = useAsync(() => prdApi.get(pid), [pid]);
  const [override, setOverride] = useState<PrdState>();
  const [viewing, setViewing] = useState<number | null>(null);
  const viewed = useAsync(() => (viewing ? prdApi.version(pid, viewing) : Promise.resolve(null)), [pid, viewing]);
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
      if (refreshOnError || (e instanceof ApiError && e.kind === "conflict")) prdApi.get(pid).then(setOverride).catch(() => undefined);
    } finally { busyRef.current = null; setBusy(null); }
  }

  async function act<T>(fn: () => Promise<T>, onDone: (r: T) => void) {
    if (busyRef.current) throw new Error("Another action is in progress.");
    busyRef.current = "dialog"; setBusy("dialog");
    try { onDone(await fn()); setModal(null); }
    catch (e) { if (e instanceof ApiError && e.kind === "conflict") prdApi.get(pid).then(setOverride).catch(() => undefined); throw e; }
    finally { busyRef.current = null; setBusy(null); }
  }

  if (load.loading && !state) return <LoadingState label="Loading PRD…" />;
  if (!state) return <ErrorState message={load.error?.message ?? "We couldn't load the PRD."} onRetry={load.reload} />;

  const doc: PrdDocument | null = viewing ? (viewed.data ?? null) : state.current;
  const readOnly = !!viewing;
  const canEdit = !readOnly && !!doc && ["draft", "in_review", "approved"].includes(doc.status);
  const content = doc?.content ?? null;
  const hash = doc?.content_hash ?? "";
  const applyEdit = (r: PrdEditResponse) => {
    setOverride(r.state);
    setNotice(r.document.version !== doc?.version ? { tone: "success", title: `Saved as a new draft, version ${r.document.version}.`, body: "The approved version is unchanged. The new version needs approval again." } : null);
  };
  const edit = (fn: (v: number) => Promise<PrdEditResponse>) => run("edit", () => fn(doc!.version), applyEdit);
  const generate = (supersede: boolean) => run("generate", () => prdApi.generate(pid, supersede), (s) => { setOverride(s); setViewing(null); }, true);
  const startLabel = state.status === "not_started" ? "Generate PRD" : state.status === "failed" ? "Retry generating PRD" : "Regenerate PRD";

  const allReqIds = content ? [...content.functional_requirements.map((r) => r.id), ...content.non_functional_requirements.map((r) => r.id)] : [];

  return (
    <div className="max-w-4xl space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Product Requirements Document (PRD)</h1>
        <p className="mt-0.5 text-slate-600">Structured user stories, functional and non-functional requirements, testable acceptance criteria, and MVP boundaries built from your approved Strategy.</p>
        <div className="mt-2 flex flex-wrap items-center gap-1.5" aria-label="PRD status">
          <Badge tone={STATUS[(doc?.status ?? state.status) as keyof typeof STATUS].tone}>{STATUS[(doc?.status ?? state.status) as keyof typeof STATUS].label}</Badge>
          {doc && <Badge>Version {doc.version}</Badge>}
          <Badge tone={state.lifecycle.status === "complete" ? "success" : "neutral"}>Product stage: {state.lifecycle.status.replace("_", " ")}</Badge>
          {state.approved_version !== null && <Badge tone="success">Approved version: {state.approved_version}</Badge>}
        </div>
      </header>

      <Alert tone="warning" title="Proposed vs approved requirements">
        <ul className="list-disc pl-5">{state.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </Alert>
      {notice && <Alert tone={notice.tone} title={notice.title}>{notice.body}</Alert>}
      {state.status === "failed" && state.last_error && !notice && <Alert tone="error" title="The last attempt failed">{state.last_error} Nothing was changed.</Alert>}

      {viewing && (
        <Alert tone="info" title={`Viewing version ${viewing} (read-only)`}>
          <Button size="sm" onClick={() => setViewing(null)}>Back to the current PRD</Button>
        </Alert>
      )}

      {!doc && !viewing && (
        <section className="rounded-lg border border-slate-200 bg-white p-5">
          {!state.strategy_ready ? (
            <>
              <h2 className="font-semibold">Approve Product Strategy first</h2>
              <p className="mt-1 text-slate-600">PRD generation requires an approved Product Strategy with no unapproved Strategy draft open.</p>
              <Link to={`/projects/${pid}/strategy`} className="mt-4 inline-flex h-9 items-center rounded-md border border-slate-300 bg-white px-3.5 text-sm font-medium hover:bg-slate-50">Go to Strategy</Link>
            </>
          ) : (
            <>
              <h2 className="font-semibold">No PRD yet</h2>
              <p className="mt-1 text-slate-600">WebForge will generate a structured PRD from your approved Strategy v{state.approved_strategy_version}.</p>
              <div className="mt-4">
                <Button variant="primary" loading={busy === "generate"} disabled={!!busy || !state.can_generate} onClick={() => void generate(false)}>
                  {busy === "generate" ? "Generating…" : startLabel}
                </Button>
              </div>
            </>
          )}
        </section>
      )}

      {doc && content && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {canEdit && doc.status === "approved" && (
              <p className="text-xs text-slate-600">This version is approved and immutable. Editing creates version {(state.history[0]?.version ?? doc.version) + 1} as a new draft.</p>
            )}
            {!readOnly && doc.status === "draft" && (
              <Button variant="primary" disabled={!!busy || !state.can_submit} loading={busy === "submit"} onClick={() => void run("submit", () => prdApi.submit(pid, doc.version, hash), setOverride)}>
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
                {busy === "generate" ? "Generating…" : "Regenerate PRD"}
              </Button>
            )}
            {canEdit && doc.proposed_count > 0 && (
              <Button size="sm" disabled={!!busy} onClick={() => void edit((v) => prdApi.setRequirementStatus(pid, v, hash, allReqIds, "approved"))}>
                Approve all requirements
              </Button>
            )}
          </div>

          {doc.status === "approved" && (
            <Alert tone="success" title={`Version ${doc.version} approved${doc.approved_at ? ` on ${formatDateTime(doc.approved_at)}` : ""}`}>
              {doc.acknowledged_unverified ? "Approved with acknowledged proposed/unlinked requirements. " : ""}{doc.approval_note}
            </Alert>
          )}
          {doc.warnings.length > 0 && !readOnly && (
            <Alert tone="warning" title="PRD review items">
              <ul className="list-disc pl-5">{doc.warnings.map((w) => <li key={w.code}>{w.message}</li>)}</ul>
            </Alert>
          )}

          <section aria-labelledby="prd-overview-h" className="space-y-2 rounded-lg border border-slate-200 bg-white p-4">
            <h2 id="prd-overview-h" className="text-base font-semibold">Problem statement & target users</h2>
            <p className="text-xs text-slate-500">Based on approved Strategy v{content.strategy_basis.strategy_version}</p>
            <p className="text-sm">{content.problem_statement}</p>
            <div>
              <h3 className="text-xs font-medium text-slate-500">Target users</h3>
              <ul className="mt-1 list-disc pl-5 text-sm">{content.target_users.map((u) => <li key={u}>{u}</li>)}</ul>
            </div>
          </section>

          <section aria-labelledby="prd-stories-h" className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 id="prd-stories-h" className="mb-2 text-base font-semibold">User stories</h2>
            <ul className="space-y-2 text-sm">
              {content.user_stories.map((s) => (
                <li key={s.id} className="rounded border border-slate-200 p-2.5">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge>{s.id}</Badge>
                    <Badge tone={PRIORITY_LABELS[s.priority].tone}>{PRIORITY_LABELS[s.priority].label}</Badge>
                    {s.source_refs.length > 0 && <span className="text-xs text-slate-500">Refs: {s.source_refs.join(", ")}</span>}
                  </div>
                  <p className="mt-1">As a <strong>{s.persona}</strong>, I want to {s.action} so that {s.benefit}.</p>
                </li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="prd-fr-h" className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <h2 id="prd-fr-h" className="text-base font-semibold">Functional requirements</h2>
              {canEdit && <Button size="sm" disabled={!!busy} onClick={() => setModal({ kind: "fr" })}>Add functional requirement</Button>}
            </div>
            <ul className="space-y-2">
              {content.functional_requirements.map((r) => (
                <li key={r.id} className="rounded-lg border border-slate-200 bg-white p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge>{r.id}</Badge>
                      <span className="font-semibold">{r.title}</span>
                      <Badge tone={PRIORITY_LABELS[r.priority].tone}>{PRIORITY_LABELS[r.priority].label}</Badge>
                      <Badge tone={BOUNDARY_LABELS[r.mvp_boundary].tone}>{BOUNDARY_LABELS[r.mvp_boundary].label}</Badge>
                      <Badge tone={r.status === "approved" ? "success" : "warning"}>{r.status === "approved" ? "User-approved" : "Proposed"}</Badge>
                      {r.unlinked && <Badge tone="warning">Unlinked</Badge>}
                    </div>
                    {canEdit && (
                      <div className="flex gap-1">
                        <Button size="sm" disabled={!!busy} onClick={() => void edit((v) => prdApi.setRequirementStatus(pid, v, hash, [r.id], r.status === "approved" ? "proposed" : "approved"))}>
                          {r.status === "approved" ? "Mark proposed" : `Approve ${r.id}`}
                        </Button>
                        <Button size="sm" disabled={!!busy} onClick={() => setModal({ kind: "fr", req: r })} aria-label={`Edit ${r.id}`}>Edit</Button>
                        <Button size="sm" variant="ghost" className="text-red-700" disabled={!!busy} onClick={() => setModal({ kind: "delete-fr", req: r })} aria-label={`Delete ${r.id}`}>Delete</Button>
                      </div>
                    )}
                  </div>
                  <p className="mt-1.5 text-sm">{r.description}</p>
                  <div className="mt-2">
                    <h3 className="text-xs font-medium text-slate-600">Testable acceptance criteria</h3>
                    <ul className="mt-0.5 list-disc pl-5 text-xs text-slate-700">{r.acceptance_criteria.map((ac) => <li key={ac}>{ac}</li>)}</ul>
                  </div>
                  {r.edge_cases.length > 0 && (
                    <div className="mt-1.5">
                      <h3 className="text-xs font-medium text-slate-600">Edge cases</h3>
                      <ul className="mt-0.5 list-disc pl-5 text-xs text-slate-600">{r.edge_cases.map((ec) => <li key={ec}>{ec}</li>)}</ul>
                    </div>
                  )}
                  <p className="mt-1.5 text-xs text-slate-500">
                    {r.source_refs.length > 0 ? `Strategy refs: ${r.source_refs.join(", ")}` : "No strategy ref linked"}
                    {r.user_story_ids.length > 0 ? ` · Stories: ${r.user_story_ids.join(", ")}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="prd-nfr-h" className="space-y-2 rounded-lg border border-slate-200 bg-white p-4">
            <h2 id="prd-nfr-h" className="text-base font-semibold">Non-functional requirements</h2>
            {content.non_functional_requirements.length === 0 ? <p className="text-sm text-slate-600">None recorded.</p> : (
              <ul className="space-y-2">
                {content.non_functional_requirements.map((nfr) => (
                  <li key={nfr.id} className="rounded border border-slate-200 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge>{nfr.id}</Badge>
                        <span className="font-medium">{nfr.title}</span>
                        <Badge>{nfr.category}</Badge>
                        <Badge tone={PRIORITY_LABELS[nfr.priority].tone}>{PRIORITY_LABELS[nfr.priority].label}</Badge>
                        <Badge tone={nfr.status === "approved" ? "success" : "warning"}>{nfr.status === "approved" ? "User-approved" : "Proposed"}</Badge>
                      </div>
                      {canEdit && (
                        <Button size="sm" disabled={!!busy} onClick={() => void edit((v) => prdApi.setRequirementStatus(pid, v, hash, [nfr.id], nfr.status === "approved" ? "proposed" : "approved"))}>
                          {nfr.status === "approved" ? "Mark proposed" : `Approve ${nfr.id}`}
                        </Button>
                      )}
                    </div>
                    <p className="mt-1 text-sm">{nfr.description}</p>
                    <ul className="mt-1 list-disc pl-5 text-xs text-slate-700">{nfr.acceptance_criteria.map((ac) => <li key={ac}>{ac}</li>)}</ul>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="prd-scope-h" className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 id="prd-scope-h" className="mb-2 text-base font-semibold">MVP boundaries, dependencies, risks & open questions</h2>
            <div className="grid gap-3 sm:grid-cols-3 text-sm">
              <div><h3 className="text-xs font-medium text-slate-500">In MVP</h3><ul className="mt-1 list-disc pl-5">{content.mvp_boundaries.in_mvp.map((x) => <li key={x}>{x}</li>)}</ul></div>
              <div><h3 className="text-xs font-medium text-slate-500">Post-MVP</h3><ul className="mt-1 list-disc pl-5">{content.mvp_boundaries.post_mvp.map((x) => <li key={x}>{x}</li>)}</ul></div>
              <div><h3 className="text-xs font-medium text-slate-500">Out of scope</h3><ul className="mt-1 list-disc pl-5">{content.mvp_boundaries.out_of_scope.map((x) => <li key={x}>{x}</li>)}</ul></div>
            </div>
            {content.risks.length > 0 && (
              <div className="mt-3 text-sm"><h3 className="text-xs font-medium text-slate-500">Risks</h3><ul className="mt-1 list-disc pl-5">{content.risks.map((rk) => <li key={rk.id}>{rk.risk} — {rk.mitigation}</li>)}</ul></div>
            )}
            {content.open_questions.length > 0 && (
              <div className="mt-3 text-sm"><h3 className="text-xs font-medium text-slate-500">Open questions</h3><ul className="mt-1 list-disc pl-5">{content.open_questions.map((q) => <li key={q.id}>{q.question}</li>)}</ul></div>
            )}
          </section>
        </>
      )}

      <section aria-labelledby="prd-history-h" className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 id="prd-history-h" className="mb-2 text-base font-semibold">PRD history</h2>
        {state.history.length === 0 ? <p className="text-slate-600">No versions yet.</p> : (
          <ul className="space-y-2">
            {state.history.map((h) => (
              <li key={h.version} className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="font-medium">Version {h.version}</span> <Badge tone={STATUS[h.status].tone}>{STATUS[h.status].label}</Badge>
                  <p className="text-xs text-slate-500">{h.requirement_count} requirements ({h.approved_requirement_count} approved · {h.proposed_requirement_count} proposed)</p>
                </div>
                <Button size="sm" disabled={viewing === h.version} onClick={() => setViewing(h.version)} aria-label={`View version ${h.version}`}>View</Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {modal?.kind === "fr" && doc && content && (
        <FunctionalReqDialog req={modal.req} availableRefs={content.strategy_basis.available_refs.map((r) => r.ref_id)} onClose={() => setModal(null)}
          onSubmit={(b) => act(() => (modal.req ? prdApi.patchFunctionalReq(pid, doc.version, hash, modal.req.id, b) : prdApi.addFunctionalReq(pid, doc.version, hash, b)), applyEdit)} />
      )}
      {modal?.kind === "delete-fr" && doc && (
        <ConfirmDialog title="Delete requirement?" confirmLabel="Delete requirement" onClose={() => setModal(null)}
          body={<p>“{modal.req.id}: {modal.req.title}” will be removed from this PRD version.</p>}
          onConfirm={() => act(() => prdApi.deleteFunctionalReq(pid, doc.version, hash, modal.req.id), applyEdit)} />
      )}
      {modal?.kind === "regenerate" && (
        <ConfirmDialog title="Regenerate PRD?" confirmLabel="Regenerate" onClose={() => setModal(null)}
          body={<p>A new PRD version will be generated. The current draft stays in history as superseded.</p>}
          onConfirm={() => act(() => prdApi.generate(pid, true), (s) => { setOverride(s); setViewing(null); })} />
      )}
      {modal?.kind === "approve" && doc && (
        <PrdApproveDialog proposed={doc.proposed_count} unlinked={doc.unlinked_count} onClose={() => setModal(null)}
          onSubmit={(ack, note) => act(() => prdApi.approve(pid, doc.version, hash, ack, note), setOverride)} />
      )}
    </div>
  );
}

function FunctionalReqDialog({ req, availableRefs, onSubmit, onClose }: { req?: FunctionalRequirement; availableRefs: string[]; onSubmit: (b: FunctionalReqBody) => Promise<void>; onClose: () => void }) {
  const [title, setTitle] = useState(req?.title ?? "");
  const [description, setDescription] = useState(req?.description ?? "");
  const [priority, setPriority] = useState<Priority>(req?.priority ?? "must_have");
  const [boundary, setBoundary] = useState<MvpBoundary>(req?.mvp_boundary ?? "in_mvp");
  const [criteriaText, setCriteriaText] = useState((req?.acceptance_criteria ?? []).join("\n"));
  const [edgeText, setEdgeText] = useState((req?.edge_cases ?? []).join("\n"));
  const [refs, setRefs] = useState<string[]>(req?.source_refs ?? (availableRefs[0] ? [availableRefs[0]] : []));
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  return (
    <Dialog title={req ? `Edit ${req.id}` : "Add functional requirement"} onClose={onClose}>
      <form noValidate className="space-y-3" onSubmit={async (e) => {
        e.preventDefault(); setBusy(true); setErrors([]);
        try {
          await onSubmit({
            title: title.trim(),
            description: description.trim(),
            priority,
            mvp_boundary: boundary,
            status: req?.status ?? "proposed",
            user_story_ids: req?.user_story_ids ?? [],
            source_refs: refs,
            acceptance_criteria: criteriaText.split("\n").map((s) => s.trim()).filter(Boolean),
            edge_cases: edgeText.split("\n").map((s) => s.trim()).filter(Boolean),
            dependencies: req?.dependencies ?? [],
          });
        } catch (err) { setErrors(messagesOf(err)); setBusy(false); }
      }}>
        {errors.length > 0 && <Alert tone="error">{errors.map((m) => <p key={m}>{m}</p>)}</Alert>}
        <TextField label="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <TextAreaField label="Description" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
        <div className="grid grid-cols-2 gap-2">
          <label className="block"><span className="mb-1 block text-xs font-medium text-slate-700">Priority</span>
            <select value={priority} onChange={(e) => setPriority(e.target.value as Priority)} className="h-9 w-full rounded-md border border-slate-300 bg-white px-2 text-sm">
              {(Object.keys(PRIORITY_LABELS) as Priority[]).map((p) => <option key={p} value={p}>{PRIORITY_LABELS[p].label}</option>)}
            </select>
          </label>
          <label className="block"><span className="mb-1 block text-xs font-medium text-slate-700">MVP boundary</span>
            <select value={boundary} onChange={(e) => setBoundary(e.target.value as MvpBoundary)} className="h-9 w-full rounded-md border border-slate-300 bg-white px-2 text-sm">
              {(Object.keys(BOUNDARY_LABELS) as MvpBoundary[]).map((b) => <option key={b} value={b}>{BOUNDARY_LABELS[b].label}</option>)}
            </select>
          </label>
        </div>
        <TextAreaField label="Acceptance criteria (one per line, specific and testable)" rows={3} value={criteriaText} onChange={(e) => setCriteriaText(e.target.value)} />
        <TextAreaField label="Edge cases (optional, one per line)" rows={2} value={edgeText} onChange={(e) => setEdgeText(e.target.value)} />
        <div className="flex justify-end gap-2"><Button onClick={onClose} disabled={busy}>Cancel</Button><Button type="submit" variant="primary" loading={busy}>{req ? "Save requirement" : "Add requirement"}</Button></div>
      </form>
    </Dialog>
  );
}

function PrdApproveDialog({ proposed, unlinked, onSubmit, onClose }: { proposed: number; unlinked: number; onSubmit: (ack: boolean, note: string) => Promise<void>; onClose: () => void }) {
  const [ack, setAck] = useState(false);
  const [note, setNote] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const needsAck = proposed > 0 || unlinked > 0;
  return (
    <Dialog title="Approve this PRD version" onClose={onClose}>
      <form noValidate className="space-y-3" onSubmit={async (e) => { e.preventDefault(); setBusy(true); setErrors([]); try { await onSubmit(ack, note); } catch (err) { setErrors(messagesOf(err)); setBusy(false); } }}>
        {errors.length > 0 && <Alert tone="error">{errors.map((m) => <p key={m}>{m}</p>)}</Alert>}
        <p>Approving records this exact PRD version in your Project Brain and completes the Product lifecycle stage.</p>
        {needsAck && (
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-0.5 h-4 w-4" checked={ack} onChange={(e) => setAck(e.target.checked)} />
            <span>I understand that {proposed} requirement(s) are still marked proposed and {unlinked} requirement(s) are unlinked.</span>
          </label>
        )}
        <TextAreaField label="Approval note (optional)" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        <div className="flex justify-end gap-2">
          <Button onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" variant="primary" loading={busy} disabled={needsAck && !ack}>Approve PRD</Button>
        </div>
      </form>
    </Dialog>
  );
}
