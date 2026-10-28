import { useRef, useState } from "react";
import { ErrorState, LoadingState } from "../components/feedback/States";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { UxWorkspaceShell, type UxNotice } from "../features/ux/UxWorkspaceShell";
import { uxApi } from "../features/ux/api";
import { ApiError } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import type { JourneysContent, UxArtifactState, UxDocument, UxEditResponse } from "../types/ux";
import { useProject } from "./ProjectLayout";

function describe(e: unknown): UxNotice {
  if (e instanceof ApiError) {
    if (e.status === 503) return { tone: "warning", title: "AI analysis is not configured yet.", body: "Nothing was changed." };
    if (e.status === 502) return { tone: "error", title: "WebForge couldn't produce valid user journeys.", body: `${e.message} Nothing was changed.` };
    return { tone: "error", title: e.message };
  }
  return { tone: "error", title: "Something went wrong." };
}

export default function JourneysPage() {
  const { project } = useProject();
  const pid = project.id;
  const load = useAsync(() => uxApi.get<JourneysContent>(pid, "journeys"), [pid]);
  const [override, setOverride] = useState<UxArtifactState<JourneysContent>>();
  const [viewing, setViewing] = useState<number | null>(null);
  const viewed = useAsync(() => (viewing ? uxApi.version<JourneysContent>(pid, "journeys", viewing) : Promise.resolve(null)), [pid, viewing]);
  const [notice, setNotice] = useState<UxNotice | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef<string | null>(null);
  const state = override ?? load.data;

  async function run<T>(key: string, fn: () => Promise<T>, onDone: (r: T) => void) {
    if (busyRef.current) return;
    busyRef.current = key; setBusy(key); setNotice(null);
    try { onDone(await fn()); }
    catch (e) { setNotice(describe(e)); }
    finally { busyRef.current = null; setBusy(null); }
  }

  if (load.loading && !state) return <LoadingState label="Loading user journeys…" />;
  if (!state) return <ErrorState message={load.error?.message ?? "We couldn't load user journeys."} onRetry={load.reload} />;

  const doc: UxDocument<JourneysContent> | null = viewing ? (viewed.data ?? null) : state.current;
  const content = doc?.content ?? null;
  const hash = doc?.content_hash ?? "";
  const canEdit = viewing === null && !!doc && ["draft", "in_review", "approved"].includes(doc.status);
  const applyEdit = (r: UxEditResponse<JourneysContent>) => {
    setOverride(r.state);
    if (r.document.version !== doc?.version) setNotice({ tone: "success", title: `Saved as new draft version ${r.document.version}.` });
  };

  return (
    <UxWorkspaceShell
      projectId={pid}
      title="User Journeys"
      subtitle="Stage-by-stage timelines for PRD-supported user goals with explicit failure and recovery paths."
      state={state}
      doc={doc}
      viewing={viewing}
      onViewVersion={setViewing}
      busy={busy}
      notice={notice}
      onGenerate={(sup) => void run("generate", () => uxApi.generate<JourneysContent>(pid, "journeys", sup), (s) => { setOverride(s); setViewing(null); })}
      onSubmit={() => void run("submit", () => uxApi.submit<JourneysContent>(pid, "journeys", doc!.version, hash), setOverride)}
      onApprove={(ack, note) => uxApi.approve<JourneysContent>(pid, "journeys", doc!.version, hash, ack, note).then(setOverride)}
    >
      {content && (
        <section aria-labelledby="journeys-list-h" className="space-y-4">
          <h2 id="journeys-list-h" className="text-base font-semibold">User journeys ({content.journeys.length})</h2>
          {content.journeys.map((j) => (
            <article key={j.id} aria-label={`${j.id}: ${j.title}`} className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge>{j.id}</Badge>
                  <h3 className="font-semibold text-base">{j.title}</h3>
                  <Badge tone="info">Persona: {j.persona_id}</Badge>
                  <Badge tone="neutral">PRD: {j.prd_requirement_ids.join(", ")}</Badge>
                </div>
                {canEdit && (
                  <Button
                    size="sm"
                    disabled={!!busy}
                    onClick={() => {
                      const updatedStages = j.stages.map((st, idx) =>
                        idx === 0
                          ? { ...st, failure_recovery_paths: [...st.failure_recovery_paths, "User can retry from preserved local draft state"] }
                          : st
                      );
                      void run("edit", () => uxApi.patchJourney(pid, doc!.version, hash, j.id, { stages: updatedStages }), applyEdit);
                    }}
                  >
                    Add recovery path
                  </Button>
                )}
              </div>
              <p className="text-sm text-slate-700"><strong>Scenario:</strong> {j.scenario}</p>
              <p className="text-xs text-slate-600"><strong>Entry point:</strong> {j.entry_point} · <strong>Desired outcome:</strong> {j.desired_outcome}</p>
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50 text-slate-600">
                      <th className="p-2">Stage</th>
                      <th className="p-2">User actions & touchpoints</th>
                      <th className="p-2">Thoughts (Hypothesis) & pain points</th>
                      <th className="p-2">System response & failure recovery</th>
                    </tr>
                  </thead>
                  <tbody>
                    {j.stages.map((st) => (
                      <tr key={st.stage_number} className="border-b border-slate-100 align-top">
                        <td className="p-2 font-medium">{st.stage_number}. {st.stage_name}</td>
                        <td className="p-2">
                          <ul className="list-disc pl-4">{st.user_actions.map((a) => <li key={a}>{a}</li>)}</ul>
                          <p className="mt-1 text-slate-500">Touchpoints: {st.touchpoints.join(", ")}</p>
                        </td>
                        <td className="p-2">
                          {st.thoughts_questions.map((t) => (
                            <p key={t}><Badge tone="warning">Hypothesis</Badge> “{t}”</p>
                          ))}
                          {st.pain_points.length > 0 && <p className="mt-1 text-amber-800">Friction: {st.pain_points.join("; ")}</p>}
                        </td>
                        <td className="p-2">
                          <p>{st.system_responses.join("; ")}</p>
                          <p className="mt-1 text-red-800"><strong>Recovery:</strong> {st.failure_recovery_paths.join("; ")}</p>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-slate-600"><strong>Accessibility:</strong> {j.accessibility_considerations.join(" · ")}</p>
            </article>
          ))}
        </section>
      )}
    </UxWorkspaceShell>
  );
}
