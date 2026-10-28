import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorState, LoadingState } from "../components/feedback/States";
import { Alert } from "../components/ui/Alert";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { TextAreaField, TextField } from "../components/ui/Fields";
import { architectureApi } from "../features/architecture/api";
import { ConfirmDialog } from "../features/research/Dialogs";
import { STATUS } from "../features/research/labels";
import { ApiError } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import { formatDateTime } from "../lib/utils";
import type {
  ArchitectureComponent,
  ArchitectureContent,
  ArchitectureDecision,
  ArchitectureDiagram,
  ArchitectureDocument,
  ArchitectureEditResponse,
  ArchitectureState,
  ApiBoundarySpec,
  ComponentLayer,
  DecisionStatus,
  DomainEntity,
  EntityDecisionStatus,
} from "../types/architecture";
import { useProject } from "./ProjectLayout";

type Notice = { tone: "error" | "warning" | "success"; title: string; body?: string };

function describe(e: unknown): Notice {
  if (e instanceof ApiError) {
    if (e.status === 503) {
      return { tone: "warning", title: "AI analysis is not configured yet.", body: "Nothing was changed." };
    }
    if (e.status === 502) {
      return {
        tone: "error",
        title: "WebForge couldn't produce a valid Product Architecture.",
        body: `${e.message} Nothing was changed.`,
      };
    }
    return { tone: "error", title: e.message };
  }
  return { tone: "error", title: "Something went wrong." };
}

const DIAGRAM_TYPE_LABELS: Record<string, string> = {
  system_context: "System Context",
  component: "Component Topology",
  data_relationship: "Data Relationships",
  request_flow: "Request / Data Flow",
  deployment: "Deployment & Runtime",
};

