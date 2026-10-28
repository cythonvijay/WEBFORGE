import { useRef, useState } from "react";
import { ErrorState, LoadingState } from "../components/feedback/States";
import { Alert } from "../components/ui/Alert";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { TextAreaField, TextField } from "../components/ui/Fields";
import { ConfirmDialog, messagesOf } from "../features/research/Dialogs";
import { UxWorkspaceShell, type UxNotice } from "../features/ux/UxWorkspaceShell";
import { uxApi } from "../features/ux/api";
import { ApiError } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import type { Persona, PersonaEvidenceStatus, PersonasContent, UxArtifactState, UxDocument, UxEditResponse } from "../types/ux";
import { useProject } from "./ProjectLayout";

const EV_BADGE: Record<PersonaEvidenceStatus, { label: string; tone: "success" | "info" | "warning" }> = {
  evidence_backed: { label: "Evidence-backed", tone: "success" },
  mixed: { label: "Mixed evidence & hypotheses", tone: "info" },
  hypothesis: { label: "Hypothesis — needs validation", tone: "warning" },
};

function describe(e: unknown): UxNotice {
  if (e instanceof ApiError) {
    if (e.status === 503) return { tone: "warning", title: "AI analysis is not configured yet.", body: "Nothing was changed. You can still create personas manually." };
    if (e.status === 502) return { tone: "error", title: "WebForge couldn't produce valid personas.", body: `${e.message} Nothing was changed.` };
    return { tone: "error", title: e.message };
  }
  return { tone: "error", title: "Something went wrong." };
}

