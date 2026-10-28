import { useRef, useState } from "react";
import { ErrorState, LoadingState } from "../components/feedback/States";
import { Alert } from "../components/ui/Alert";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { TextAreaField } from "../components/ui/Fields";
import { messagesOf } from "../features/research/Dialogs";
import { UxWorkspaceShell, type UxNotice } from "../features/ux/UxWorkspaceShell";
import { uxApi } from "../features/ux/api";
import { ApiError } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import type { FindingSeverity, FindingStatus, UxArtifactState, UxDocument, UxEditResponse, UxReviewContent, UxReviewFinding } from "../types/ux";
import { useProject } from "./ProjectLayout";

const SEV_TONE: Record<FindingSeverity, "danger" | "warning" | "info" | "neutral"> = {
  critical: "danger",
  high: "warning",
  medium: "info",
  low: "neutral",
};

function describe(e: unknown): UxNotice {
  if (e instanceof ApiError) return { tone: "error", title: e.message };
  return { tone: "error", title: "Something went wrong." };
}

export default function UxReviewPage() {
  const { project } = useProject();
  const pid = project.id;
  const load = useAsync(() => uxApi.get<UxReviewContent>(pid, "ux_review"), [pid]);
  const [override, setOverride] = useState<UxArtifactState<UxReviewContent>>();
  const [viewing, setViewing] = useState<number | null>(null);
  const viewed = useAsync(() => (viewing ? uxApi.version<UxReviewContent>(pid, "ux_review", viewing) : Promise.resolve(null)), [pid, viewing]);
  const [notice, setNotice] = useState<UxNotice | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef<string | null>(null);
  const [resolving, setResolving] = useState<{ finding: UxReviewFinding; targetStatus: FindingStatus } | null>(null);
  const state = override ?? load.data;

  async function run<T>(key: string, fn: () => Promise<T>, onDone: (r: T) => void) {
    if (busyRef.current) return;
    busyRef.current = key; setBusy(key); setNotice(null);
    try { onDone(await fn()); }
    catch (e) { setNotice(describe(e)); }
    finally { busyRef.current = null; setBusy(null); }
  }

  async function act<T>(fn: () => Promise<T>, onDone: (r: T) => void) {
    if (busyRef.current) throw new Error("Another action is in progress.");
    busyRef.current = "dialog"; setBusy("dialog");
    try { onDone(await fn()); setResolving(null); }
    finally { busyRef.current = null; setBusy(null); }
  }

  if (load.loading && !state) return <LoadingState label="Loading UX review…" />;
  if (!state) return <ErrorState message={load.error?.message ?? "We couldn't load the UX review."} onRetry={load.reload} />;

  const doc: UxDocument<UxReviewContent> | null = viewing ? (viewed.data ?? null) : state.current;
  const content = doc?.content ?? null;
  const hash = doc?.content_hash ?? "";
  const canEdit = viewing === null && !!doc && ["draft", "in_review", "approved"].includes(doc.status);
  const applyEdit = (r: UxEditResponse<UxReviewContent>) => {
    setOverride(r.state);
    if (r.document.version !== doc?.version) setNotice({ tone: "success", title: `Saved as new draft version ${r.document.version}.` });
  };

  return (
    <UxWorkspaceShell
      projectId={pid}
      title="UX Review"
      subtitle="Deterministic cross-artifact coverage checks and AI design review across Personas, Journeys, IA, and Wireframes."
      state={state}
      doc={doc}
      viewing={viewing}
      onViewVersion={setViewing}
      busy={busy}
      notice={notice}
      onGenerate={(sup) => void run("generate", () => uxApi.generate<UxReviewContent>(pid, "ux_review", sup), (s) => { setOverride(s); setViewing(null); })}
      onSubmit={() => void run("submit", () => uxApi.submit<UxReviewContent>(pid, "ux_review", doc!.version, hash), setOverride)}
      onApprove={(ack, note) => uxApi.approve<UxReviewContent>(pid, "ux_review", doc!.version, hash, ack, note).then(setOverride)}
    >
      {content && (
        <section aria-labelledby="ux-review-h" className="space-y-3">
          <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-2">
            <h2 id="ux-review-h" className="text-base font-semibold">Review summary</h2>
            <p className="text-sm text-slate-700">{content.summary}</p>
            {doc?.review_counts && (
              <div className="flex flex-wrap gap-1.5 text-xs pt-1">
                <Badge tone={doc.review_counts.critical_open > 0 ? "danger" : "success"}>
                  Critical open: {doc.review_counts.critical_open}
                </Badge>
                <Badge tone="info">Deterministic checks: {doc.review_counts.deterministic}</Badge>
                <Badge tone="warning">AI suggestions: {doc.review_counts.ai}</Badge>
                <Badge tone="success">Resolved: {doc.review_counts.resolved}</Badge>
                <Badge tone="neutral">Accepted risks: {doc.review_counts.accepted}</Badge>
              </div>
            )}
          </div>

          <ul className="space-y-2" aria-label="UX review findings">
            {content.findings.map((f) => (
              <li key={f.id} className="rounded-lg border border-slate-200 bg-white p-4 space-y-1.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge>{f.id}</Badge>
                    <Badge tone={SEV_TONE[f.severity]}>{f.severity.toUpperCase()}</Badge>
                    <Badge tone={f.origin === "deterministic" ? "info" : "warning"}>
                      {f.origin === "deterministic" ? "Deterministic check" : f.origin === "ai" ? "AI suggestion" : "User finding"}
                    </Badge>
                    <Badge tone="neutral">{f.affected_artifact} v{f.affected_version}{f.affected_item_id ? ` · ${f.affected_item_id}` : ""}</Badge>
                    <Badge tone={f.status === "resolved" ? "success" : f.status === "accepted" ? "info" : "warning"}>
                      Status: {f.status}
                    </Badge>
                  </div>
                  {canEdit && (
                    <div className="flex gap-1">
                      <Button size="sm" disabled={!!busy} onClick={() => setResolving({ finding: f, targetStatus: "resolved" })}>
                        Resolve {f.id}
                      </Button>
                      <Button size="sm" disabled={!!busy} onClick={() => setResolving({ finding: f, targetStatus: "accepted" })}>
                        Accept risk
                      </Button>
                    </div>
                  )}
                </div>
                <h3 className="font-semibold text-sm">{f.title}</h3>
                <p className="text-xs text-slate-700">{f.reasoning}</p>
                <p className="text-xs text-slate-600"><strong>Recommended action:</strong> {f.recommended_action}</p>
                {f.resolution_note && (
                  <p className="text-xs text-emerald-800 bg-emerald-50 rounded p-2">
                    <strong>Resolution / Accepted risk note:</strong> {f.resolution_note}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {resolving && doc && (
        <ResolveFindingDialog
          finding={resolving.finding}
          targetStatus={resolving.targetStatus}
          onClose={() => setResolving(null)}
          onSubmit={(note) => act(() => uxApi.patchFinding(pid, doc.version, hash, resolving.finding.id, { status: resolving.targetStatus, resolution_note: note }), applyEdit)}
        />
      )}
    </UxWorkspaceShell>
  );
}

function ResolveFindingDialog({ finding, targetStatus, onSubmit, onClose }: { finding: UxReviewFinding; targetStatus: FindingStatus; onSubmit: (note: string) => Promise<void>; onClose: () => void }) {
  const [note, setNote] = useState(finding.resolution_note ?? "");
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  return (
    <Dialog title={`${targetStatus === "resolved" ? "Resolve" : "Accept risk for"} ${finding.id}`} onClose={onClose}>
      <form noValidate className="space-y-3" onSubmit={async (e) => {
        e.preventDefault(); setBusy(true); setErrors([]);
        try { await onSubmit(note.trim()); } catch (err) { setErrors(messagesOf(err)); setBusy(false); }
      }}>
        {errors.length > 0 && <Alert tone="error">{errors.map((m) => <p key={m}>{m}</p>)}</Alert>}
        <p className="text-sm">{finding.title}</p>
        <TextAreaField label={targetStatus === "resolved" ? "How was this resolved?" : "Why is this risk accepted?"} rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
        <div className="flex justify-end gap-2">
          <Button onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" variant="primary" loading={busy}>Save {targetStatus}</Button>
        </div>
      </form>
    </Dialog>
  );
}