export default function ArchitecturePage() {
  const { project } = useProject();
  const pid = project.id;
  const load = useAsync(() => architectureApi.get(pid), [pid]);
  const [override, setOverride] = useState<ArchitectureState>();
  const [viewing, setViewing] = useState<number | null>(null);
  const viewed = useAsync(
    () => (viewing ? architectureApi.version(pid, viewing) : Promise.resolve(null)),
    [pid, viewing]
  );
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef<string | null>(null);
  const [modal, setModal] = useState<"regenerate" | "approve" | null>(null);
  const [activeDiagramId, setActiveDiagramId] = useState<string | null>(null);

  const state = override ?? load.data;

  async function run<T>(key: string, fn: () => Promise<T>, onDone: (r: T) => void) {
    if (busyRef.current) return;
    busyRef.current = key;
    setBusy(key);
    setNotice(null);
    try {
      onDone(await fn());
    } catch (e) {
      setNotice(describe(e));
    } finally {
      busyRef.current = null;
      setBusy(null);
    }
  }

  if (load.loading && !state) return <LoadingState label="Loading Product Architecture…" />;
  if (!state) {
    return (
      <ErrorState
        message={load.error?.message ?? "We couldn't load the Product Architecture."}
        onRetry={load.reload}
      />
    );
  }

  const doc: ArchitectureDocument | null = viewing ? (viewed.data ?? null) : state.current;
  const content = doc?.content ?? null;
  const hash = doc?.content_hash ?? "";
  const readOnly = viewing !== null;
  const canEdit = !readOnly && !!doc && ["draft", "in_review", "approved"].includes(doc.status);

  const applyEdit = (r: ArchitectureEditResponse) => {
    setOverride(r.state);
    if (r.document.version !== doc?.version) {
      setNotice({
        tone: "success",
        title: `Saved as new draft version ${r.document.version}.`,
      });
    } else {
      setNotice({ tone: "success", title: "Architecture changes saved." });
    }
  };

  const startLabel =
    state.status === "not_started"
      ? "Generate Product Architecture"
      : state.status === "failed"
      ? "Retry generating Architecture"
      : "Regenerate Architecture";

  const selectedDiagram: ArchitectureDiagram | null = content
    ? content.diagrams.find((d) => d.id === activeDiagramId) ?? content.diagrams[0] ?? null
    : null;

  return (
    <div className="max-w-5xl space-y-4">
      <header>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-xl font-semibold">Product Architecture</h1>
          <nav aria-label="Architecture and Design workspaces" className="flex flex-wrap gap-1.5 text-xs">
            <Link
              to={`/projects/${pid}/design-system`}
              className="rounded border border-slate-200 bg-white px-2.5 py-1 hover:bg-slate-50"
            >
              Design System
            </Link>
            <Link
              to={`/projects/${pid}/prototype`}
              className="rounded border border-slate-200 bg-white px-2.5 py-1 hover:bg-slate-50"
            >
              Interactive Prototype
            </Link>
            <Link
              to={`/projects/${pid}/architecture`}
              className="rounded border border-slate-300 bg-slate-100 px-2.5 py-1 font-medium"
            >
              1. Architecture
            </Link>
          </nav>
        </div>
        <p className="mt-0.5 text-slate-600">
          Concrete system boundaries, application modules, domain data entities, API contracts, deployment topology,
          technical decision records (ADRs), validated diagrams, and end-to-end PRD traceability.
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-1.5" aria-label="Architecture status">
          <Badge tone={STATUS[(doc?.status ?? state.status) as keyof typeof STATUS].tone}>
            {STATUS[(doc?.status ?? state.status) as keyof typeof STATUS].label}
          </Badge>
          {doc && <Badge>Version {doc.version}</Badge>}
          {doc?.is_stale && <Badge tone="warning">Stale upstream</Badge>}
          <Badge tone={state.lifecycle.status === "complete" ? "success" : "neutral"}>
            Architecture stage: {state.lifecycle.status.replace("_", " ")}
          </Badge>
          {state.approved_version !== null && (
            <Badge tone="success">Approved version: {state.approved_version}</Badge>
          )}
          {doc?.completeness && (
            <Badge tone={doc.completeness.complete_traceability ? "success" : "warning"}>
              Traceability: {doc.completeness.traced_requirements}/{doc.completeness.total_requirements} requirements
            </Badge>
          )}
        </div>
      </header>

      <Alert tone="warning" title="Architecture provenance & scope notice">
        <ul className="list-disc pl-5">
          {state.limitations.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      </Alert>

      {notice && (
        <Alert tone={notice.tone} title={notice.title}>
          {notice.body}
        </Alert>
      )}

      {!state.prerequisites.ready && (
        <section
          aria-label="Prerequisite gates"
          className="rounded-lg border border-amber-300 bg-amber-50 p-4 space-y-2"
        >
          <h2 className="font-semibold text-amber-900">Upstream prerequisites required</h2>
          <p className="text-xs text-amber-800">
            Product Architecture requires approved, current Research, Strategy, PRD, UX, Design System, and Interactive
            Prototype artifacts.
          </p>
          <ul className="space-y-2">
            {state.prerequisites.missing.map((m) => (
              <li
                key={m.artifact}
                className="flex flex-wrap items-center justify-between gap-2 rounded border border-amber-200 bg-white p-2.5 text-sm"
              >
                <span>
                  <strong>{m.label}:</strong> {m.message}
                </span>
                <Link
                  to={m.workspace_path}
                  className="inline-flex h-8 items-center rounded-md border border-slate-300 bg-white px-3 text-xs font-medium hover:bg-slate-50"
                >
                  Go to {m.label}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {!doc && !viewing && state.prerequisites.ready && (
        <section className="rounded-lg border border-slate-200 bg-white p-5 space-y-3">
          <h2 className="font-semibold">No Product Architecture yet</h2>
          <p className="text-sm text-slate-600">{state.next_step.label}</p>
          {state.last_error && (
            <Alert tone="error" title="Last generation attempt failed">
              {state.last_error}
            </Alert>
          )}
          <Button
            variant="primary"
            loading={busy === "generate"}
            disabled={!!busy || !state.can_generate}
            onClick={() =>
              void run("generate", () => architectureApi.generate(pid, false), setOverride)
            }
          >
            {busy === "generate" ? "Generating…" : startLabel}
          </Button>
        </section>
      )}

      {doc && content && (
        <>
          {viewing !== null && (
            <Alert tone="warning" title={`Viewing historical version ${doc.version} (read-only)`}>
              <Button variant="secondary" onClick={() => setViewing(null)}>
                Return to current version
              </Button>
            </Alert>
          )}

          {doc.warnings.length > 0 && (
            <Alert tone="warning" title="Architecture warnings & review items">
              <ul className="list-disc pl-5">
                {doc.warnings.map((w, i) => (
                  <li key={`${w.code}-${i}`}>{w.message}</li>
                ))}
              </ul>
            </Alert>
          )}

          {/* Action Bar & Provenance Bar */}
          <section
            aria-label="Architecture workflow actions"
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white p-3.5"
          >
            <div className="space-y-1">
              <p className="text-sm font-medium">{state.next_step.label}</p>
              <p className="text-xs text-slate-500">
                Source basis: Research v{content.basis.research_version} · Strategy v{content.basis.strategy_version} ·
                PRD v{content.basis.prd_version} · Personas v{content.basis.personas_version} · Journeys v
                {content.basis.journeys_version} · IA v{content.basis.ia_version} · Wireframes v
                {content.basis.wireframes_version} · UX Review v{content.basis.ux_review_version} · Design System v
                {content.basis.design_system_version} · Prototype v{content.basis.prototype_version}
              </p>
            </div>
            {!readOnly && (
              <div className="flex flex-wrap gap-2">
                {doc.status === "draft" && (
                  <Button
                    variant="primary"
                    loading={busy === "submit"}
                    disabled={!!busy || !state.can_submit}
                    onClick={() =>
                      void run("submit", () => architectureApi.submit(pid, doc.version, hash), setOverride)
                    }
                  >
                    Submit for review
                  </Button>
                )}
                {doc.status === "in_review" && (
                  <Button
                    variant="primary"
                    disabled={!!busy || !state.can_approve}
                    onClick={() => setModal("approve")}
                  >
                    Approve Architecture
                  </Button>
                )}
                <Button
                  variant="secondary"
                  disabled={!!busy || !state.can_generate}
                  onClick={() =>
                    state.needs_supersede
                      ? setModal("regenerate")
                      : void run("generate", () => architectureApi.generate(pid, false), setOverride)
                  }
                >
                  Regenerate Architecture
                </Button>
              </div>
            )}
          </section>

          {/* A. System Overview, Roles, Components, and External Integrations */}
          <SystemOverviewSection
            pid={pid}
            version={doc.version}
            hash={hash}
            overview={content.system_overview}
            canEdit={canEdit}
            busy={busy}
            run={run}
            onSaved={applyEdit}
          />

          {/* B. Application Architecture */}
          <ApplicationArchitectureSection
            pid={pid}
            version={doc.version}
            hash={hash}
            appArch={content.application_architecture}
            canEdit={canEdit}
            busy={busy}
            run={run}
            onSaved={applyEdit}
          />

          {/* C. Data Architecture */}
          <DataArchitectureSection
            pid={pid}
            version={doc.version}
            hash={hash}
            dataArch={content.data_architecture}
            canEdit={canEdit}
            busy={busy}
            run={run}
            onSaved={applyEdit}
          />

          {/* D. API & Integration Architecture */}
          <ApiArchitectureSection
            pid={pid}
            version={doc.version}
            hash={hash}
            apiArch={content.api_architecture}
            canEdit={canEdit}
            busy={busy}
            run={run}
            onSaved={applyEdit}
          />

          {/* E. Deployment & Operational Architecture */}
          <DeploymentArchitectureSection
            pid={pid}
            version={doc.version}
            hash={hash}
            deployArch={content.deployment_architecture}
            canEdit={canEdit}
            busy={busy}
            run={run}
            onSaved={applyEdit}
          />

          {/* F. Technical Decisions (ADRs) */}
          <DecisionsSection
            pid={pid}
            version={doc.version}
            hash={hash}
            decisions={content.decisions}
            canEdit={canEdit}
            busy={busy}
            run={run}
            onSaved={applyEdit}
          />

          {/* G. Architecture Diagrams Viewer */}
          <DiagramsSection
            pid={pid}
            version={doc.version}
            hash={hash}
            diagrams={content.diagrams}
            selected={selectedDiagram}
            onSelect={(id) => setActiveDiagramId(id)}
            canEdit={canEdit}
            busy={busy}
            run={run}
            onSaved={applyEdit}
          />

          {/* H. Requirement Traceability Matrix */}
          <section
            aria-label="Requirement traceability matrix"
            className="rounded-lg border border-slate-200 bg-white p-4 space-y-3"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="font-semibold">Requirement Traceability Matrix</h2>
                <p className="text-xs text-slate-500">
                  PRD Requirement → Architecture Component → Data / API / Service Boundary → Approved Design / Prototype
                </p>
              </div>
              {doc.completeness && (
                <Badge tone={doc.completeness.complete_traceability ? "success" : "warning"}>
                  {doc.completeness.complete_traceability
                    ? "100% PRD Requirements Traced"
                    : `${doc.completeness.uncovered_requirements.length} Requirement(s) Missing Full Coverage`}
                </Badge>
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-slate-700">
                    <th className="p-2">PRD Req</th>
                    <th className="p-2">Components</th>
                    <th className="p-2">Data / API / Backend</th>
                    <th className="p-2">Design / Prototype Refs</th>
                    <th className="p-2">ADRs</th>
                    <th className="p-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {content.traceability.map((row) => (
                    <tr key={row.requirement_id}>
                      <td className="p-2 font-medium">
                        <div>{row.requirement_id}</div>
                        <div className="font-normal text-slate-500">{row.requirement_title}</div>
                      </td>
                      <td className="p-2">{row.component_ids.join(", ") || "—"}</td>
                      <td className="p-2">
                        {[...row.entity_ids, ...row.endpoint_ids, ...row.backend_module_ids, ...row.integration_ids].join(
                          ", "
                        ) || "—"}
                      </td>
                      <td className="p-2">{row.design_refs.join(", ") || "—"}</td>
                      <td className="p-2">{row.decision_ids.join(", ") || "—"}</td>
                      <td className="p-2">
                        {row.fully_traced ? (
                          <Badge tone="success">Traced</Badge>
                        ) : (
                          <div className="space-y-1">
                            <Badge tone="warning">Coverage gap</Badge>
                            {row.coverage_gaps.map((g) => (
                              <div key={g} className="text-[11px] text-amber-800">
                                {g}
                              </div>
                            ))}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* Version History */}
          {state.history.length > 0 && (
            <section
              aria-label="Architecture version history"
              className="rounded-lg border border-slate-200 bg-white p-4 space-y-2"
            >
              <h2 className="font-semibold">Version History</h2>
              <ul className="divide-y divide-slate-200 text-sm">
                {state.history.map((hItem) => (
                  <li key={hItem.version} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">Version {hItem.version}</span>
                      <Badge tone={STATUS[hItem.status].tone}>{STATUS[hItem.status].label}</Badge>
                      <span className="text-xs text-slate-500">
                        {hItem.created_via.replace(/_/g, " ")} ·{" "}
                        {hItem.updated_at ? formatDateTime(hItem.updated_at) : "—"}
                      </span>
                    </div>
                    {doc.version !== hItem.version ? (
                      <Button variant="secondary" onClick={() => setViewing(hItem.version)}>
                        View v{hItem.version}
                      </Button>
                    ) : (
                      <span className="text-xs font-medium text-slate-500">Current view</span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      {modal === "regenerate" && (
        <ConfirmDialog
          title="Supersede current draft and regenerate?"
          body="Your existing draft version will remain in version history as superseded, and a new Product Architecture draft will be generated from your current approved artifacts."
          confirmLabel="Supersede & regenerate"
          busy={busy === "generate"}
          onCancel={() => setModal(null)}
          onConfirm={() =>
            run(
              "generate",
              () => architectureApi.generate(pid, true),
              (s) => {
                setOverride(s);
                setModal(null);
              }
            )
          }
        />
      )}

      {modal === "approve" && doc && (
        <ApproveArchitectureModal
          unverifiedCount={doc.unverified_count}
          busy={busy === "approve"}
          onCancel={() => setModal(null)}
          onConfirm={(ack, note) =>
            run(
              "approve",
              () => architectureApi.approve(pid, doc.version, hash, ack, note),
              (s) => {
                setOverride(s);
                setModal(null);
              }
            )
          }
        />
      )}
    </div>
  );
}

function SystemOverviewSection({
  pid,
  version,
  hash,
  overview,
  canEdit,
  busy,
  run,
  onSaved,
}: {
  pid: string;
  version: number;
  hash: string;
  overview: ArchitectureContent["system_overview"];
  canEdit: boolean;
  busy: string | null;
  run: <T>(key: string, fn: () => Promise<T>, onDone: (r: T) => void) => Promise<void>;
  onSaved: (r: ArchitectureEditResponse) => void;
}) {
  const [editingScope, setEditingScope] = useState(false);
  const [scope, setScope] = useState(overview.product_scope);
  const [editingComp, setEditingComp] = useState<string | null>(null);
  const [compName, setCompName] = useState("");
  const [compPurpose, setCompPurpose] = useState("");
  const [addingComp, setAddingComp] = useState(false);
  const [newComp, setNewComp] = useState({
    name: "",
    layer: "backend" as ComponentLayer,
    purpose: "",
    responsibilities: "",
    communicates_with: "",
    prd_requirement_ids: "",
    design_refs: "",
  });

  function startEditComp(c: ArchitectureComponent) {
    setEditingComp(c.id);
    setCompName(c.name);
    setCompPurpose(c.purpose);
  }

  return (
    <section
      aria-label="System overview and components"
      className="rounded-lg border border-slate-200 bg-white p-4 space-y-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-semibold">A. System Overview & Component Inventory</h2>
          <p className="text-xs text-slate-500">
            Product scope, system boundaries, trust zones, major components, and external integrations.
          </p>
        </div>
        {canEdit && !editingScope && (
          <Button
            variant="secondary"
            onClick={() => {
              setScope(overview.product_scope);
              setEditingScope(true);
            }}
          >
            Edit system scope
          </Button>
        )}
      </div>

      {editingScope ? (
        <div className="space-y-2 rounded border border-slate-200 bg-slate-50 p-3">
          <TextAreaField
            id="arch-product-scope"
            label="Product scope"
            rows={3}
            value={scope}
            onChange={(e) => setScope(e.target.value)}
          />
          <div className="flex gap-2">
            <Button
              variant="primary"
              loading={busy === "patch-scope"}
              onClick={() =>
                void run(
                  "patch-scope",
                  () => architectureApi.patchOverview(pid, version, hash, { product_scope: scope }),
                  (r) => {
                    onSaved(r);
                    setEditingScope(false);
                  }
                )
              }
            >
              Save scope
            </Button>
            <Button variant="secondary" onClick={() => setEditingScope(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <p className="text-sm text-slate-700">{overview.product_scope}</p>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded border border-slate-200 p-3 space-y-1.5">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">System Boundaries</h3>
          <ul className="list-disc pl-5 text-xs text-slate-700 space-y-1">
            {overview.system_boundaries.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </div>
        <div className="rounded border border-slate-200 p-3 space-y-1.5">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            User Roles & Trust Boundaries
          </h3>
          <ul className="space-y-2 text-xs">
            {overview.user_roles_and_trust_boundaries.map((r) => (
              <li key={r.role} className="rounded bg-slate-50 p-2">
                <div className="flex flex-wrap items-center justify-between gap-1 font-medium">
                  <span>
                    {r.role} ({r.persona_ids.join(", ")})
                  </span>
                  <Badge>{r.trust_zone.replace(/_/g, " ")}</Badge>
                </div>
                <p className="mt-1 text-slate-600">{r.allowed_capabilities.join(" · ")}</p>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">
            Architecture Components ({overview.components.length})
          </h3>
          {canEdit && !addingComp && (
            <Button variant="secondary" onClick={() => setAddingComp(true)}>
              Add component
            </Button>
          )}
        </div>

        {addingComp && (
          <div className="rounded border border-slate-200 bg-slate-50 p-3 space-y-2">
            <div className="grid gap-2 sm:grid-cols-2">
              <TextField
                id="new-comp-name"
                label="Component name"
                value={newComp.name}
                onChange={(e) => setNewComp({ ...newComp, name: e.target.value })}
              />
              <div>
                <label htmlFor="new-comp-layer" className="block text-sm font-medium text-slate-700">
                  Layer
                </label>
                <select
                  id="new-comp-layer"
                  className="mt-1 h-9 w-full rounded-md border border-slate-300 bg-white px-2 text-sm"
                  value={newComp.layer}
                  onChange={(e) => setNewComp({ ...newComp, layer: e.target.value as ComponentLayer })}
                >
                  <option value="frontend">frontend</option>
                  <option value="backend">backend</option>
                  <option value="data">data</option>
                  <option value="integration">integration</option>
                  <option value="infrastructure">infrastructure</option>
                </select>
              </div>
            </div>
            <TextAreaField
              id="new-comp-purpose"
              label="Purpose"
              rows={2}
              value={newComp.purpose}
              onChange={(e) => setNewComp({ ...newComp, purpose: e.target.value })}
            />
            <div className="grid gap-2 sm:grid-cols-2">
              <TextField
                id="new-comp-resp"
                label="Responsibilities (comma-separated)"
                value={newComp.responsibilities}
                onChange={(e) => setNewComp({ ...newComp, responsibilities: e.target.value })}
              />
              <TextField
                id="new-comp-reqs"
                label="PRD Requirement IDs (comma-separated)"
                value={newComp.prd_requirement_ids}
                onChange={(e) => setNewComp({ ...newComp, prd_requirement_ids: e.target.value })}
              />
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <TextField
                id="new-comp-comm"
                label="Communicates with (COMP-*/INT-*, comma-separated)"
                value={newComp.communicates_with}
                onChange={(e) => setNewComp({ ...newComp, communicates_with: e.target.value })}
              />
              <TextField
                id="new-comp-drefs"
                label="Design/UX refs (SCR-*/CMP-*/WF-*, comma-separated)"
                value={newComp.design_refs}
                onChange={(e) => setNewComp({ ...newComp, design_refs: e.target.value })}
              />
            </div>
            <div className="flex gap-2">
              <Button
                variant="primary"
                loading={busy === "add-comp"}
                onClick={() =>
                  void run(
                    "add-comp",
                    () =>
                      architectureApi.addComponent(pid, version, hash, {
                        name: newComp.name,
                        layer: newComp.layer,
                        purpose: newComp.purpose,
                        responsibilities: newComp.responsibilities
                          .split(",")
                          .map((s) => s.trim())
                          .filter(Boolean),
                        communicates_with: newComp.communicates_with
                          .split(",")
                          .map((s) => s.trim())
                          .filter(Boolean),
                        prd_requirement_ids: newComp.prd_requirement_ids
                          .split(",")
                          .map((s) => s.trim())
                          .filter(Boolean),
                        design_refs: newComp.design_refs
                          .split(",")
                          .map((s) => s.trim())
                          .filter(Boolean),
                      }),
                    (r) => {
                      onSaved(r);
                      setAddingComp(false);
                    }
                  )
                }
              >
                Create component
              </Button>
              <Button variant="secondary" onClick={() => setAddingComp(false)}>
                Cancel
              </Button>
            </div>
          </div>
        )}

        <div className="grid gap-2.5 md:grid-cols-2">
          {overview.components.map((c) => (
            <div key={c.id} className="rounded border border-slate-200 p-3 space-y-2 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-1">
                <div className="font-semibold text-sm">
                  {c.id}: {c.name}
                </div>
                <Badge>{c.layer}</Badge>
              </div>
              {editingComp === c.id ? (
                <div className="space-y-2 pt-1">
                  <TextField
                    id={`edit-comp-name-${c.id}`}
                    label="Component name"
                    value={compName}
                    onChange={(e) => setCompName(e.target.value)}
                  />
                  <TextAreaField
                    id={`edit-comp-purpose-${c.id}`}
                    label="Component purpose"
                    rows={2}
                    value={compPurpose}
                    onChange={(e) => setCompPurpose(e.target.value)}
                  />
                  <div className="flex gap-2">
                    <Button
                      variant="primary"
                      loading={busy === `comp-${c.id}`}
                      onClick={() =>
                        void run(
                          `comp-${c.id}`,
                          () =>
                            architectureApi.patchComponent(pid, version, hash, c.id, {
                              name: compName,
                              purpose: compPurpose,
                            }),
                          (r) => {
                            onSaved(r);
                            setEditingComp(null);
                          }
                        )
                      }
                    >
                      Save component
                    </Button>
                    <Button variant="secondary" onClick={() => setEditingComp(null)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <>
                  <p className="text-slate-600">{c.purpose}</p>
                  <ul className="list-disc pl-4 text-slate-700 space-y-0.5">
                    {c.responsibilities.map((resp) => (
                      <li key={resp}>{resp}</li>
                    ))}
                  </ul>
                  <div className="flex flex-wrap gap-1.5 text-[11px] text-slate-500">
                    <span>PRD: {c.prd_requirement_ids.join(", ")}</span>
                    {c.communicates_with.length > 0 && <span>· Calls: {c.communicates_with.join(", ")}</span>}
                    {c.design_refs.length > 0 && <span>· Design: {c.design_refs.join(", ")}</span>}
                  </div>
                  {canEdit && (
                    <Button variant="secondary" onClick={() => startEditComp(c)}>
                      Edit {c.id}
                    </Button>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      </div>

      {overview.external_integrations.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">
            External Integrations ({overview.external_integrations.length})
          </h3>
          <div className="grid gap-2 md:grid-cols-2">
            {overview.external_integrations.map((ext) => (
              <div key={ext.id} className="rounded border border-slate-200 p-3 text-xs space-y-1">
                <div className="flex items-center justify-between gap-2 font-medium">
                  <span>
                    {ext.id}: {ext.name}
                  </span>
                  <Badge tone={ext.implementation_status === "verified_existing" ? "success" : "warning"}>
                    {ext.implementation_status.replace(/_/g, " ")}
                  </Badge>
                </div>
                <p className="text-slate-600">{ext.purpose}</p>
                <p className="text-slate-500">
                  <strong>Contract:</strong> {ext.protocol_or_contract}
                </p>
                <p className="text-slate-500">
                  <strong>Failure / fallback:</strong> {ext.failure_mode_and_fallback}
                </p>
                <p className="text-[11px] text-slate-500">PRD: {ext.prd_requirement_ids.join(", ")}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function ApplicationArchitectureSection({
  pid,
  version,
  hash,
  appArch,
  canEdit,
  busy,
  run,
  onSaved,
}: {
  pid: string;
  version: number;
  hash: string;
  appArch: NonNullable<NonNullable<ArchitectureState["current"]>["content"]>["application_architecture"];
  canEdit: boolean;
  busy: string | null;
  run: <T>(key: string, fn: () => Promise<T>, onDone: (r: T) => void) => Promise<void>;
  onSaved: (r: ArchitectureEditResponse) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [authFlow, setAuthFlow] = useState(appArch.authentication_and_authorization);
  const [stateMgmt, setStateMgmt] = useState(appArch.state_management_and_data_fetching);

  return (
    <section
      aria-label="Application architecture"
      className="rounded-lg border border-slate-200 bg-white p-4 space-y-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-semibold">B. Application Architecture</h2>
          <p className="text-xs text-slate-500">
            Frontend feature modules, backend services, auth/authz flows, state management, error handling, and config.
          </p>
        </div>
        {canEdit && !editing && (
          <Button
            variant="secondary"
            onClick={() => {
              setAuthFlow(appArch.authentication_and_authorization);
              setStateMgmt(appArch.state_management_and_data_fetching);
              setEditing(true);
            }}
          >
            Edit application policies
          </Button>
        )}
      </div>

      {editing && (
        <div className="rounded border border-slate-200 bg-slate-50 p-3 space-y-2">
          <TextAreaField
            id="app-auth-flow"
            label="Authentication & Authorization"
            rows={2}
            value={authFlow}
            onChange={(e) => setAuthFlow(e.target.value)}
          />
          <TextAreaField
            id="app-state-mgmt"
            label="State Management & Data Fetching"
            rows={2}
            value={stateMgmt}
            onChange={(e) => setStateMgmt(e.target.value)}
          />
          <div className="flex gap-2">
            <Button
              variant="primary"
              loading={busy === "patch-app"}
              onClick={() =>
                void run(
                  "patch-app",
                  () =>
                    architectureApi.patchApplication(pid, version, hash, {
                      authentication_and_authorization: authFlow,
                      state_management_and_data_fetching: stateMgmt,
                    }),
                  (r) => {
                    onSaved(r);
                    setEditing(false);
                  }
                )
              }
            >
              Save application policies
            </Button>
            <Button variant="secondary" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Frontend Feature Boundaries ({appArch.frontend_boundaries.length})
          </h3>
          {appArch.frontend_boundaries.map((fe) => (
            <div key={fe.id} className="rounded border border-slate-200 p-2.5 text-xs space-y-1">
              <div className="flex items-center justify-between font-medium">
                <span>
                  {fe.id}: {fe.module_name}
                </span>
                <Badge>{fe.component_id}</Badge>
              </div>
              <p className="text-slate-600">{fe.route_or_feature_scope}</p>
              <p className="text-[11px] text-slate-500">
                Screens: {fe.prototype_screen_ids.join(", ")} · Design Components: {fe.design_component_ids.join(", ")}{" "}
                · Tokens: {fe.design_tokens_used.join(", ")} · PRD: {fe.prd_requirement_ids.join(", ")}
              </p>
            </div>
          ))}
        </div>

        <div className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Backend Service Modules ({appArch.backend_modules.length})
          </h3>
          {appArch.backend_modules.map((be) => (
            <div key={be.id} className="rounded border border-slate-200 p-2.5 text-xs space-y-1">
              <div className="flex items-center justify-between font-medium">
                <span>
                  {be.id}: {be.module_name}
                </span>
                <Badge>{be.component_id}</Badge>
              </div>
              <p className="text-slate-600">{be.service_responsibility}</p>
              <p className="text-[11px] text-slate-500">PRD: {be.prd_requirement_ids.join(", ")}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-2 text-xs md:grid-cols-2">
        <div className="rounded bg-slate-50 p-2.5">
          <strong>Authentication & Authorization:</strong> {appArch.authentication_and_authorization}
        </div>
        <div className="rounded bg-slate-50 p-2.5">
          <strong>State & Data Fetching:</strong> {appArch.state_management_and_data_fetching}
        </div>
        <div className="rounded bg-slate-50 p-2.5">
          <strong>Error Handling & Logging:</strong> {appArch.error_handling_and_logging}
        </div>
        <div className="rounded bg-slate-50 p-2.5">
          <strong>Config & Environment Separation:</strong> {appArch.configuration_and_env_separation}
        </div>
      </div>
    </section>
  );
}

function DataArchitectureSection({
  pid,
  version,
  hash,
  dataArch,
  canEdit,
  busy,
  run,
  onSaved,
}: {
  pid: string;
  version: number;
  hash: string;
  dataArch: NonNullable<NonNullable<ArchitectureState["current"]>["content"]>["data_architecture"];
  canEdit: boolean;
  busy: string | null;
  run: <T>(key: string, fn: () => Promise<T>, onDone: (r: T) => void) => Promise<void>;
  onSaved: (r: ArchitectureEditResponse) => void;
}) {
  const [editingEnt, setEditingEnt] = useState<string | null>(null);
  const [entDesc, setEntDesc] = useState("");
  const [entStatus, setEntStatus] = useState<EntityDecisionStatus>("approved_scope");

  function startEditEnt(e: DomainEntity) {
    setEditingEnt(e.id);
    setEntDesc(e.description);
    setEntStatus(e.status);
  }

  return (
    <section
      aria-label="Data architecture"
      className="rounded-lg border border-slate-200 bg-white p-4 space-y-3"
    >
      <div>
        <h2 className="font-semibold">C. Data Architecture</h2>
        <p className="text-xs text-slate-500">
          PRD-backed domain entities, entity ownership, relationships, access boundaries, retention, and migration rules.
        </p>
      </div>

      <div className="grid gap-2.5 md:grid-cols-2">
        {dataArch.entities.map((ent) => (
          <div key={ent.id} className="rounded border border-slate-200 p-3 text-xs space-y-1.5">
            <div className="flex flex-wrap items-center justify-between gap-1">
              <span className="font-semibold text-sm">
                {ent.id}: {ent.name}
              </span>
              <div className="flex gap-1">
                <Badge>{ent.owning_component_id}</Badge>
                <Badge tone={ent.status === "approved_scope" ? "success" : "warning"}>
                  {ent.status.replace(/_/g, " ")}
                </Badge>
              </div>
            </div>
            {editingEnt === ent.id ? (
              <div className="space-y-2 pt-1">
                <TextAreaField
                  id={`edit-ent-desc-${ent.id}`}
                  label="Entity description"
                  rows={2}
                  value={entDesc}
                  onChange={(e) => setEntDesc(e.target.value)}
                />
                <div>
                  <label htmlFor={`edit-ent-status-${ent.id}`} className="block text-xs font-medium text-slate-700">
                    Entity status
                  </label>
                  <select
                    id={`edit-ent-status-${ent.id}`}
                    className="mt-1 h-8 w-full rounded border border-slate-300 bg-white px-2 text-xs"
                    value={entStatus}
                    onChange={(e) => setEntStatus(e.target.value as EntityDecisionStatus)}
                  >
                    <option value="approved_scope">approved_scope</option>
                    <option value="proposed">proposed</option>
                    <option value="requires_review">requires_review</option>
                  </select>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="primary"
                    loading={busy === `ent-${ent.id}`}
                    onClick={() =>
                      void run(
                        `ent-${ent.id}`,
                        () =>
                          architectureApi.patchEntity(pid, version, hash, ent.id, {
                            description: entDesc,
                            status: entStatus,
                          }),
                        (r) => {
                          onSaved(r);
                          setEditingEnt(null);
                        }
                      )
                    }
                  >
                    Save entity
                  </Button>
                  <Button variant="secondary" onClick={() => setEditingEnt(null)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <p className="text-slate-600">{ent.description}</p>
                <p className="text-slate-700">
                  <strong>Key fields:</strong> {ent.key_fields.join(", ")}
                </p>
                <p className="text-slate-500">
                  <strong>Access boundary:</strong> {ent.access_boundary}
                </p>
                <p className="text-slate-500">
                  <strong>Retention:</strong> {ent.retention_and_lifecycle} · <strong>Sensitive data:</strong>{" "}
                  {ent.sensitive_data_handling}
                </p>
                <p className="text-[11px] text-slate-500">PRD: {ent.prd_requirement_ids.join(", ")}</p>
                {canEdit && (
                  <Button variant="secondary" onClick={() => startEditEnt(ent)}>
                    Edit {ent.id}
                  </Button>
                )}
              </>
            )}
          </div>
        ))}
      </div>

      {dataArch.relationships.length > 0 && (
        <div className="rounded border border-slate-200 p-3 text-xs space-y-1">
          <h3 className="font-semibold">Entity Relationships</h3>
          <ul className="space-y-1">
            {dataArch.relationships.map((r, i) => (
              <li key={`${r.source_entity_id}-${r.target_entity_id}-${i}`}>
                <strong>{r.source_entity_id}</strong> ({r.cardinality}) → <strong>{r.target_entity_id}</strong>:{" "}
                {r.description}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-2 text-xs md:grid-cols-2">
        <div className="rounded bg-slate-50 p-2.5">
          <strong>Transaction & Integrity Rules:</strong>{" "}
          {dataArch.transaction_and_integrity_rules.join(" · ")}
        </div>
        <div className="rounded bg-slate-50 p-2.5">
          <strong>Migration Strategy:</strong> {dataArch.migration_strategy}
        </div>
      </div>
    </section>
  );
}

function ApiArchitectureSection({
  pid,
  version,
  hash,
  apiArch,
  canEdit,
  busy,
  run,
  onSaved,
}: {
  pid: string;
  version: number;
  hash: string;
  apiArch: NonNullable<NonNullable<ArchitectureState["current"]>["content"]>["api_architecture"];
  canEdit: boolean;
  busy: string | null;
  run: <T>(key: string, fn: () => Promise<T>, onDone: (r: T) => void) => Promise<void>;
  onSaved: (r: ArchitectureEditResponse) => void;
}) {
  const [editingEp, setEditingEp] = useState<string | null>(null);
  const [epSummary, setEpSummary] = useState("");

  function startEditEp(ep: ApiBoundarySpec) {
    setEditingEp(ep.id);
    setEpSummary(ep.summary);
  }

  return (
    <section
      aria-label="API and integration architecture"
      className="rounded-lg border border-slate-200 bg-white p-4 space-y-3"
    >
      <div>
        <h2 className="font-semibold">D. API & Integration Architecture</h2>
        <p className="text-xs text-slate-500">
          API boundary specifications, request/response contracts, auth requirements, and error conventions.
        </p>
      </div>

      <div className="space-y-2">
        {apiArch.endpoints.map((ep) => (
          <div key={ep.id} className="rounded border border-slate-200 p-3 text-xs space-y-1.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="font-semibold">
                {ep.id}: <span className="font-mono">{ep.method} {ep.path}</span>
              </div>
              <div className="flex flex-wrap gap-1">
                <Badge>{ep.component_id}</Badge>
                <Badge>{ep.auth_requirement}</Badge>
                <Badge tone={ep.implementation_status === "verified_existing" ? "success" : "warning"}>
                  {ep.implementation_status.replace(/_/g, " ")}
                </Badge>
              </div>
            </div>
            {editingEp === ep.id ? (
              <div className="space-y-2 pt-1">
                <TextField
                  id={`edit-ep-summary-${ep.id}`}
                  label="Endpoint summary"
                  value={epSummary}
                  onChange={(e) => setEpSummary(e.target.value)}
                />
                <div className="flex gap-2">
                  <Button
                    variant="primary"
                    loading={busy === `ep-${ep.id}`}
                    onClick={() =>
                      void run(
                        `ep-${ep.id}`,
                        () => architectureApi.patchEndpoint(pid, version, hash, ep.id, { summary: epSummary }),
                        (r) => {
                          onSaved(r);
                          setEditingEp(null);
                        }
                      )
                    }
                  >
                    Save endpoint
                  </Button>
                  <Button variant="secondary" onClick={() => setEditingEp(null)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <p className="text-slate-600">{ep.summary}</p>
                <div className="grid gap-1 text-slate-500 sm:grid-cols-2">
                  <div>
                    <strong>Request:</strong> {ep.request_contract}
                  </div>
                  <div>
                    <strong>Response:</strong> {ep.response_contract}
                  </div>
                  <div>
                    <strong>Validation / Errors:</strong> {ep.validation_and_error_handling}
                  </div>
                  <div>
                    <strong>Pagination / Filtering:</strong> {ep.pagination_and_filtering}
                  </div>
                </div>
                <p className="text-[11px] text-slate-500">
                  Entities: {ep.entity_ids.join(", ") || "—"} · Screens: {ep.prototype_screen_ids.join(", ") || "—"} ·
                  PRD: {ep.prd_requirement_ids.join(", ")}
                </p>
                {canEdit && (
                  <Button variant="secondary" onClick={() => startEditEp(ep)}>
                    Edit {ep.id}
                  </Button>
                )}
              </>
            )}
          </div>
        ))}
      </div>

      <div className="grid gap-2 text-xs md:grid-cols-3">
        <div className="rounded bg-slate-50 p-2.5">
          <strong>Request/Response Conventions:</strong> {apiArch.request_response_conventions}
        </div>
        <div className="rounded bg-slate-50 p-2.5">
          <strong>Validation & Error Conventions:</strong> {apiArch.validation_and_error_conventions}
        </div>
        <div className="rounded bg-slate-50 p-2.5">
          <strong>Integration Contracts & Failure Behavior:</strong>{" "}
          {apiArch.integration_contracts_and_failure_behavior}
        </div>
      </div>
    </section>
  );
}

function DeploymentArchitectureSection({
  deployArch,
}: {
  pid: string;
  version: number;
  hash: string;
  deployArch: NonNullable<NonNullable<ArchitectureState["current"]>["content"]>["deployment_architecture"];
  canEdit: boolean;
  busy: string | null;
  run: <T>(key: string, fn: () => Promise<T>, onDone: (r: T) => void) => Promise<void>;
  onSaved: (r: ArchitectureEditResponse) => void;
}) {
  return (
    <section
      aria-label="Deployment and operational architecture"
      className="rounded-lg border border-slate-200 bg-white p-4 space-y-3"
    >
      <div>
        <h2 className="font-semibold">E. Deployment & Operational Architecture</h2>
        <p className="text-xs text-slate-500">
          Runtime services, environment separation, secrets, health checks, observability, and recovery boundaries.
        </p>
      </div>

      <div className="grid gap-2 md:grid-cols-2">
        {deployArch.services_and_infrastructure.map((svc) => (
          <div key={svc.id} className="rounded border border-slate-200 p-3 text-xs space-y-1">
            <div className="flex flex-wrap items-center justify-between gap-1 font-medium">
              <span>
                {svc.id}: {svc.name}
              </span>
              <div className="flex gap-1">
                <Badge>{svc.environment}</Badge>
                <Badge tone={svc.implementation_status === "verified_current" ? "success" : "warning"}>
                  {svc.implementation_status.replace(/_/g, " ")}
                </Badge>
              </div>
            </div>
            <p className="text-slate-600">{svc.responsibility}</p>
            <p className="text-[11px] text-slate-500">Hosts components: {svc.component_ids.join(", ")}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-2 text-xs md:grid-cols-2">
        <div className="rounded bg-slate-50 p-2.5">
          <strong>Local Development Environment:</strong> {deployArch.local_development_environment}
        </div>
        <div className="rounded bg-slate-50 p-2.5">
          <strong>Configuration & Secret Management:</strong> {deployArch.configuration_and_secret_management}
        </div>
        <div className="rounded bg-slate-50 p-2.5">
          <strong>Deployment Boundaries:</strong> {deployArch.deployment_boundaries}
        </div>
        <div className="rounded bg-slate-50 p-2.5">
          <strong>Health Checks & Observability:</strong> {deployArch.health_checks_and_observability}
        </div>
        <div className="rounded bg-slate-50 p-2.5 md:col-span-2">
          <strong>Backup, Recovery & Failure Considerations:</strong> {deployArch.backup_recovery_and_failure}
        </div>
      </div>
    </section>
  );
}

function DecisionsSection({
  pid,
  version,
  hash,
  decisions,
  canEdit,
  busy,
  run,
  onSaved,
}: {
  pid: string;
  version: number;
  hash: string;
  decisions: ArchitectureDecision[];
  canEdit: boolean;
  busy: string | null;
  run: <T>(key: string, fn: () => Promise<T>, onDone: (r: T) => void) => Promise<void>;
  onSaved: (r: ArchitectureEditResponse) => void;
}) {
  const [editingAdr, setEditingAdr] = useState<string | null>(null);
  const [adrTitle, setAdrTitle] = useState("");
  const [adrDecision, setAdrDecision] = useState("");
  const [adrStatus, setAdrStatus] = useState<DecisionStatus>("accepted");

  function startEditAdr(d: ArchitectureDecision) {
    setEditingAdr(d.id);
    setAdrTitle(d.title);
    setAdrDecision(d.decision);
    setAdrStatus(d.status);
  }

  return (
    <section
      aria-label="Technical decisions"
      className="rounded-lg border border-slate-200 bg-white p-4 space-y-3"
    >
      <div>
        <h2 className="font-semibold">F. Technical Architecture Decision Records ({decisions.length})</h2>
        <p className="text-xs text-slate-500">
          Deterministic ADRs linking architectural choices, alternatives, trade-offs, and consequences to PRD and UX
          artifacts.
        </p>
      </div>

      <div className="space-y-2.5">
        {decisions.map((adr) => (
          <div key={adr.id} className="rounded border border-slate-200 p-3 text-xs space-y-1.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="font-semibold text-sm">
                {adr.id}: {adr.title}
              </div>
              <Badge
                tone={
                  adr.status === "accepted"
                    ? "success"
                    : adr.status === "requires_review"
                    ? "danger"
                    : "warning"
                }
              >
                {adr.status.replace(/_/g, " ")}
              </Badge>
            </div>
            {editingAdr === adr.id ? (
              <div className="space-y-2 pt-1">
                <TextField
                  id={`edit-adr-title-${adr.id}`}
                  label="Decision title"
                  value={adrTitle}
                  onChange={(e) => setAdrTitle(e.target.value)}
                />
                <TextAreaField
                  id={`edit-adr-decision-${adr.id}`}
                  label="Decision statement"
                  rows={2}
                  value={adrDecision}
                  onChange={(e) => setAdrDecision(e.target.value)}
                />
                <div>
                  <label htmlFor={`edit-adr-status-${adr.id}`} className="block text-xs font-medium text-slate-700">
                    Status
                  </label>
                  <select
                    id={`edit-adr-status-${adr.id}`}
                    className="mt-1 h-8 w-full rounded border border-slate-300 bg-white px-2 text-xs"
                    value={adrStatus}
                    onChange={(e) => setAdrStatus(e.target.value as DecisionStatus)}
                  >
                    <option value="accepted">accepted</option>
                    <option value="proposed">proposed</option>
                    <option value="requires_review">requires_review</option>
                  </select>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="primary"
                    loading={busy === `adr-${adr.id}`}
                    onClick={() =>
                      void run(
                        `adr-${adr.id}`,
                        () =>
                          architectureApi.patchDecision(pid, version, hash, adr.id, {
                            title: adrTitle,
                            decision: adrDecision,
                            status: adrStatus,
                          }),
                        (r) => {
                          onSaved(r);
                          setEditingAdr(null);
                        }
                      )
                    }
                  >
                    Save {adr.id}
                  </Button>
                  <Button variant="secondary" onClick={() => setEditingAdr(null)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <p className="text-slate-600">
                  <strong>Context:</strong> {adr.context_and_problem}
                </p>
                <p className="text-slate-800">
                  <strong>Decision:</strong> {adr.decision}
                </p>
                <p className="text-slate-600">
                  <strong>Rationale:</strong> {adr.rationale}
                </p>
                <p className="text-slate-500">
                  <strong>Alternatives & Trade-offs:</strong> {adr.alternatives_and_tradeoffs.join(" · ")}
                </p>
                <p className="text-slate-500">
                  <strong>Consequences & Risks:</strong> {adr.consequences_and_risks.join(" · ")}
                </p>
                <p className="text-[11px] text-slate-500">
                  PRD: {adr.prd_requirement_ids.join(", ")} · Source refs: {adr.source_refs.join(", ")}
                </p>
                {canEdit && (
                  <Button variant="secondary" onClick={() => startEditAdr(adr)}>
                    Edit {adr.id}
                  </Button>
                )}
              </>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function DiagramsSection({
  pid,
  version,
  hash,
  diagrams,
  selected,
  onSelect,
  canEdit,
  busy,
  run,
  onSaved,
}: {
  pid: string;
  version: number;
  hash: string;
  diagrams: ArchitectureDiagram[];
  selected: ArchitectureDiagram | null;
  onSelect: (id: string) => void;
  canEdit: boolean;
  busy: string | null;
  run: <T>(key: string, fn: () => Promise<T>, onDone: (r: T) => void) => Promise<void>;
  onSaved: (r: ArchitectureEditResponse) => void;
}) {
  const [editingDiag, setEditingDiag] = useState(false);
  const [diagTitle, setDiagTitle] = useState("");
  const [diagSummary, setDiagSummary] = useState("");

  function startEdit(d: ArchitectureDiagram) {
    setDiagTitle(d.title);
    setDiagSummary(d.summary);
    setEditingDiag(true);
  }

  return (
    <section
      aria-label="Architecture diagrams"
      className="rounded-lg border border-slate-200 bg-white p-4 space-y-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-semibold">G. Validated Architecture Diagrams ({diagrams.length})</h2>
          <p className="text-xs text-slate-500">
            Structured topology viewer and validated Mermaid specifications verified against the component, entity, and
            service inventory.
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Select architecture diagram">
          {diagrams.map((d) => (
            <button
              key={d.id}
              type="button"
              role="tab"
              aria-selected={selected?.id === d.id}
              onClick={() => {
                onSelect(d.id);
                setEditingDiag(false);
              }}
              className={`rounded border px-2.5 py-1 text-xs font-medium ${
                selected?.id === d.id
                  ? "border-slate-800 bg-slate-900 text-white"
                  : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {d.id}: {DIAGRAM_TYPE_LABELS[d.diagram_type] ?? d.diagram_type}
            </button>
          ))}
        </div>
      </div>

      {selected && (
        <div className="rounded border border-slate-200 p-3 space-y-3 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="font-semibold text-sm">
                {selected.id}: {selected.title}
              </h3>
              <p className="text-slate-600">{selected.summary}</p>
            </div>
            <div className="flex items-center gap-2">
              <Badge>{DIAGRAM_TYPE_LABELS[selected.diagram_type] ?? selected.diagram_type}</Badge>
              {canEdit && !editingDiag && (
                <Button variant="secondary" onClick={() => startEdit(selected)}>
                  Edit {selected.id}
                </Button>
              )}
            </div>
          </div>

          {editingDiag && (
            <div className="rounded border border-slate-200 bg-slate-50 p-3 space-y-2">
              <TextField
                id="edit-diag-title"
                label="Diagram title"
                value={diagTitle}
                onChange={(e) => setDiagTitle(e.target.value)}
              />
              <TextAreaField
                id="edit-diag-summary"
                label="Diagram summary"
                rows={2}
                value={diagSummary}
                onChange={(e) => setDiagSummary(e.target.value)}
              />
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  loading={busy === `diag-${selected.id}`}
                  onClick={() =>
                    void run(
                      `diag-${selected.id}`,
                      () =>
                        architectureApi.patchDiagram(pid, version, hash, selected.id, {
                          title: diagTitle,
                          summary: diagSummary,
                        }),
                      (r) => {
                        onSaved(r);
                        setEditingDiag(false);
                      }
                    )
                  }
                >
                  Save diagram
                </Button>
                <Button variant="secondary" onClick={() => setEditingDiag(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}

          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded border border-slate-200 bg-slate-50 p-2.5 space-y-1.5">
              <h4 className="font-semibold text-slate-700">Validated Inventory Nodes ({selected.nodes.length})</h4>
              <ul className="space-y-1">
                {selected.nodes.map((n) => (
                  <li key={n.id} className="flex items-center justify-between rounded bg-white px-2 py-1">
                    <span>
                      <strong>{n.id}:</strong> {n.label}
                    </span>
                    <Badge>{n.reference_id}</Badge>
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded border border-slate-200 bg-slate-50 p-2.5 space-y-1.5">
              <h4 className="font-semibold text-slate-700">Directed Connections ({selected.edges.length})</h4>
              <ul className="space-y-1">
                {selected.edges.map((e, i) => (
                  <li key={`${e.from_node}-${e.to_node}-${i}`} className="rounded bg-white px-2 py-1">
                    <strong>{e.from_node}</strong> → <strong>{e.to_node}</strong>:{" "}
                    <span className="text-slate-600">{e.label}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div>
            <h4 className="font-semibold text-slate-700 mb-1">Mermaid Specification</h4>
            <pre
              aria-label={`Mermaid definition for ${selected.id}`}
              className="overflow-x-auto rounded bg-slate-900 p-3 font-mono text-[11px] text-slate-100"
            >
              {selected.mermaid}
            </pre>
          </div>
        </div>
      )}
    </section>
  );
}

function ApproveArchitectureModal({
  unverifiedCount,
  busy,
  onCancel,
  onConfirm,
}: {
  unverifiedCount: number;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (ack: boolean, note: string) => void;
}) {
  const [ack, setAck] = useState(false);
  const [note, setNote] = useState("");
  return (
    <Dialog title="Approve Product Architecture" onClose={onCancel}>
      <div className="space-y-3 text-sm">
        <p className="text-slate-600">
          Approving locks this Product Architecture version as an immutable specification, records a provenance pointer
          in your Project Brain, and marks the Architecture lifecycle stage complete.
        </p>
        {unverifiedCount > 0 && (
          <label className="flex items-start gap-2 rounded border border-amber-300 bg-amber-50 p-2.5 text-xs text-amber-900">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
            />
            <span>
              I acknowledge that {unverifiedCount} architecture decision(s) or domain entities are marked{" "}
              <strong>proposed</strong> for target implementation.
            </span>
          </label>
        )}
        <TextAreaField
          id="arch-approval-note"
          label="Approval note (optional)"
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={busy}
            disabled={unverifiedCount > 0 && !ack}
            onClick={() => onConfirm(ack, note)}
          >
            Approve Architecture
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
