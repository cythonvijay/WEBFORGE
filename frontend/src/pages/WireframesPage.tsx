import { useRef, useState } from "react";
import { ErrorState, LoadingState } from "../components/feedback/States";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { UxWorkspaceShell, type UxNotice } from "../features/ux/UxWorkspaceShell";
import { uxApi } from "../features/ux/api";
import { ApiError } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import type { UxArtifactState, UxDocument, UxEditResponse, WireframesContent } from "../types/ux";
import { useProject } from "./ProjectLayout";

type PreviewViewport = "desktop" | "tablet" | "mobile";
type PreviewState = "default" | "loading" | "empty" | "error" | "success";

function describe(e: unknown): UxNotice {
  if (e instanceof ApiError) return { tone: "error", title: e.message };
  return { tone: "error", title: "Something went wrong." };
}

export default function WireframesPage() {
  const { project } = useProject();
  const pid = project.id;
  const load = useAsync(() => uxApi.get<WireframesContent>(pid, "wireframes"), [pid]);
  const [override, setOverride] = useState<UxArtifactState<WireframesContent>>();
  const [viewing, setViewing] = useState<number | null>(null);
  const viewed = useAsync(() => (viewing ? uxApi.version<WireframesContent>(pid, "wireframes", viewing) : Promise.resolve(null)), [pid, viewing]);
  const [notice, setNotice] = useState<UxNotice | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef<string | null>(null);
  const [viewport, setViewport] = useState<PreviewViewport>("desktop");
  const [previewState, setPreviewState] = useState<PreviewState>("default");
  const state = override ?? load.data;

  async function run<T>(key: string, fn: () => Promise<T>, onDone: (r: T) => void) {
    if (busyRef.current) return;
    busyRef.current = key; setBusy(key); setNotice(null);
    try { onDone(await fn()); }
    catch (e) { setNotice(describe(e)); }
    finally { busyRef.current = null; setBusy(null); }
  }

  if (load.loading && !state) return <LoadingState label="Loading wireframes…" />;
  if (!state) return <ErrorState message={load.error?.message ?? "We couldn't load wireframes."} onRetry={load.reload} />;

  const doc: UxDocument<WireframesContent> | null = viewing ? (viewed.data ?? null) : state.current;
  const content = doc?.content ?? null;
  const hash = doc?.content_hash ?? "";
  const canEdit = viewing === null && !!doc && ["draft", "in_review", "approved"].includes(doc.status);
  const applyEdit = (r: UxEditResponse<WireframesContent>) => {
    setOverride(r.state);
    if (r.document.version !== doc?.version) setNotice({ tone: "success", title: `Saved as new draft version ${r.document.version}.` });
  };

  const widthClass = viewport === "desktop" ? "w-full" : viewport === "tablet" ? "max-w-xl mx-auto" : "max-w-xs mx-auto";

  return (
    <UxWorkspaceShell
      projectId={pid}
      title="Wireframes"
      subtitle="Structured low-fidelity wireframe specifications rendered deterministically across viewports and UI states."
      state={state}
      doc={doc}
      viewing={viewing}
      onViewVersion={setViewing}
      busy={busy}
      notice={notice}
      onGenerate={(sup) => void run("generate", () => uxApi.generate<WireframesContent>(pid, "wireframes", sup), (s) => { setOverride(s); setViewing(null); })}
      onSubmit={() => void run("submit", () => uxApi.submit<WireframesContent>(pid, "wireframes", doc!.version, hash), setOverride)}
      onApprove={(ack, note) => uxApi.approve<WireframesContent>(pid, "wireframes", doc!.version, hash, ack, note).then(setOverride)}
    >
      {content && (
        <section aria-labelledby="wf-canvas-h" className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white p-3">
            <h2 id="wf-canvas-h" className="text-base font-semibold">Interactive wireframe preview ({content.wireframes.length} screens)</h2>
            <div className="flex flex-wrap items-center gap-3 text-xs">
              <div role="group" aria-label="Viewport switcher" className="flex gap-1">
                {(["desktop", "tablet", "mobile"] as PreviewViewport[]).map((vp) => (
                  <Button key={vp} size="sm" variant={viewport === vp ? "primary" : "secondary"} onClick={() => setViewport(vp)}>
                    {vp.charAt(0).toUpperCase() + vp.slice(1)}
                  </Button>
                ))}
              </div>
              <label className="flex items-center gap-1">
                <span>UI state:</span>
                <select aria-label="UI state preview" value={previewState} onChange={(e) => setPreviewState(e.target.value as PreviewState)} className="h-8 rounded border border-slate-300 bg-white px-2 text-xs">
                  <option value="default">Default layout</option>
                  <option value="loading">Loading state</option>
                  <option value="empty">Empty state</option>
                  <option value="error">Error state</option>
                  <option value="success">Success state</option>
                </select>
              </label>
            </div>
          </div>

          {content.wireframes.map((w) => (
            <article key={w.id} aria-label={`Wireframe ${w.id}: ${w.page_name}`} className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge>{w.id}</Badge>
                  <h3 className="font-semibold text-base">{w.page_name}</h3>
                  <Badge tone="info">IA: {w.ia_node_id}</Badge>
                  <Badge tone="neutral">Personas: {w.persona_ids.join(", ")}</Badge>
                  <Badge tone="neutral">Journeys: {w.journey_ids.join(", ")}</Badge>
                  <Badge tone="neutral">PRD: {w.prd_requirement_ids.join(", ")}</Badge>
                </div>
                {canEdit && (
                  <Button
                    size="sm"
                    disabled={!!busy}
                    onClick={() => void run("edit", () => uxApi.patchWireframe(pid, doc!.version, hash, w.id, { primary_actions: [...w.primary_actions, "Keyboard Shortcut Help"] }), applyEdit)}
                  >
                    Add action
                  </Button>
                )}
              </div>
              <p className="text-sm text-slate-700">{w.purpose}</p>

              {/* Low-fidelity deterministic wireframe canvas */}
              <div className={`${widthClass} rounded-lg border-2 border-dashed border-slate-300 bg-slate-50 p-3 space-y-2 transition-all`} data-testid={`wf-canvas-${w.id}`} data-viewport={viewport}>
                <div className="flex items-center justify-between border-b border-slate-200 pb-1.5 text-xs text-slate-500">
                  <span>Low-fidelity frame · {viewport.toUpperCase()}</span>
                  <span>{w.responsive_behavior[viewport]}</span>
                </div>

                {previewState !== "default" ? (
                  <div className="rounded border border-slate-300 bg-white p-4 text-center text-sm">
                    <Badge tone={previewState === "error" ? "danger" : previewState === "success" ? "success" : "info"}>
                      {previewState.toUpperCase()} STATE
                    </Badge>
                    <p className="mt-2 text-slate-700">{w.states[previewState]}</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {w.regions.map((reg, idx) => (
                      <div key={`${reg.region}-${idx}`} className="rounded border border-slate-300 bg-white p-2.5 space-y-1.5">
                        <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-slate-500">
                          <span>[{reg.region}] {reg.heading}</span>
                        </div>
                        <div className={viewport === "mobile" ? "space-y-2" : "grid gap-2 sm:grid-cols-2"}>
                          {reg.components.map((cmp) => (
                            <div key={cmp.id} className="rounded border border-slate-200 bg-slate-50 p-2 text-xs">
                              <div className="font-medium text-slate-800">{cmp.label} <span className="text-slate-500">({cmp.kind})</span></div>
                              <p className="text-slate-600">{cmp.content_role}</p>
                              <div className="mt-1 flex flex-wrap gap-1">
                                {cmp.elements.map((el) => (
                                  <span key={el} className="rounded border border-slate-300 bg-white px-1.5 py-0.5 text-[11px]">{el}</span>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-xs">
                  <div className="flex flex-wrap gap-1">
                    {w.primary_actions.map((a) => <span key={a} className="rounded bg-slate-800 px-2 py-0.5 text-white">[Primary] {a}</span>)}
                    {w.secondary_actions.map((a) => <span key={a} className="rounded border border-slate-400 bg-white px-2 py-0.5 text-slate-700">[Secondary] {a}</span>)}
                  </div>
                </div>
              </div>

              {w.form_fields.length > 0 && (
                <div className="text-xs">
                  <strong>Form fields & validation:</strong>
                  <ul className="mt-1 list-disc pl-5">
                    {w.form_fields.map((f) => <li key={f.name}><strong>{f.name}</strong> ({f.field_type}{f.required ? ", required" : ""}): {f.validation_rule}</li>)}
                  </ul>
                </div>
              )}
              <p className="text-xs text-slate-600"><strong>Keyboard & accessibility:</strong> {w.accessibility_keyboard.join(" · ")}</p>
            </article>
          ))}
        </section>
      )}
    </UxWorkspaceShell>
  );
}
