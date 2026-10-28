import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorState, LoadingState } from "../components/feedback/States";
import { Alert } from "../components/ui/Alert";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { researchApi } from "../features/research/api";
import { ApproveDialog, ConfirmDialog, FindingDialog, SourceDialog, messagesOf } from "../features/research/Dialogs";
import { FindingCard } from "../features/research/FindingCard";
import { EVIDENCE, EVIDENCE_ORDER, STATUS, TOPIC_ORDER, TOPICS } from "../features/research/labels";
import { BriefPanel, HistoryPanel, SourcesPanel } from "../features/research/Panels";
import { ApiError } from "../lib/api";
import { formatDateTime } from "../lib/utils";
import { useAsync } from "../lib/useAsync";
import type { EditResponse, Finding, Report, ResearchState, Source } from "../types/research";
import { useProject } from "./ProjectLayout";

type Notice = { tone: "error" | "warning" | "success"; title: string; body?: string };
type Modal = { kind: "finding"; finding?: Finding } | { kind: "source"; source?: Source } | { kind: "delete-finding"; finding: Finding } | { kind: "delete-source"; source: Source }
  | { kind: "regenerate" } | { kind: "approve" } | null;

function describe(e: unknown): Notice {
  if (e instanceof ApiError) {
    if (e.status === 503) return { tone: "warning", title: "AI analysis is not configured yet.", body: "Nothing was changed. Configure an AI provider to generate research." };
    if (e.status === 502) return { tone: "error", title: "WebForge couldn't produce a valid research report.", body: `${e.message} Nothing was changed. You can try again.` };
    return { tone: "error", title: e.message };
  }
  return { tone: "error", title: "Something went wrong." };
}

