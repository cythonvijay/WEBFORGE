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
import type { DesignArtifactState, DesignDocument, DesignEditResponse, DesignSystemContent } from "../types/design";
import { useProject } from "./ProjectLayout";

type Notice = { tone: "error" | "warning" | "success"; title: string; body?: string };

function describe(e: unknown): Notice {
  if (e instanceof ApiError) {
    if (e.status === 503) return { tone: "warning", title: "AI analysis is not configured yet.", body: "Nothing was changed." };
    if (e.status === 502) return { tone: "error", title: "WebForge couldn't produce a valid Design System.", body: `${e.message} Nothing was changed.` };
    return { tone: "error", title: e.message };
  }
  return { tone: "error", title: "Something went wrong." };
}

export default function DesignSystemPage() {
  const { project } = useProject();
  const pid = project.id;
  const load = useAsync(() => designApi.get<DesignSystemContent>(pid, "design_system"), [pid]);
  const [override, setOverride] = useState<DesignArtifactState<DesignSystemContent>>();
  const [viewing, setViewing] = useState<number | null>(null);
  const viewed = useAsync(() => (viewing ? designApi.version<DesignSystemContent>(pid, "design_system", viewing) : Promise.resolve(null)), [pid, viewing]);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef<string | null>(null);
  const [modal, setModal] = useState<"regenerate" | "approve" | null>(null);
  const state = override ?? load.data;

  async function run<T>(key: string, fn: () => Promise<T>, onDone: (r: T) => void) {
    if (busyRef.current) return;
    busyRef.current = key; setBusy(key); setNotice(null);
    try { onDone(await fn()); }
    catch (e) { setNotice(describe(e)); }
    finally { busyRef.current = null; setBusy(null); }
  }

  if (load.loading && !state) return <LoadingState label="Loading Design System…" />;
  if (!state) return <ErrorState message={load.error?.message ?? "We couldn't load the Design System."} onRetry={load.reload} />;

  const doc: DesignDocument<DesignSystemContent> | null = viewing ? (viewed.data ?? null) : state.current;
  const content = doc?.content ?? null;
  const hash = doc?.content_hash ?? "";
  const readOnly = viewing !== null;
  const canEdit = !readOnly && !!doc && ["draft", "in_review", "approved"].includes(doc.status);
  const applyEdit = (r: DesignEditResponse<DesignSystemContent>) => {
    setOverride(r.state);
    if (r.document.version !== doc?.version) setNotice({ tone: "success", title: `Saved as new draft version ${r.document.version}.` });
  };
  const startLabel = state.status === "not_started" ? "Generate Design System" : state.status === "failed" ? "Retry generating Design System" : "Regenerate Design System";

  return (
    <div className="max-w-4xl space-y-4">
      <header>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-xl font-semibold">Design System</h1>
          <nav aria-label="Design workspaces" className="flex gap-1.5 text-xs">
            <Link to={`/projects/${pid}/design-system`} className="rounded border border-slate-300 bg-slate-100 px-2.5 py-1 font-medium">1. Design System</Link>
            <Link to={`/projects/${pid}/prototype`} className="rounded border border-slate-200 bg-white px-2.5 py-1 hover:bg-slate-50">2. Interactive Prototype</Link>
          </nav>
        </div>
        <p className="mt-0.5 text-slate-600">Semantic color tokens, typography scale, spacing/grid foundations, reusable component specifications, and traceable design decisions.</p>
        <div className="mt-2 flex flex-wrap items-center gap-1.5" aria-label="Design System status">
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

      <Alert tone="warning" title="Design system provenance notice">
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
          <h2 className="font-semibold">No Design System yet</h2>
          <p className="text-sm text-slate-600">{state.next_step.label}</p>
          <Button variant="primary" loading={busy === "generate"} disabled={!!busy || !state.can_generate} onClick={() => void run("generate", () => designApi.generate<DesignSystemContent>(pid, "design_system", false), setOverride)}>
            {busy === "generate" ? "Generating…" : startLabel}
          </Button>
        </section>
      )}

      {doc && content && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {canEdit && doc.status === "approved" && (
              <p className="text-xs text-slate-600">This version is approved and immutable. Editing creates version {(state.history[0]?.version ?? doc.version) + 1} as a new draft.</p>
            )}
            {!readOnly && doc.status === "draft" && (
              <Button variant="primary" disabled={!!busy || !state.can_submit} loading={busy === "submit"} onClick={() => void run("submit", () => designApi.submit<DesignSystemContent>(pid, "design_system", doc.version, hash), setOverride)}>
                Submit for review
              </Button>
            )}
            {!readOnly && doc.status === "in_review" && (
              <Button variant="primary" disabled={!!busy || !state.can_approve} onClick={() => setModal("approve")}>
                Approve version {doc.version}
              </Button>
            )}
            {!readOnly && (
              <Button disabled={!!busy || !state.can_generate} loading={busy === "generate"} onClick={() => (state.needs_supersede ? setModal("regenerate") : void run("generate", () => designApi.generate<DesignSystemContent>(pid, "design_system", false), setOverride))}>
                {busy === "generate" ? "Generating…" : "Regenerate Design System"}
              </Button>
            )}
            {doc.status === "approved" && !doc.is_stale && (
              <Link to={`/projects/${pid}/prototype`} className="inline-flex h-9 items-center rounded-md border border-slate-300 bg-white px-3.5 text-sm font-medium hover:bg-slate-50">
                Continue to Interactive Prototype
              </Link>
            )}
          </div>

          {doc.status === "approved" && (
            <Alert tone="success" title={`Version ${doc.version} approved${doc.approved_at ? ` on ${formatDateTime(doc.approved_at)}` : ""}`}>
              {doc.approval_note}
            </Alert>
          )}
          {doc.warnings.length > 0 && !readOnly && (
            <Alert tone="warning" title="Design system warnings">
              <ul className="list-disc pl-5">{doc.warnings.map((w, i) => <li key={`${w.code}-${i}`}>{w.message}</li>)}</ul>
            </Alert>
          )}

          {/* 1. Foundations: Color Swatches & Typography Specimens */}
          <section aria-labelledby="ds-foundations-h" className="rounded-lg border border-slate-200 bg-white p-4 space-y-4">
            <h2 id="ds-foundations-h" className="text-base font-semibold">Foundations: Color Palette, Typography & Layout Grid</h2>
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Color tokens ({content.foundations.color_tokens.length})</h3>
              <ul className="mt-2 grid gap-2 sm:grid-cols-2" aria-label="Color tokens">
                {content.foundations.color_tokens.map((ct) => (
                  <li key={ct.token} className="flex items-start gap-3 rounded border border-slate-200 p-2.5 text-xs">
                    <span className="h-9 w-9 shrink-0 rounded border border-slate-300" style={{ backgroundColor: ct.hex_value }} aria-label={`Color swatch ${ct.hex_value}`} />
                    <div>
                      <div className="font-semibold text-slate-800">{ct.token} · <code>{ct.hex_value}</code></div>
                      <p className="text-slate-600">{ct.role} — {ct.usage}</p>
                      <p className="text-slate-500">Contrast: {ct.contrast_note}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Typography scale ({content.foundations.typography_scale.length})</h3>
              <ul className="mt-2 space-y-2" aria-label="Typography scale">
                {content.foundations.typography_scale.map((tt) => (
                  <li key={tt.token} className="rounded border border-slate-200 p-2.5 text-xs">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <span className="font-semibold text-slate-800">{tt.token} — {tt.role}</span>
                      <span className="text-slate-500">{tt.font_family} · {tt.font_size} / {tt.line_height} · weight {tt.font_weight}</span>
                    </div>
                    <p className="mt-1 text-slate-700" style={{ fontWeight: Number(tt.font_weight) || 400 }}>
                      Specimen: Scope baseline deliverables and client exclusions
                    </p>
                  </li>
                ))}
              </ul>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 text-xs">
              <div>
                <h3 className="font-semibold text-slate-600">Spacing scale</h3>
                <ul className="mt-1 list-disc pl-4 space-y-0.5">
                  {content.foundations.spacing_scale.map((sp) => <li key={sp.token}><code>{sp.token}</code> ({sp.value}): {sp.usage}</li>)}
                </ul>
              </div>
              <div>
                <h3 className="font-semibold text-slate-600">Grid & responsive breakpoints</h3>
                <p className="mt-1">{content.foundations.grid_breakpoints.columns} cols · gutter {content.foundations.grid_breakpoints.gutter} · max {content.foundations.grid_breakpoints.max_width}</p>
                <ul className="mt-1 list-disc pl-4 space-y-0.5">
                  <li>Desktop: {content.foundations.grid_breakpoints.desktop}</li>
                  <li>Tablet: {content.foundations.grid_breakpoints.tablet}</li>
                  <li>Mobile: {content.foundations.grid_breakpoints.mobile}</li>
                </ul>
              </div>
            </div>
          </section>

          {/* 2. Component Library */}
          <section aria-labelledby="ds-components-h" className="space-y-3">
            <h2 id="ds-components-h" className="text-base font-semibold">Component library ({content.components.length})</h2>
            <ul className="space-y-2" aria-label="Component specifications">
              {content.components.map((c) => (
                <li key={c.id} className="rounded-lg border border-slate-200 bg-white p-4 space-y-1.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge>{c.id}</Badge>
                      <span className="font-semibold">{c.name}</span>
                      <Badge tone="info">{c.category.replace("_", " ")}</Badge>
                    </div>
                  </div>
                  <p className="text-sm text-slate-700">{c.purpose}</p>
                  <p className="text-xs text-slate-600"><strong>Variants:</strong> {c.variants.join(", ")} · <strong>States:</strong> {c.states.join(", ")}</p>
                  <p className="text-xs text-slate-600"><strong>Tokens used:</strong> {c.design_tokens_used.join(", ")}</p>
                  <p className="text-xs text-slate-600"><strong>Responsive:</strong> {c.responsive_behavior} · <strong>Accessibility:</strong> {c.accessibility_notes}</p>
                  <p className="text-xs text-slate-500">Wireframes: {c.wireframe_ids.join(", ")} · PRD: {c.prd_requirement_ids.join(", ")}</p>
                </li>
              ))}
            </ul>
          </section>

          {/* 3. Design Decisions */}
          <section aria-labelledby="ds-decisions-h" className="space-y-2 rounded-lg border border-slate-200 bg-white p-4">
            <h2 id="ds-decisions-h" className="text-base font-semibold">Design decisions ({content.decisions.length})</h2>
            <ul className="space-y-2" aria-label="Design decisions">
              {content.decisions.map((d) => (
                <li key={d.id} className="rounded border border-slate-200 p-3 space-y-1">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge>{d.id}</Badge>
                      <span className="font-semibold text-sm">{d.title}</span>
                      <Badge tone={d.status === "approved" ? "success" : d.status === "reviewed" ? "info" : "warning"}>
                        {d.status}
                      </Badge>
                    </div>
                    {canEdit && d.status !== "approved" && (
                      <Button
                        size="sm"
                        disabled={!!busy}
                        onClick={() => void run("edit", () => designApi.patchDecision(pid, doc.version, hash, d.id, { status: "approved" }), applyEdit)}
                      >
                        Approve {d.id}
                      </Button>
                    )}
                  </div>
                  <p className="text-xs text-slate-800"><strong>Rule:</strong> {d.chosen_value_or_rule}</p>
                  <p className="text-xs text-slate-600"><strong>Rationale:</strong> {d.rationale}</p>
                  <p className="text-xs text-slate-500">Supporting refs: {d.supporting_refs.join(", ")}</p>
                  {d.note && <p className="text-xs text-amber-800">{d.note}</p>}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}

      {modal === "regenerate" && (
        <ConfirmDialog title="Regenerate Design System?" confirmLabel="Regenerate" onClose={() => setModal(null)}
          body={<p>A new version will be generated. The current draft stays in history as superseded.</p>}
          onConfirm={async () => { setModal(null); void run("generate", () => designApi.generate<DesignSystemContent>(pid, "design_system", true), setOverride); }} />
      )}
      {modal === "approve" && doc && (
        <DsApproveDialog unverified={doc.unverified_count} onClose={() => setModal(null)}
          onSubmit={async (ack, note) => {
            const next = await designApi.approve<DesignSystemContent>(pid, "design_system", doc.version, hash, ack, note);
            setOverride(next);
            setModal(null);
          }} />
      )}
    </div>
  );
}

function DsApproveDialog({ unverified, onSubmit, onClose }: { unverified: number; onSubmit: (ack: boolean, note: string) => Promise<void>; onClose: () => void }) {
  const [ack, setAck] = useState(false);
  const [note, setNote] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  return (
    <Dialog title="Approve Design System version" onClose={onClose}>
      <form noValidate className="space-y-3" onSubmit={async (e) => { e.preventDefault(); setBusy(true); setErrors([]); try { await onSubmit(ack, note); } catch (err) { setErrors(messagesOf(err)); setBusy(false); } }}>
        {errors.length > 0 && <Alert tone="error">{errors.map((m) => <p key={m}>{m}</p>)}</Alert>}
        <p className="text-sm">Approving locks this exact Design System version in your Project Brain and unlocks the Interactive Prototype.</p>
        {unverified > 0 && (
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-0.5 h-4 w-4" checked={ack} onChange={(e) => setAck(e.target.checked)} />
            <span>I understand that {unverified} design decision(s) are still marked proposed or have open assumptions.</span>
          </label>
        )}
        <TextAreaField label="Approval note (optional)" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        <div className="flex justify-end gap-2">
          <Button onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" variant="primary" loading={busy} disabled={unverified > 0 && !ack}>Approve Design System</Button>
        </div>
      </form>
    </Dialog>
  );
}