export default function PersonasPage() {
  const { project } = useProject();
  const pid = project.id;
  const load = useAsync(() => uxApi.get<PersonasContent>(pid, "personas"), [pid]);
  const [override, setOverride] = useState<UxArtifactState<PersonasContent>>();
  const [viewing, setViewing] = useState<number | null>(null);
  const viewed = useAsync(() => (viewing ? uxApi.version<PersonasContent>(pid, "personas", viewing) : Promise.resolve(null)), [pid, viewing]);
  const [notice, setNotice] = useState<UxNotice | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef<string | null>(null);
  const [modal, setModal] = useState<{ kind: "edit"; persona?: Persona; manualInit?: boolean } | { kind: "delete"; persona: Persona } | null>(null);
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
    try { onDone(await fn()); setModal(null); }
    finally { busyRef.current = null; setBusy(null); }
  }

  if (load.loading && !state) return <LoadingState label="Loading personas…" />;
  if (!state) return <ErrorState message={load.error?.message ?? "We couldn't load personas."} onRetry={load.reload} />;

  const doc: UxDocument<PersonasContent> | null = viewing ? (viewed.data ?? null) : state.current;
  const content = doc?.content ?? null;
  const hash = doc?.content_hash ?? "";
  const canEdit = viewing === null && !!doc && ["draft", "in_review", "approved"].includes(doc.status);
  const applyEdit = (r: UxEditResponse<PersonasContent>) => {
    setOverride(r.state);
    if (r.document.version !== doc?.version) setNotice({ tone: "success", title: `Saved as new draft version ${r.document.version}.` });
  };

  return (
    <UxWorkspaceShell
      projectId={pid}
      title="Personas"
      subtitle="Research- and PRD-grounded user personas with explicit evidence provenance and accessibility considerations."
      state={state}
      doc={doc}
      viewing={viewing}
      onViewVersion={setViewing}
      busy={busy}
      notice={notice}
      onGenerate={(sup) => void run("generate", () => uxApi.generate<PersonasContent>(pid, "personas", sup), (s) => { setOverride(s); setViewing(null); })}
      onSubmit={() => void run("submit", () => uxApi.submit<PersonasContent>(pid, "personas", doc!.version, hash), setOverride)}
      onApprove={(ack, note) => act(() => uxApi.approve<PersonasContent>(pid, "personas", doc!.version, hash, ack, note), setOverride)}
      emptyExtra={
        <Button onClick={() => setModal({ kind: "edit", manualInit: true })}>Create persona manually</Button>
      }
    >
      {content && (
        <section aria-labelledby="personas-list-h" className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h2 id="personas-list-h" className="text-base font-semibold">Defined personas ({content.personas.length})</h2>
            {canEdit && <Button size="sm" disabled={!!busy} onClick={() => setModal({ kind: "edit" })}>Add persona</Button>}
          </div>
          <ul className="space-y-3">
            {content.personas.map((p) => (
              <li key={p.id} className="rounded-lg border border-slate-200 bg-white p-4 space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge>{p.id}</Badge>
                    <span className="font-semibold text-base">{p.name}</span>
                    <Badge tone="neutral">{p.segment}</Badge>
                    <Badge tone={EV_BADGE[p.evidence_status].tone}>{EV_BADGE[p.evidence_status].label}</Badge>
                    {p.needs_evidence && <Badge tone="warning">Needs evidence</Badge>}
                  </div>
                  {canEdit && (
                    <div className="flex gap-1">
                      <Button size="sm" disabled={!!busy} onClick={() => setModal({ kind: "edit", persona: p })} aria-label={`Edit ${p.id}`}>Edit</Button>
                      <Button size="sm" variant="ghost" className="text-red-700" disabled={!!busy} onClick={() => setModal({ kind: "delete", persona: p })} aria-label={`Delete ${p.id}`}>Delete</Button>
                    </div>
                  )}
                </div>
                <p className="text-sm text-slate-700">{p.context}</p>
                {p.note && <p className="text-xs text-amber-800">{p.note}</p>}
                <div className="grid gap-3 sm:grid-cols-2 text-xs">
                  <div><h3 className="font-semibold text-slate-600">Goals & outcomes</h3><ul className="mt-1 list-disc pl-4 space-y-0.5">{p.goals.map((g) => <li key={g}>{g}</li>)}</ul></div>
                  <div><h3 className="font-semibold text-slate-600">Tasks & behaviors</h3><ul className="mt-1 list-disc pl-4 space-y-0.5">{p.tasks_behaviors.map((t) => <li key={t}>{t}</li>)}</ul></div>
                  <div><h3 className="font-semibold text-slate-600">Needs & pain points</h3><ul className="mt-1 list-disc pl-4 space-y-0.5">{p.needs_pain_points.map((n) => <li key={n}>{n}</li>)}</ul></div>
                  <div><h3 className="font-semibold text-slate-600">Accessibility & devices</h3><ul className="mt-1 list-disc pl-4 space-y-0.5">{p.accessibility_device_notes.map((a) => <li key={a}>{a}</li>)}</ul></div>
                </div>
                {p.unverified_assumptions.length > 0 && (
                  <div className="text-xs text-amber-900 bg-amber-50 rounded p-2">
                    <strong>Unverified assumptions:</strong> {p.unverified_assumptions.join(" · ")}
                  </div>
                )}
                <p className="text-xs text-slate-500">
                  PRD requirements: {p.prd_requirement_ids.join(", ")}
                  {p.user_story_ids.length > 0 ? ` · User stories: ${p.user_story_ids.join(", ")}` : ""}
                  {p.evidence_refs.length > 0 ? ` · Evidence refs: ${p.evidence_refs.join(", ")}` : ""}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {modal?.kind === "edit" && (
        <PersonaDialog
          persona={modal.persona}
          validReqs={content?.basis.valid_req_ids ?? state.basis_preview?.valid_req_ids ?? ["FR-1"]}
          onClose={() => setModal(null)}
          onSubmit={(b) =>
            modal.manualInit
              ? act(() => uxApi.manualPersonas(pid, b), setOverride)
              : act(() => (modal.persona ? uxApi.patchPersona(pid, doc!.version, hash, modal.persona.id, b) : uxApi.addPersona(pid, doc!.version, hash, b)), applyEdit)
          }
        />
      )}
      {modal?.kind === "delete" && doc && (
        <ConfirmDialog
          title="Delete persona?"
          confirmLabel="Delete persona"
          onClose={() => setModal(null)}
          body={<p>“{modal.persona.name}” will be removed from this version.</p>}
          onConfirm={() => act(() => uxApi.deletePersona(pid, doc.version, hash, modal.persona.id), applyEdit)}
        />
      )}
    </UxWorkspaceShell>
  );
}

function PersonaDialog({ persona, validReqs, onSubmit, onClose }: { persona?: Persona; validReqs: string[]; onSubmit: (b: Record<string, unknown>) => Promise<void>; onClose: () => void }) {
  const [name, setName] = useState(persona?.name ?? "");
  const [segment, setSegment] = useState(persona?.segment ?? "");
  const [context, setContext] = useState(persona?.context ?? "");
  const [goals, setGoals] = useState((persona?.goals ?? []).join("
"));
  const [tasks, setTasks] = useState((persona?.tasks_behaviors ?? []).join("
"));
  const [needs, setNeeds] = useState((persona?.needs_pain_points ?? []).join("
"));
  const [a11y, setA11y] = useState((persona?.accessibility_device_notes ?? []).join("
"));
  const [reqs, setReqs] = useState<string[]>(persona?.prd_requirement_ids ?? (validReqs[0] ? [validReqs[0]] : []));
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  return (
    <Dialog title={persona ? `Edit ${persona.id}` : "Add persona"} onClose={onClose}>
      <form noValidate className="space-y-3" onSubmit={async (e) => {
        e.preventDefault(); setBusy(true); setErrors([]);
        try {
          await onSubmit({
            name: name.trim(),
            segment: segment.trim(),
            context: context.trim(),
            goals: goals.split("
").map((s) => s.trim()).filter(Boolean),
            tasks_behaviors: tasks.split("
").map((s) => s.trim()).filter(Boolean),
            needs_pain_points: needs.split("
").map((s) => s.trim()).filter(Boolean),
            accessibility_device_notes: a11y.split("
").map((s) => s.trim()).filter(Boolean),
            prd_requirement_ids: reqs,
            evidence_status: persona?.evidence_status ?? "hypothesis",
          });
        } catch (err) { setErrors(messagesOf(err)); setBusy(false); }
      }}>
        {errors.length > 0 && <Alert tone="error">{errors.map((m) => <p key={m}>{m}</p>)}</Alert>}
        <TextField label="Persona name" value={name} onChange={(e) => setName(e.target.value)} />
        <TextField label="User segment" value={segment} onChange={(e) => setSegment(e.target.value)} />
        <TextAreaField label="Context" rows={2} value={context} onChange={(e) => setContext(e.target.value)} />
        <TextAreaField label="Goals (one per line)" rows={2} value={goals} onChange={(e) => setGoals(e.target.value)} />
        <TextAreaField label="Tasks & behaviors (one per line)" rows={2} value={tasks} onChange={(e) => setTasks(e.target.value)} />
        <TextAreaField label="Needs & pain points (one per line)" rows={2} value={needs} onChange={(e) => setNeeds(e.target.value)} />
        <TextAreaField label="Accessibility & device notes (one per line)" rows={2} value={a11y} onChange={(e) => setA11y(e.target.value)} />
        <div className="flex justify-end gap-2"><Button onClick={onClose} disabled={busy}>Cancel</Button><Button type="submit" variant="primary" loading={busy}>{persona ? "Save persona" : "Add persona"}</Button></div>
      </form>
    </Dialog>
  );
}