export default function ResearchPage() {
  const { project } = useProject();
  const pid = project.id;
  const load = useAsync(() => researchApi.get(pid), [pid]);
  const [override, setOverride] = useState<ResearchState>();
  const [viewing, setViewing] = useState<number | null>(null);
  const viewed = useAsync(() => (viewing ? researchApi.report(pid, viewing) : Promise.resolve(null)), [pid, viewing]);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef<string | null>(null); // synchronous guard against double submits
  const [modal, setModal] = useState<Modal>(null);
  const state = override ?? load.data;

  async function run<T>(key: string, fn: () => Promise<T>, onDone: (r: T) => void, refreshOnError = false) {
    if (busyRef.current) return;
    busyRef.current = key; setBusy(key); setNotice(null);
    try { onDone(await fn()); }
    catch (e) {
      setNotice(describe(e));
      if (refreshOnError || (e instanceof ApiError && e.kind === "conflict")) researchApi.get(pid).then(setOverride).catch(() => undefined);
    } finally { busyRef.current = null; setBusy(null); }
  }
  /** Dialog actions throw so the dialog can show validation messages; the busy guard still applies. */
  async function act<T>(fn: () => Promise<T>, onDone: (r: T) => void) {
    if (busyRef.current) throw new Error("Another action is in progress.");
    busyRef.current = "dialog"; setBusy("dialog");
    try { onDone(await fn()); setModal(null); }
    catch (e) { if (e instanceof ApiError && e.kind === "conflict") researchApi.get(pid).then(setOverride).catch(() => undefined); throw e; }
    finally { busyRef.current = null; setBusy(null); }
  }

  if (load.loading && !state) return <LoadingState label="Loading research…" />;
  if (!state) return <ErrorState message={load.error?.message ?? "We couldn't load research."} onRetry={load.reload} />;

  const report: Report | null = viewing ? (viewed.data ?? null) : state.current;
  const readOnly = !!viewing;
  const canEdit = !readOnly && !!report && ["draft", "in_review", "approved"].includes(report.status);
  const content = report?.content ?? null;
  const hash = report?.content_hash ?? "";
  const applyEdit = (r: EditResponse) => {
    setOverride(r.state);
    setNotice(r.report.version !== report?.version ? { tone: "success", title: `Saved as a new draft, version ${r.report.version}.`, body: "The approved version is unchanged. The new version needs approval again." } : null);
  };
  const edit = (fn: (v: number) => Promise<EditResponse>) => run("edit", () => fn(report!.version), applyEdit);
  const generate = (supersede: boolean) => run("generate", () => researchApi.generate(pid, supersede), (s) => { setOverride(s); setViewing(null); }, true);
  const startLabel = state.status === "not_started" ? "Start preliminary research" : state.status === "failed" ? "Retry generating the report" : "Regenerate report";
  const overviewPath = `/projects/${pid}/overview`;

  return (
    <div className="max-w-4xl space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Research</h1>
        <p className="mt-0.5 text-slate-600">A structured, editable research report built from your Project Brain and Discovery answers.</p>
        <div className="mt-2 flex flex-wrap items-center gap-1.5" aria-label="Research status">
          <Badge tone={STATUS[(report?.status ?? state.status) as keyof typeof STATUS].tone}>{STATUS[(report?.status ?? state.status) as keyof typeof STATUS].label}</Badge>
          {report && <Badge>Version {report.version}</Badge>}
          <Badge tone={state.lifecycle.status === "complete" ? "success" : "neutral"}>Research stage: {state.lifecycle.status.replace("_", " ")}</Badge>
          {state.approved_version !== null && <Badge tone="success">Approved version: {state.approved_version}</Badge>}
        </div>
      </header>

      <Alert tone="warning" title="Preliminary research: no web research was performed">
        <ul className="list-disc pl-5">{state.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </Alert>
      {notice && <Alert tone={notice.tone} title={notice.title}>{notice.body}</Alert>}
      {state.status === "failed" && state.last_error && !notice && <Alert tone="error" title="The last attempt failed">{state.last_error} Nothing was changed.</Alert>}

      {viewing && (
        <Alert tone="info" title={`Viewing version ${viewing} (read-only)`}>
          <Button size="sm" onClick={() => setViewing(null)}>Back to the current report</Button>
        </Alert>
      )}
      {viewing && viewed.loading && <LoadingState label="Loading version…" />}
      {viewing && viewed.error && <ErrorState message={viewed.error.message} onRetry={viewed.reload} />}

      {!report && !viewing && (
        <section className="rounded-lg border border-slate-200 bg-white p-5">
          {state.idea_ready ? (
            <>
              <h2 className="font-semibold">No research report yet</h2>
              <p className="mt-1 text-slate-600">WebForge will turn your idea and confirmed answers into research objectives, questions and clearly labeled hypotheses. It will not invent sources or statistics.</p>
              <div className="mt-4"><Button variant="primary" loading={busy === "generate"} disabled={!!busy || !state.can_generate} onClick={() => void generate(false)}>{busy === "generate" ? "Generating…" : startLabel}</Button></div>
            </>
          ) : (
            <>
              <h2 className="font-semibold">Describe your idea first</h2>
              <p className="mt-1 text-slate-600">Research builds on your product idea, and none has been analyzed yet.</p>
              <Link to={overviewPath} className="mt-4 inline-flex h-9 items-center rounded-md border border-slate-300 bg-white px-3.5 text-sm font-medium hover:bg-slate-50">Go to Overview</Link>
            </>
          )}
        </section>
      )}
      {!report && !viewing && state.brief_preview && <BriefPanel brief={state.brief_preview} preview />}

      {report && content && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {canEdit && report.status === "approved" && <p className="text-xs text-slate-600">This version is approved and cannot change. Editing creates version {(state.history[0]?.version ?? report.version) + 1} as a new draft.</p>}
            {!readOnly && report.status === "draft" && <Button variant="primary" disabled={!!busy || !state.can_submit} loading={busy === "submit"} onClick={() => void run("submit", () => researchApi.submit(pid, report.version, hash), setOverride)}>Submit for review</Button>}
            {!readOnly && report.status === "in_review" && <Button variant="primary" disabled={!!busy || !state.can_approve} onClick={() => setModal({ kind: "approve" })}>Approve version {report.version}</Button>}
            {!readOnly && <Button disabled={!!busy || !state.can_generate} loading={busy === "generate"} onClick={() => (state.needs_supersede ? setModal({ kind: "regenerate" }) : void generate(false))}>{busy === "generate" ? "Generating…" : "Regenerate report"}</Button>}
          </div>
          {!readOnly && report.status === "in_review" && <Alert tone="info">Submitted for review. Editing returns it to draft; approval applies to exactly this version.</Alert>}
          {report.status === "approved" && <Alert tone="success" title={`Version ${report.version} approved${report.approved_at ? ` on ${formatDateTime(report.approved_at)}` : ""}`}>{report.acknowledged_unverified ? "Approved with acknowledged unverified findings. " : ""}{report.approval_note}</Alert>}
          {report.warnings.length > 0 && !readOnly && <Alert tone="warning" title="What remains unverified"><ul className="list-disc pl-5">{report.warnings.map((w) => <li key={w.code}>{w.message}</li>)}</ul></Alert>}

          <BriefPanel brief={content.brief} />

          <section aria-labelledby="findings-h" className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 id="findings-h" className="text-base font-semibold">Findings</h2>
              {canEdit && <Button size="sm" disabled={!!busy} onClick={() => setModal({ kind: "finding" })}>Add finding</Button>}
            </div>
            <details className="rounded-md border border-slate-200 bg-white p-3"><summary className="cursor-pointer text-sm font-medium">What the evidence labels mean</summary>
              <dl className="mt-2 space-y-1">{EVIDENCE_ORDER.map((e) => <div key={e}><dt className="font-medium">{EVIDENCE[e].label}</dt><dd className="text-slate-600">{EVIDENCE[e].help}</dd></div>)}</dl></details>
            {content.findings.length === 0 && <p className="text-slate-600">This report has no findings.</p>}
            {TOPIC_ORDER.filter((t) => content.findings.some((f) => f.topic === t)).map((t) => (
              <div key={t}><h3 className="mb-1.5 text-sm font-semibold text-slate-700">{TOPICS[t]}</h3>
                <ul className="space-y-2">{content.findings.filter((f) => f.topic === t).map((f) => (
                  <FindingCard key={f.id} f={f} sources={content.sources} canEdit={canEdit} busy={!!busy}
                    onEdit={() => setModal({ kind: "finding", finding: f })} onDelete={() => setModal({ kind: "delete-finding", finding: f })}
                    onFollowUp={() => void edit((v) => researchApi.followUp(pid, v, hash, [f.id], !f.follow_up))} />))}</ul></div>
            ))}
          </section>

          <SourcesPanel sources={content.sources} canEdit={canEdit} busy={!!busy} onAdd={() => setModal({ kind: "source" })} onEdit={(s) => setModal({ kind: "source", source: s })} onDelete={(s) => setModal({ kind: "delete-source", source: s })} />

          <section aria-labelledby="open-h" className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 id="open-h" className="mb-2 text-base font-semibold">Unresolved questions</h2>
            {content.unresolved_questions.length === 0 ? <p className="text-slate-600">None recorded.</p> : <ul className="list-disc space-y-0.5 pl-5">{content.unresolved_questions.map((q) => <li key={q.id}>{q.question}</li>)}</ul>}
          </section>
        </>
      )}

      <HistoryPanel history={state.history} viewing={viewing} onView={setViewing} />

      {modal?.kind === "finding" && report && content && (
        <FindingDialog finding={modal.finding} sources={content.sources} onClose={() => setModal(null)}
          onSubmit={(b) => act(() => (modal.finding ? researchApi.patchFinding(pid, report.version, hash, modal.finding.id, b) : researchApi.addFinding(pid, report.version, hash, b)), applyEdit)} />
      )}
      {modal?.kind === "source" && report && (
        <SourceDialog source={modal.source} onClose={() => setModal(null)}
          onSubmit={(b) => act(() => (modal.source ? researchApi.patchSource(pid, report.version, hash, modal.source.id, b) : researchApi.addSource(pid, report.version, hash, b)), applyEdit)} />
      )}
      {modal?.kind === "delete-finding" && report && (
        <ConfirmDialog title="Delete finding?" confirmLabel="Delete finding" onClose={() => setModal(null)} body={<p className="[overflow-wrap:anywhere]">“{modal.finding.statement}” will be removed from this version.</p>}
          onConfirm={() => act(() => researchApi.deleteFinding(pid, report.version, hash, modal.finding.id), applyEdit)} />
      )}
      {modal?.kind === "delete-source" && report && (
        <ConfirmDialog title="Delete source?" confirmLabel="Delete source" onClose={() => setModal(null)} body={<p className="[overflow-wrap:anywhere]">“{modal.source.title}” will be removed. Findings that cite it must drop the citation first.</p>}
          onConfirm={() => act(() => researchApi.deleteSource(pid, report.version, hash, modal.source.id), applyEdit)} />
      )}
      {modal?.kind === "regenerate" && (
        <ConfirmDialog title="Regenerate the report?" confirmLabel="Regenerate" onClose={() => setModal(null)}
          body={<p>A new version will be generated. The current draft stays in the history as superseded. If generation fails, nothing changes.</p>}
          onConfirm={() => act(() => researchApi.generate(pid, true), (s) => { setOverride(s); setViewing(null); })} />
      )}
      {modal?.kind === "approve" && report && (
        <ApproveDialog unverified={report.unverified_count} onClose={() => setModal(null)}
          onSubmit={(ack, note) => act(() => researchApi.approve(pid, report.version, hash, ack, note), setOverride)} />
      )}
    </div>
  );
}
