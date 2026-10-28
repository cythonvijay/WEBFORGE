import { useState } from "react";
import { Link } from "react-router-dom";
import { Alert } from "../../components/ui/Alert";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { TextAreaField } from "../../components/ui/Fields";
import { formatDateTime } from "../../lib/utils";
import type { UxArtifactState, UxDocument } from "../../types/ux";
import { ConfirmDialog, messagesOf } from "../research/Dialogs";
import { STATUS } from "../research/labels";

export type UxNotice = { tone: "error" | "warning" | "success"; title: string; body?: string };

export function UxWorkspaceShell<C>({
  projectId,
  title,
  subtitle,
  state,
  doc,
  viewing,
  onViewVersion,
  busy,
  notice,
  onGenerate,
  onSubmit,
  onApprove,
  emptyExtra,
  children,
}: {
  projectId: string;
  title: string;
  subtitle: string;
  state: UxArtifactState<C>;
  doc: UxDocument<C> | null;
  viewing: number | null;
  onViewVersion: (v: number | null) => void;
  busy: string | null;
  notice: UxNotice | null;
  onGenerate: (supersede: boolean) => void;
  onSubmit: () => void;
  onApprove: (ack: boolean, note: string) => Promise<void>;
  emptyExtra?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [modal, setModal] = useState<"regenerate" | "approve" | null>(null);
  const readOnly = viewing !== null;
  const upVers = state.prerequisites.upstream_versions;
  const startLabel = state.status === "not_started" ? `Generate ${title}` : state.status === "failed" ? `Retry generating ${title}` : `Regenerate ${title}`;

  return (
    <div className="max-w-4xl space-y-4">
      <header>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-xl font-semibold">{title}</h1>
          <nav aria-label="UX workspaces" className="flex flex-wrap gap-1.5 text-xs">
            <Link to={`/projects/${projectId}/personas`} className="rounded border border-slate-200 bg-white px-2.5 py-1 hover:bg-slate-50">1. Personas</Link>
            <Link to={`/projects/${projectId}/journeys`} className="rounded border border-slate-200 bg-white px-2.5 py-1 hover:bg-slate-50">2. Journeys</Link>
            <Link to={`/projects/${projectId}/ia`} className="rounded border border-slate-200 bg-white px-2.5 py-1 hover:bg-slate-50">3. IA</Link>
            <Link to={`/projects/${projectId}/wireframes`} className="rounded border border-slate-200 bg-white px-2.5 py-1 hover:bg-slate-50">4. Wireframes</Link>
            <Link to={`/projects/${projectId}/ux-review`} className="rounded border border-slate-200 bg-white px-2.5 py-1 hover:bg-slate-50">5. UX Review</Link>
          </nav>
        </div>
        <p className="mt-0.5 text-slate-600">{subtitle}</p>
        <div className="mt-2 flex flex-wrap items-center gap-1.5" aria-label={`${title} status`}>
          <Badge tone={STATUS[(doc?.status ?? state.status) as keyof typeof STATUS].tone}>
            {STATUS[(doc?.status ?? state.status) as keyof typeof STATUS].label}
          </Badge>
          {doc && <Badge>Version {doc.version}</Badge>}
          {doc?.is_stale && <Badge tone="warning">Stale upstream</Badge>}
          <Badge tone={state.lifecycle.status === "complete" ? "success" : "neutral"}>
            UX stage: {state.lifecycle.status.replace("_", " ")}
          </Badge>
          {state.approved_version !== null && <Badge tone="success">Approved version: {state.approved_version}</Badge>}
          {upVers.prd && <Badge tone="info">PRD v{upVers.prd} · Strategy v{upVers.strategy} · Research v{upVers.research}</Badge>}
        </div>
      </header>

      <Alert tone="warning" title="Evidence & provenance notice">
        <ul className="list-disc pl-5">{state.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </Alert>

      {notice && <Alert tone={notice.tone} title={notice.title}>{notice.body}</Alert>}
      {state.status === "failed" && state.last_error && !notice && (
        <Alert tone="error" title="The last attempt failed">{state.last_error} Nothing was changed.</Alert>
      )}

      {!state.prerequisites.ready && (
        <section aria-label="Prerequisite gates" className="rounded-lg border border-amber-300 bg-amber-50 p-4 space-y-2">
          <h2 className="font-semibold text-amber-900">Upstream prerequisites required</h2>
          <p className="text-sm text-amber-800">Complete or update the following upstream artifacts before generating or approving {title}:</p>
          <ul className="space-y-2">
            {state.prerequisites.missing.map((m) => (
              <li key={m.artifact} className="flex flex-wrap items-center justify-between gap-2 rounded border border-amber-200 bg-white p-2.5 text-sm">
                <span><strong>{m.label}:</strong> {m.message}</span>
                <Link to={m.workspace_path} className="inline-flex h-8 items-center rounded-md border border-slate-300 bg-white px-3 text-xs font-medium hover:bg-slate-50">
                  Go to {m.label}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {viewing !== null && (
        <Alert tone="info" title={`Viewing version ${viewing} (read-only)`}>
          <Button size="sm" onClick={() => onViewVersion(null)}>Back to current version</Button>
        </Alert>
      )}

      {!doc && viewing === null && state.prerequisites.ready && (
        <section className="rounded-lg border border-slate-200 bg-white p-5 space-y-3">
          <h2 className="font-semibold">No {title.toLowerCase()} yet</h2>
          <p className="text-sm text-slate-600">{state.next_step.label}</p>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" loading={busy === "generate"} disabled={!!busy || !state.can_generate} onClick={() => onGenerate(false)}>
              {busy === "generate" ? "Generating…" : startLabel}
            </Button>
            {emptyExtra}
          </div>
        </section>
      )}

      {doc && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {!readOnly && doc.status === "approved" && (
              <p className="text-xs text-slate-600">This version is approved and immutable. Editing creates version {(state.history[0]?.version ?? doc.version) + 1} as a new draft.</p>
            )}
            {!readOnly && doc.status === "draft" && (
              <Button variant="primary" disabled={!!busy || !state.can_submit} loading={busy === "submit"} onClick={onSubmit}>
                Submit for review
              </Button>
            )}
            {!readOnly && doc.status === "in_review" && (
              <Button variant="primary" disabled={!!busy || !state.can_approve} onClick={() => setModal("approve")}>
                Approve version {doc.version}
              </Button>
            )}
            {!readOnly && (
              <Button disabled={!!busy || !state.can_generate} loading={busy === "generate"} onClick={() => (state.needs_supersede ? setModal("regenerate") : onGenerate(false))}>
                {busy === "generate" ? "Generating…" : `Regenerate ${title}`}
              </Button>
            )}
            {doc.status === "approved" && !doc.is_stale && state.next_step.workspace_path && (
              <Link to={state.next_step.workspace_path} className="inline-flex h-9 items-center rounded-md border border-slate-300 bg-white px-3.5 text-sm font-medium hover:bg-slate-50">
                {state.next_step.label.replace(/^Approved\.\s*/, "")}
              </Link>
            )}
          </div>

          {doc.status === "approved" && (
            <Alert tone="success" title={`Version ${doc.version} approved${doc.approved_at ? ` on ${formatDateTime(doc.approved_at)}` : ""}`}>
              {doc.acknowledged_unverified ? "Approved with acknowledged hypotheses/open items. " : ""}{doc.approval_note}
            </Alert>
          )}
          {doc.warnings.length > 0 && !readOnly && (
            <Alert tone="warning" title="Review items & warnings">
              <ul className="list-disc pl-5">{doc.warnings.map((w, i) => <li key={`${w.code}-${i}`}>{w.message}</li>)}</ul>
            </Alert>
          )}

          {children}
        </>
      )}

      <section aria-labelledby="ux-history-h" className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 id="ux-history-h" className="mb-2 text-base font-semibold">Version history</h2>
        {state.history.length === 0 ? <p className="text-slate-600">No versions yet.</p> : (
          <ul className="space-y-2">
            {state.history.map((h) => (
              <li key={h.version} className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="font-medium">Version {h.version}</span> <Badge tone={STATUS[h.status].tone}>{STATUS[h.status].label}</Badge>
                  <p className="text-xs text-slate-500">{h.item_count} items · {h.created_via}</p>
                </div>
                <Button size="sm" disabled={viewing === h.version} onClick={() => onViewVersion(h.version)} aria-label={`View version ${h.version}`}>View</Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {modal === "regenerate" && (
        <ConfirmDialog title={`Regenerate ${title}?`} confirmLabel="Regenerate" onClose={() => setModal(null)}
          body={<p>A new version will be generated. The current draft stays in history as superseded.</p>}
          onConfirm={async () => { setModal(null); onGenerate(true); }} />
      )}
      {modal === "approve" && doc && (
        <UxApproveDialog title={`Approve ${title} version ${doc.version}`} unverified={doc.unverified_count} onClose={() => setModal(null)}
          onSubmit={async (ack, note) => { await onApprove(ack, note); setModal(null); }} />
      )}
    </div>
  );
}

function UxApproveDialog({ title, unverified, onSubmit, onClose }: { title: string; unverified: number; onSubmit: (ack: boolean, note: string) => Promise<void>; onClose: () => void }) {
  const [ack, setAck] = useState(false);
  const [note, setNote] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  return (
    <Dialog title={title} onClose={onClose}>
      <form noValidate className="space-y-3" onSubmit={async (e) => { e.preventDefault(); setBusy(true); setErrors([]); try { await onSubmit(ack, note); } catch (err) { setErrors(messagesOf(err)); setBusy(false); } }}>
        {errors.length > 0 && <Alert tone="error">{errors.map((m) => <p key={m}>{m}</p>)}</Alert>}
        <p>Approving locks this exact version by its content hash and records its provenance in your Project Brain.</p>
        {unverified > 0 && (
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-0.5 h-4 w-4" checked={ack} onChange={(e) => setAck(e.target.checked)} />
            <span>I understand that {unverified} item(s) contain unverified hypotheses, assumptions, or open questions.</span>
          </label>
        )}
        <TextAreaField label="Approval note (optional)" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        <div className="flex justify-end gap-2">
          <Button onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" variant="primary" loading={busy} disabled={unverified > 0 && !ack}>Approve version</Button>
        </div>
      </form>
    </Dialog>
  );
}
