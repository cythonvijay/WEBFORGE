import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorState, LoadingState } from "../components/feedback/States";
import { Alert } from "../components/ui/Alert";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { TextAreaField } from "../components/ui/Fields";
import { designApi } from "../features/design/api";
import { ConfirmDialog, messagesOf } from "../features/research/Dialogs";
import { STATUS } from "../features/research/labels";
import { ApiError } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import { formatDateTime } from "../lib/utils";
import type { DesignArtifactState, DesignDocument, PrototypeContent, PrototypeInteraction, UiStateKind } from "../types/design";
import { useProject } from "./ProjectLayout";

type PreviewViewport = "desktop" | "tablet" | "mobile";
type Notice = { tone: "error" | "warning" | "success"; title: string; body?: string };

function describe(e: unknown): Notice {
  if (e instanceof ApiError) return { tone: "error", title: e.message };
  return { tone: "error", title: "Something went wrong." };
}

export default function PrototypePage() {
  const { project } = useProject();
  const pid = project.id;
  const load = useAsync(() => designApi.get<PrototypeContent>(pid, "prototype"), [pid]);
  const [override, setOverride] = useState<DesignArtifactState<PrototypeContent>>();
  const [viewing, setViewing] = useState<number | null>(null);
  const viewed = useAsync(() => (viewing ? designApi.version<PrototypeContent>(pid, "prototype", viewing) : Promise.resolve(null)), [pid, viewing]);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef<string | null>(null);
  const [modal, setModal] = useState<"regenerate" | "approve" | null>(null);

  // Interactive prototype simulation state (isolated from production APIs)
  const [activeScreenId, setActiveScreenId] = useState<string | null>(null);
  const [showIndex, setShowIndex] = useState<boolean>(false);
  const [viewport, setViewport] = useState<PreviewViewport>("desktop");
  const [uiState, setUiState] = useState<UiStateKind>("default");
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [simDialog, setSimDialog] = useState<{ title: string; body: string } | null>(null);
  const [simLog, setSimLog] = useState<string[]>([]);

  const state = override ?? load.data;

  async function run<T>(key: string, fn: () => Promise<T>, onDone: (r: T) => void) {
    if (busyRef.current) return;
    busyRef.current = key; setBusy(key); setNotice(null);
    try { onDone(await fn()); }
    catch (e) { setNotice(describe(e)); }
    finally { busyRef.current = null; setBusy(null); }
  }

  if (load.loading && !state) return <LoadingState label="Loading interactive prototype…" />;
  if (!state) return <ErrorState message={load.error?.message ?? "We couldn't load the interactive prototype."} onRetry={load.reload} />;

  const doc: DesignDocument<PrototypeContent> | null = viewing ? (viewed.data ?? null) : state.current;
  const content = doc?.content ?? null;
  const hash = doc?.content_hash ?? "";
  const readOnly = viewing !== null;
  const startLabel = state.status === "not_started" ? "Generate Interactive Prototype" : state.status === "failed" ? "Retry generating Prototype" : "Regenerate Prototype";

  const screens = content?.screens ?? [];
  const currentScreen = screens.find((s) => s.id === (activeScreenId ?? screens[0]?.id)) ?? screens[0] ?? null;
  const tokenPreview = content?.basis.token_preview ?? {};
  const primaryHex = tokenPreview["--color-primary"] ?? "#1E40AF";
  const widthClass = viewport === "desktop" ? "w-full" : viewport === "tablet" ? "max-w-xl mx-auto" : "max-w-xs mx-auto";

  function handleInteraction(ix: PrototypeInteraction) {
    if (!currentScreen) return;
    if (ix.action_type === "navigate" && ix.target_screen_id) {
      setActiveScreenId(ix.target_screen_id);
      setUiState(ix.resulting_state || "default");
      setShowIndex(false);
      setFormErrors({});
      setSimLog((prev) => [`Navigated from ${currentScreen.id} to ${ix.target_screen_id} via "${ix.trigger_label}"`, ...prev.slice(0, 7)]);
    } else if (ix.action_type === "open_dialog" && ix.dialog_title && ix.dialog_body) {
      setSimDialog({ title: ix.dialog_title, body: ix.dialog_body });
      setSimLog((prev) => [`Opened simulated dialog "${ix.dialog_title}" on ${currentScreen.id}`, ...prev.slice(0, 7)]);
    } else if (ix.action_type === "submit_form") {
      const errs: Record<string, string> = {};
      for (const f of currentScreen.form_fields) {
        const val = (formValues[`${currentScreen.id}:${f.name}`] ?? f.default_mock_value).trim();
        if (f.required && !val) {
          errs[f.name] = `${f.label} is required (${f.validation_rule})`;
        }
      }
      setFormErrors(errs);
      if (Object.keys(errs).length > 0) {
        setSimLog((prev) => [`Form validation blocked "${ix.trigger_label}" on ${currentScreen.id}`, ...prev.slice(0, 7)]);
        return;
      }
      setUiState(ix.resulting_state || "success");
      setSimLog((prev) => [`Simulated form submit "${ix.trigger_label}" succeeded on ${currentScreen.id}`, ...prev.slice(0, 7)]);
    } else if (ix.action_type === "set_state") {
      setUiState(ix.resulting_state);
      setSimLog((prev) => [`Switched ${currentScreen.id} to simulated ${ix.resulting_state} state`, ...prev.slice(0, 7)]);
    }
  }

  return (
    <div className="max-w-4xl space-y-4">
      <header>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-xl font-semibold">Interactive Prototype</h1>
          <nav aria-label="Design workspaces" className="flex gap-1.5 text-xs">
            <Link to={`/projects/${pid}/design-system`} className="rounded border border-slate-200 bg-white px-2.5 py-1 hover:bg-slate-50">1. Design System</Link>
            <Link to={`/projects/${pid}/prototype`} className="rounded border border-slate-300 bg-slate-100 px-2.5 py-1 font-medium">2. Interactive Prototype</Link>
          </nav>
        </div>
        <p className="mt-0.5 text-slate-600">Interactive screen navigation, journey happy-path flows, simulated form validation, and dialogs driven by your approved Wireframes and Design System.</p>
        <div className="mt-2 flex flex-wrap items-center gap-1.5" aria-label="Prototype status">
          <Badge tone={STATUS[(doc?.status ?? state.status) as keyof typeof STATUS].tone}>
            {STATUS[(doc?.status ?? state.status) as keyof typeof STATUS].label}
          </Badge>
          {doc && <Badge>Version {doc.version}</Badge>}
          {doc?.is_stale && <Badge tone="warning">Stale upstream</Badge>}
          <Badge tone={state.lifecycle.status === "complete" ? "success" : "neutral"}>
            Design stage: {state.lifecycle.status.replace("_", " ")}
          </Badge>
          {state.approved_version !== null && <Badge tone="success">Approved version: {state.approved_version}</Badge>}
        </div>
      </header>

      <Alert tone="warning" title="Simulated prototype — isolated from production APIs and real user data">
        <ul className="list-disc pl-5">{state.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </Alert>
      {notice && <Alert tone={notice.tone} title={notice.title}>{notice.body}</Alert>}

      {!state.prerequisites.ready && (
        <section aria-label="Prerequisite gates" className="rounded-lg border border-amber-300 bg-amber-50 p-4 space-y-2">
          <h2 className="font-semibold text-amber-900">Upstream prerequisites required</h2>
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

      {!doc && !viewing && state.prerequisites.ready && (
        <section className="rounded-lg border border-slate-200 bg-white p-5 space-y-3">
          <h2 className="font-semibold">No Interactive Prototype yet</h2>
          <p className="text-sm text-slate-600">{state.next_step.label}</p>
          <Button variant="primary" loading={busy === "generate"} disabled={!!busy || !state.can_generate} onClick={() => void run("generate", () => designApi.generate<PrototypeContent>(pid, "prototype", false), setOverride)}>
            {busy === "generate" ? "Generating…" : startLabel}
          </Button>
        </section>
      )}

      {doc && content && currentScreen && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {!readOnly && doc.status === "draft" && (
              <Button variant="primary" disabled={!!busy || !state.can_submit} loading={busy === "submit"} onClick={() => void run("submit", () => designApi.submit<PrototypeContent>(pid, "prototype", doc.version, hash), setOverride)}>
                Submit for review
              </Button>
            )}
            {!readOnly && doc.status === "in_review" && (
              <Button variant="primary" disabled={!!busy || !state.can_approve} onClick={() => setModal("approve")}>
                Approve version {doc.version}
              </Button>
            )}
            {!readOnly && (
              <Button disabled={!!busy || !state.can_generate} loading={busy === "generate"} onClick={() => (state.needs_supersede ? setModal("regenerate") : void run("generate", () => designApi.generate<PrototypeContent>(pid, "prototype", false), setOverride))}>
                {busy === "generate" ? "Generating…" : "Regenerate Prototype"}
              </Button>
            )}
          </div>

          {doc.status === "approved" && (
            <Alert tone="success" title={`Version ${doc.version} approved${doc.approved_at ? ` on ${formatDateTime(doc.approved_at)}` : ""}`}>
              {doc.approval_note}
            </Alert>
          )}

          {/* Prototype Controls: Screen Index, Journey Flows, Viewport & State Switcher */}
          <section aria-label="Prototype controls" className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <Button size="sm" variant={showIndex ? "primary" : "secondary"} onClick={() => setShowIndex(!showIndex)}>
                  {showIndex ? "Hide Screen Index" : "Screen Index & Relationships"}
                </Button>
                {screens.map((s) => (
                  <Button
                    key={s.id}
                    size="sm"
                    variant={!showIndex && currentScreen.id === s.id ? "primary" : "secondary"}
                    onClick={() => { setActiveScreenId(s.id); setShowIndex(false); setUiState("default"); setFormErrors({}); }}
                  >
                    {s.id}: {s.title}
                  </Button>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <div role="group" aria-label="Viewport switcher" className="flex gap-1">
                  {(["desktop", "tablet", "mobile"] as PreviewViewport[]).map((vp) => (
                    <Button key={vp} size="sm" variant={viewport === vp ? "primary" : "secondary"} onClick={() => setViewport(vp)}>
                      {vp.charAt(0).toUpperCase() + vp.slice(1)}
                    </Button>
                  ))}
                </div>
                <label className="flex items-center gap-1">
                  <span>State:</span>
                  <select aria-label="Prototype UI state" value={uiState} onChange={(e) => setUiState(e.target.value as UiStateKind)} className="h-8 rounded border border-slate-300 bg-white px-2 text-xs">
                    <option value="default">Default</option>
                    <option value="loading">Loading</option>
                    <option value="empty">Empty</option>
                    <option value="error">Error</option>
                    <option value="success">Success</option>
                  </select>
                </label>
              </div>
            </div>

            {/* Journey Happy-Path Flows */}
            <div className="border-t border-slate-100 pt-2 text-xs">
              <span className="font-semibold text-slate-600">Journey happy paths: </span>
              {content.flows.map((fl) => (
                <button
                  key={fl.id}
                  type="button"
                  onClick={() => { setActiveScreenId(fl.start_screen_id); setShowIndex(false); setUiState("default"); }}
                  className="mr-2 inline-flex items-center gap-1 rounded border border-slate-200 bg-slate-50 px-2 py-0.5 hover:bg-slate-100"
                >
                  <strong>{fl.id} ({fl.journey_id}):</strong> {fl.title} ({fl.ordered_screen_ids.join(" → ")})
                </button>
              ))}
            </div>
          </section>

          {showIndex ? (
            <section aria-label="Screen index" className="rounded-lg border border-slate-200 bg-white p-4 space-y-2">
              <h2 className="text-base font-semibold">Screen index & navigation relationships ({screens.length} screens)</h2>
              <ul className="space-y-2 text-sm">
                {screens.map((s) => (
                  <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-slate-200 p-3">
                    <div>
                      <Badge>{s.id}</Badge> <span className="font-semibold">{s.title}</span> <code className="text-xs text-slate-500">{s.route_path}</code>
                      <p className="text-xs text-slate-600">Wireframe: {s.wireframe_id} · IA: {s.ia_node_id} · Components: {s.component_ids.join(", ")}</p>
                      <p className="text-xs text-slate-500">
                        Links to: {s.interactions.filter((ix) => ix.target_screen_id).map((ix) => `${ix.target_screen_id} (${ix.trigger_label})`).join(", ") || "None"}
                      </p>
                    </div>
                    <Button size="sm" onClick={() => { setActiveScreenId(s.id); setShowIndex(false); }}>Open {s.id}</Button>
                  </li>
                ))}
              </ul>
            </section>
          ) : (
            <section
              aria-label={`Interactive screen ${currentScreen.id}`}
              data-testid={`proto-screen-${currentScreen.id}`}
              data-viewport={viewport}
              style={{ borderColor: primaryHex }}
              className={`${widthClass} rounded-lg border-2 bg-white p-4 space-y-3 shadow-sm transition-all`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge>{currentScreen.id}</Badge>
                  <h2 className="text-base font-semibold">{currentScreen.title}</h2>
                  <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{currentScreen.route_path}</code>
                  <Badge tone="info">Wireframe {currentScreen.wireframe_id}</Badge>
                  <Badge tone="neutral">Components: {currentScreen.component_ids.join(", ")}</Badge>
                </div>
                <span className="text-xs text-slate-500">{viewport.toUpperCase()} · {currentScreen.responsive_behavior[viewport]}</span>
              </div>

              <p className="text-xs text-slate-500"><strong>Simulated data:</strong> {currentScreen.mock_data_note}</p>

              {uiState !== "default" ? (
                <div className="rounded border border-slate-300 bg-slate-50 p-5 text-center space-y-2" data-testid="proto-state-view">
                  <Badge tone={uiState === "error" ? "error" : uiState === "success" ? "success" : "info"}>
                    SIMULATED {uiState.toUpperCase()} STATE
                  </Badge>
                  <p className="text-sm text-slate-700">{currentScreen.states[uiState]}</p>
                  <Button size="sm" onClick={() => setUiState("default")}>Return to default layout</Button>
                </div>
              ) : (
                <div className="space-y-3">
                  {/* Reused wireframe layout regions */}
                  {currentScreen.regions.map((reg, idx) => (
                    <div key={`${reg.region}-${idx}`} className="rounded border border-slate-200 bg-slate-50 p-3 space-y-1.5">
                      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">[{reg.region}] {reg.heading}</div>
                      <div className={viewport === "mobile" ? "space-y-2" : "grid gap-2 sm:grid-cols-2"}>
                        {reg.components.map((cmp) => (
                          <div key={cmp.id} className="rounded border border-slate-200 bg-white p-2.5 text-xs">
                            <div className="font-medium text-slate-800">{cmp.label}</div>
                            <p className="text-slate-600">{cmp.content_role}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}

                  {/* Interactive simulated form fields */}
                  {currentScreen.form_fields.length > 0 && (
                    <div className="rounded border border-slate-200 bg-white p-3 space-y-2">
                      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Interactive simulated form</h3>
                      {currentScreen.form_fields.map((f) => {
                        const key = `${currentScreen.id}:${f.name}`;
                        const val = formValues[key] ?? f.default_mock_value;
                        const err = formErrors[f.name];
                        return (
                          <div key={f.name} className="space-y-1">
                            <label className="block text-xs font-medium text-slate-700">
                              {f.label} {f.required && <span className="text-red-600">*</span>}
                              <input
                                aria-label={f.label}
                                value={val}
                                placeholder={f.placeholder}
                                onChange={(e) => setFormValues({ ...formValues, [key]: e.target.value })}
                                className="mt-1 h-8 w-full rounded border border-slate-300 px-2 text-xs"
                              />
                            </label>
                            {err && <p role="alert" className="text-xs text-red-700">{err}</p>}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* Interactive Simulated Triggers */}
              <div className="border-t border-slate-200 pt-3">
                <div className="mb-1.5 text-xs font-semibold text-slate-600">Simulated actions (local prototype state only):</div>
                <div className="flex flex-wrap gap-2">
                  {currentScreen.interactions.map((ix) => (
                    <Button
                      key={ix.id}
                      size="sm"
                      variant={ix.trigger_kind === "primary_button" || ix.trigger_kind === "form_submit" ? "primary" : "secondary"}
                      onClick={() => handleInteraction(ix)}
                    >
                      {ix.trigger_label}
                    </Button>
                  ))}
                </div>
              </div>
            </section>
          )}

          {simLog.length > 0 && (
            <section aria-label="Simulated interaction log" className="rounded border border-slate-200 bg-slate-50 p-3 text-xs">
              <div className="font-semibold text-slate-600">Simulated interaction log</div>
              <ul className="mt-1 list-disc pl-4 space-y-0.5 text-slate-600">
                {simLog.map((entry, idx) => <li key={idx}>{entry}</li>)}
              </ul>
            </section>
          )}
        </>
      )}

      {simDialog && (
        <Dialog title={`${simDialog.title} (Simulated)`} onClose={() => setSimDialog(null)}>
          <div className="space-y-3 text-sm">
            <Badge tone="info">Simulated Prototype Dialog</Badge>
            <p>{simDialog.body}</p>
            <div className="flex justify-end gap-2">
              <Button onClick={() => setSimDialog(null)}>Close</Button>
              <Button variant="primary" onClick={() => { setSimDialog(null); setUiState("success"); }}>
                Confirm (Simulated)
              </Button>
            </div>
          </div>
        </Dialog>
      )}

      {modal === "regenerate" && (
        <ConfirmDialog title="Regenerate Interactive Prototype?" confirmLabel="Regenerate" onClose={() => setModal(null)}
          body={<p>A new version will be generated. The current draft stays in history as superseded.</p>}
          onConfirm={async () => { setModal(null); void run("generate", () => designApi.generate<PrototypeContent>(pid, "prototype", true), setOverride); }} />
      )}
      {modal === "approve" && doc && (
        <Dialog title="Approve Interactive Prototype version" onClose={() => setModal(null)}>
          <ProtoApproveBody
            onClose={() => setModal(null)}
            onSubmit={async (note) => {
              const next = await designApi.approve<PrototypeContent>(pid, "prototype", doc.version, hash, false, note);
              setOverride(next);
              setModal(null);
            }}
          />
        </Dialog>
      )}
    </div>
  );
}

function ProtoApproveBody({ onSubmit, onClose }: { onSubmit: (note: string) => Promise<void>; onClose: () => void }) {
  const [note, setNote] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  return (
    <form noValidate className="space-y-3" onSubmit={async (e) => { e.preventDefault(); setBusy(true); setErrors([]); try { await onSubmit(note); } catch (err) { setErrors(messagesOf(err)); setBusy(false); } }}>
      {errors.length > 0 && <Alert tone="error">{errors.map((m) => <p key={m}>{m}</p>)}</Alert>}
      <p className="text-sm">Approving records this exact Prototype version in your Project Brain and completes the Design lifecycle stage.</p>
      <TextAreaField label="Approval note (optional)" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
      <div className="flex justify-end gap-2">
        <Button onClick={onClose} disabled={busy}>Cancel</Button>
        <Button type="submit" variant="primary" loading={busy}>Approve Prototype</Button>
      </div>
    </form>
  );
}
