import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorState, LoadingState } from "../components/feedback/States";
import { Alert } from "../components/ui/Alert";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { TextAreaField, TextField } from "../components/ui/Fields";
import { optimizationApi } from "../features/optimization/api";
import { ConfirmDialog } from "../features/research/Dialogs";
import { STATUS } from "../features/research/labels";
import { ApiError } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import { formatDateTime } from "../lib/utils";
import type {
  AnalyticsContent,
  OptimizationArea,
  OptimizationAreaState,
  OptimizationDocument,
  OptimizationEditResponse,
  OptimizationItemStatus,
  PerformanceContent,
  SeoContent,
} from "../types/optimization";
import { useProject } from "./ProjectLayout";

type Notice = { tone: "error" | "warning" | "success"; title: string; body?: string };

function describe(e: unknown, label: string): Notice {
  if (e instanceof ApiError) {
    if (e.status === 503) {
      return { tone: "warning", title: "AI analysis is not configured yet.", body: "You can initialize a baseline specification directly from your approved PRD, UX, and Architecture artifacts." };
    }
    if (e.status === 502) {
      return {
        tone: "error",
        title: `WebForge couldn't produce a valid ${label} specification.`,
        body: `${e.message} Nothing was changed.`,
      };
    }
    return { tone: "error", title: e.message };
  }
  return { tone: "error", title: "Something went wrong." };
}

const AREA_META: Record<
  OptimizationArea,
  { title: string; subtitle: string; badge: string; scopeNote: string }
> = {
  seo: {
    title: "SEO & Search Discoverability",
    subtitle: "Define search intent, public vs. private route indexability, canonical URLs, Open Graph/Twitter metadata, structured data schemas, and XML sitemap / robots.txt directives.",
    badge: "Phase 16 · SEO Stage",
    scopeNote: "Generated Product Specification: Enforces noindex and sitemap exclusion on private, authenticated, transactional, and admin routes.",
  },
  analytics: {
    title: "Product Analytics & Privacy Taxonomy",
    subtitle: "Define structured snake_case event taxonomies linked to PRD goals and UX journeys, explicit opt-in consent gates, PII redaction rules, and diagnostic reporting views.",
    badge: "Phase 16 · Analytics Stage",
    scopeNote: "Scope Separation: Defines analytics for the generated product only (provider-neutral, third-party transmission disabled by default). WebForge platform metrics remain strictly operational.",
  },
  performance: {
    title: "Performance Budgets & Verification",
    subtitle: "Define Core Web Vitals targets (LCP, INP, CLS, FCP, TTFB), route JS/CSS/image budgets, backend API p95/p99 latency targets, caching strategies, and recorded measurement evidence.",
    badge: "Phase 16 · Performance & Verification",
    scopeNote: "Honest Measurement Policy: Target budgets are explicitly distinguished from measured observations. Measured scores require recorded tool, environment, timestamp, and limitation metadata.",
  },
};

export function OptimizationWorkspace({ area }: { area: OptimizationArea }) {
  const { project } = useProject();
  const pid = project.id;
  const meta = AREA_META[area];

  const load = useAsync(() => optimizationApi.getArea(pid, area), [pid, area]);
  const [override, setOverride] = useState<OptimizationAreaState>();
  const [viewing, setViewing] = useState<number | null>(null);
  const viewed = useAsync(
    () => (viewing ? optimizationApi.getVersion(pid, area, viewing) : Promise.resolve(null)),
    [pid, area, viewing]
  );
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef<string | null>(null);
  const [modal, setModal] = useState<"regenerate" | "approve" | null>(null);

  const state = override ?? load.data;

  async function run<T>(key: string, fn: () => Promise<T>, onDone: (r: T) => void) {
    if (busyRef.current) return;
    busyRef.current = key;
    setBusy(key);
    setNotice(null);
    try {
      onDone(await fn());
    } catch (e) {
      setNotice(describe(e, meta.title));
    } finally {
      busyRef.current = null;
      setBusy(null);
    }
  }

  const applyEdit = (res: OptimizationEditResponse, msg: string) => {
    setOverride(res.state);
    setViewing(null);
    setNotice({
      tone: "success",
      title: res.copied_from_approved
        ? `Draft v${res.edited_version} started from approved v${res.copied_from_approved}. ${msg}`
        : msg,
    });
  };

  if (load.loading && !state) return <LoadingState label={`Loading ${meta.title}...`} />;
  if (load.error && !state) return <ErrorState message={load.error.message} onRetry={load.reload} />;
  if (!state) return null;

  const active: OptimizationDocument | null =
    viewing && viewed.data
      ? viewed.data
      : state.current_draft ?? state.current_approved;
  const isHistorical = Boolean(viewing && viewed.data && active && active.version !== (state.current_draft?.version ?? state.current_approved?.version));
  const prereqReady = state.prerequisites.ready;

  const confirmAllItems = (doc: OptimizationDocument) => {
    const cloned = JSON.parse(JSON.stringify(doc.content));
    if (area === "seo") {
      const c = cloned as SeoContent;
      c.page_metadata.forEach((p) => { p.status = "confirmed"; });
      c.technical_checklist.forEach((t) => { t.status = "confirmed"; });
    } else if (area === "analytics") {
      const c = cloned as AnalyticsContent;
      c.events.forEach((e) => { e.status = "confirmed"; });
      c.reporting_views.forEach((r) => { r.status = "confirmed"; });
    } else {
      const c = cloned as PerformanceContent;
      c.route_budgets.forEach((r) => { r.status = "confirmed"; });
      c.api_budgets.forEach((a) => { a.status = "confirmed"; });
    }
    run(
      "confirm-all",
      () => optimizationApi.putContent(pid, area, doc.version, doc.content_hash, cloned),
      (r) => applyEdit(r, "All items marked as confirmed.")
    );
  };

  return (
    <div className="space-y-6" data-testid={`optimization-workspace-${area}`}>
      {/* Header */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Badge tone="info">{meta.badge}</Badge>
              <Badge tone={state.stage_status === "complete" ? "success" : "neutral"}>
                Stage: {state.stage_status}
              </Badge>
              {active && (
                <Badge tone={STATUS[active.status]?.tone ?? "neutral"}>
                  v{active.version} · {STATUS[active.status]?.label ?? active.status}
                </Badge>
              )}
            </div>
            <h1 className="text-2xl font-semibold text-white">{meta.title}</h1>
            <p className="max-w-3xl text-sm text-slate-400">{meta.subtitle}</p>
            <p className="text-xs text-indigo-300/90">{meta.scopeNote}</p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Link
              to={`/projects/${pid}/seo`}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
                area === "seo" ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-300 hover:bg-slate-700"
              }`}
            >
              SEO
            </Link>
            <Link
              to={`/projects/${pid}/analytics`}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
                area === "analytics" ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-300 hover:bg-slate-700"
              }`}
            >
              Analytics
            </Link>
            <Link
              to={`/projects/${pid}/performance`}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
                area === "performance" ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-300 hover:bg-slate-700"
              }`}
            >
              Performance
            </Link>
          </div>
        </div>

        {/* Action Bar */}
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-800/80 pt-4">
          <div className="flex flex-wrap items-center gap-2">
            {!active ? (
              <>
                <Button
                  disabled={!prereqReady || Boolean(busy)}
                  onClick={() =>
                    run(
                      "generate",
                      () => optimizationApi.generate(pid, area, false),
                      (s) => {
                        setOverride(s);
                        setNotice({ tone: "success", title: `Generated ${meta.title} draft.` });
                      }
                    )
                  }
                >
                  {busy === "generate" ? "Generating..." : `Generate ${area.toUpperCase()} with AI`}
                </Button>
                <Button
                  variant="secondary"
                  disabled={!prereqReady || Boolean(busy)}
                  onClick={() =>
                    run(
                      "initialize",
                      () => optimizationApi.initialize(pid, area, false),
                      (s) => {
                        setOverride(s);
                        setNotice({ tone: "success", title: `Initialized ${meta.title} from approved artifacts.` });
                      }
                    )
                  }
                >
                  {busy === "initialize" ? "Initializing..." : "Initialize from Approved Basis"}
                </Button>
              </>
            ) : (
              <>
                <Button
                  variant="secondary"
                  disabled={!prereqReady || Boolean(busy)}
                  onClick={() => setModal("regenerate")}
                >
                  Regenerate Draft
                </Button>
                {!isHistorical && (
                  <Button
                    variant="secondary"
                    disabled={Boolean(busy)}
                    onClick={() => confirmAllItems(active)}
                  >
                    {busy === "confirm-all" ? "Confirming..." : "Confirm All Items"}
                  </Button>
                )}
                {state.current_draft && !isHistorical && state.current_draft.status === "draft" && (
                  <Button
                    disabled={!state.completeness.ready_for_submission || Boolean(busy)}
                    onClick={() =>
                      run(
                        "submit",
                        () =>
                          optimizationApi.submit(
                            pid,
                            area,
                            state.current_draft!.version,
                            state.current_draft!.content_hash
                          ),
                        (s) => {
                          setOverride(s);
                          setNotice({ tone: "success", title: `v${s.current_draft?.version} submitted for review.` });
                        }
                      )
                    }
                  >
                    {busy === "submit" ? "Submitting..." : "Submit for Review"}
                  </Button>
                )}
                {state.current_draft && !isHistorical && (
                  <Button
                    disabled={!state.completeness.ready_for_approval || Boolean(busy)}
                    onClick={() => setModal("approve")}
                  >
                    Approve v{state.current_draft.version}
                  </Button>
                )}
              </>
            )}
          </div>

          {/* Version Selector */}
          {state.versions.length > 0 && (
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <span>Version history:</span>
              {state.versions.map((v) => (
                <button
                  key={v.version}
                  type="button"
                  onClick={() => setViewing(v.version === active?.version ? null : v.version)}
                  className={`rounded px-2 py-1 font-mono ${
                    active?.version === v.version
                      ? "bg-indigo-600/30 text-indigo-200 ring-1 ring-indigo-500/50"
                      : "bg-slate-800 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  v{v.version} ({v.status})
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {notice && (
        <Alert tone={notice.tone} title={notice.title}>
          {notice.body}
        </Alert>
      )}

      {/* Upstream Warnings */}
      {state.warnings.length > 0 && (
        <div className="space-y-2" data-testid="upstream-warnings">
          {state.warnings.map((w, idx) => (
            <Alert key={idx} tone="warning" title={w.message}>
              <div className="mt-1 flex items-center gap-3 text-xs">
                <span>Artifact: {w.artifact}</span>
                <Link
                  to={`/projects/${pid}/${w.workspace}`}
                  className="font-medium text-amber-300 underline hover:text-amber-200"
                >
                  Open {w.workspace} workspace →
                </Link>
              </div>
            </Alert>
          ))}
        </div>
      )}

      {/* Prerequisite Gate Banner */}
      {!prereqReady && (
        <Alert
          tone="warning"
          title="Upstream prerequisites must be approved with no open drafts before generating or approving Phase 16 specifications."
        >
          <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
            {state.prerequisites.remediation_links.map((r, i) => (
              <li key={i}>
                <span>{r.reason} — </span>
                <Link
                  to={`/projects/${pid}/${r.workspace}`}
                  className="font-medium text-amber-300 underline hover:text-amber-200"
                >
                  Go to {r.label}
                </Link>
              </li>
            ))}
          </ul>
        </Alert>
      )}

      {/* Completeness & Traceability Summary */}
      {active && (
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
            <div className="text-xs font-medium uppercase tracking-wider text-slate-400">
              Specification Readiness
            </div>
            <div className="mt-2 flex items-center gap-2">
              <Badge tone={state.completeness.ready_for_approval ? "success" : "warning"}>
                {state.completeness.ready_for_approval ? "Ready for Approval" : "Action Needed"}
              </Badge>
              <span className="text-xs text-slate-400">{state.completeness.item_count} items</span>
            </div>
            {state.completeness.missing_fields.length > 0 && (
              <ul className="mt-2 list-disc pl-4 text-xs text-amber-300">
                {state.completeness.missing_fields.map((m, i) => (
                  <li key={i}>{m}</li>
                ))}
              </ul>
            )}
            {state.completeness.requires_review_items.length > 0 && (
              <p className="mt-2 text-xs text-rose-300">
                Requires review: {state.completeness.requires_review_items.join(", ")}
              </p>
            )}
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
            <div className="text-xs font-medium uppercase tracking-wider text-slate-400">
              PRD Requirement Coverage
            </div>
            <div className="mt-2 text-lg font-semibold text-white">
              {state.traceability.covered_requirements} / {state.traceability.total_requirements} covered
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Every Must/Should PRD requirement must be covered or explicitly justified as not_applicable.
            </p>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
            <div className="text-xs font-medium uppercase tracking-wider text-slate-400">
              Provenance & Content Hash
            </div>
            <div className="mt-2 font-mono text-xs text-slate-300 break-all">
              SHA-256: {active.content_hash.slice(0, 24)}…
            </div>
            <div className="mt-1 text-xs text-slate-400">
              Source: {active.generation_source} · Updated {formatDateTime(active.updated_at)}
            </div>
          </div>
        </div>
      )}

      {/* Traceability Findings */}
      {active && state.traceability.findings.length > 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4" data-testid="traceability-findings">
          <h2 className="text-sm font-semibold text-white">Cross-Artifact Traceability Findings</h2>
          <ul className="mt-2 space-y-1.5 text-xs">
            {state.traceability.findings.map((f, i) => (
              <li key={i} className="flex items-center justify-between rounded bg-slate-950/60 px-3 py-2">
                <span className={f.severity === "error" ? "text-rose-300" : "text-amber-300"}>
                  [{f.code}] {f.message}
                </span>
                <Link
                  to={`/projects/${pid}/${f.workspace}`}
                  className="text-indigo-400 underline hover:text-indigo-300"
                >
                  Inspect {f.workspace}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Area-Specific Content */}
      {active && area === "seo" && (
        <SeoSectionView
          pid={pid}
          doc={active}
          state={state}
          readOnly={isHistorical}
          onSaveSection={(sec, val, msg) =>
            run(
              `save-${sec}`,
              () => optimizationApi.patchSection(pid, "seo", active.version, active.content_hash, sec, val),
              (r) => applyEdit(r, msg)
            )
          }
        />
      )}

      {active && area === "analytics" && (
        <AnalyticsSectionView
          doc={active}
          readOnly={isHistorical}
          onSaveSection={(sec, val, msg) =>
            run(
              `save-${sec}`,
              () => optimizationApi.patchSection(pid, "analytics", active.version, active.content_hash, sec, val),
              (r) => applyEdit(r, msg)
            )
          }
        />
      )}

      {active && area === "performance" && (
        <PerformanceSectionView
          pid={pid}
          doc={active}
          readOnly={isHistorical}
          onSaveSection={(sec, val, msg) =>
            run(
              `save-${sec}`,
              () => optimizationApi.patchSection(pid, "performance", active.version, active.content_hash, sec, val),
              (r) => applyEdit(r, msg)
            )
          }
        />
      )}

      {/* PRD Requirement Coverage Matrix */}
      {active && state.traceability.requirement_coverage.length > 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5" data-testid="requirement-coverage-table">
          <h2 className="text-base font-semibold text-white">PRD Requirement Traceability Matrix</h2>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="border-b border-slate-800 text-slate-400">
                <tr>
                  <th className="py-2 pr-4">Requirement</th>
                  <th className="py-2 pr-4">Title</th>
                  <th className="py-2 pr-4">Priority</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Mapped Items / Justification</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {state.traceability.requirement_coverage.map((rc) => (
                  <tr key={rc.requirement_id}>
                    <td className="py-2 pr-4 font-mono text-indigo-300">{rc.requirement_id}</td>
                    <td className="py-2 pr-4">{rc.title}</td>
                    <td className="py-2 pr-4 uppercase">{rc.priority}</td>
                    <td className="py-2 pr-4">
                      <Badge tone={rc.covered ? "success" : "danger"}>{rc.coverage_status}</Badge>
                    </td>
                    <td className="py-2 pr-4">
                      {rc.mapped_item_ids.length > 0
                        ? rc.mapped_item_ids.join(", ")
                        : rc.justification || "Uncovered"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Regenerate Confirm Dialog */}
      <ConfirmDialog
        open={modal === "regenerate"}
        title={`Regenerate ${meta.title} Draft?`}
        description="This will replace your current open draft with a newly generated specification grounded in the latest approved upstream artifacts."
        confirmLabel="Regenerate"
        onCancel={() => setModal(null)}
        onConfirm={() => {
          setModal(null);
          run(
            "regenerate",
            () => optimizationApi.generate(pid, area, true),
            (s) => {
              setOverride(s);
              setViewing(null);
              setNotice({ tone: "success", title: `Regenerated ${meta.title} draft.` });
            }
          );
        }}
      />

      {/* Approve Dialog */}
      {modal === "approve" && state.current_draft && (
        <ApproveOptimizationDialog
          doc={state.current_draft}
          unverifiedCount={state.completeness.unverified_items.length}
          onClose={() => setModal(null)}
          onConfirm={(ack, note) => {
            setModal(null);
            run(
              "approve",
              () =>
                optimizationApi.approve(
                  pid,
                  area,
                  state.current_draft!.version,
                  state.current_draft!.content_hash,
                  ack,
                  note
                ),
              (s) => {
                setOverride(s);
                setViewing(null);
                setNotice({
                  tone: "success",
                  title: `Approved ${meta.title} v${s.current_approved?.version}. Project Brain updated.`,
                });
              }
            );
          }}
        />
      )}
    </div>
  );
}

function SeoSectionView({
  pid,
  doc,
  state,
  readOnly,
  onSaveSection,
}: {
  pid: string;
  doc: OptimizationDocument;
  state: OptimizationAreaState;
  readOnly: boolean;
  onSaveSection: (section: string, value: unknown, msg: string) => void;
}) {
  const c = doc.content as SeoContent;
  const [intent, setIntent] = useState(c.seo_strategy.primary_search_intent);
  const [policy, setPolicy] = useState(c.seo_strategy.crawl_and_indexing_policy);
  const [htmlSample, setHtmlSample] = useState(
    `<!doctype html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/><title>${c.page_metadata[0]?.title_template ?? "Product Home"}</title><meta name="description" content="${c.page_metadata[0]?.meta_description ?? "Structured product description for search discovery."}"/><meta name="robots" content="${c.page_metadata[0]?.robots_index ?? "index"},${c.page_metadata[0]?.robots_follow ?? "follow"}"/><link rel="canonical" href="${c.page_metadata[0]?.canonical_path ?? "/"}"/></head><body><main><h1>${c.page_metadata[0]?.h1_heading ?? "Main Heading"}</h1></main></body></html>`
  );
  const [htmlCheckResult, setHtmlCheckResult] = useState<{
    status: string;
    findings: { code: string; severity: string; message: string }[];
  } | null>(null);

  const togglePageStatus = (idx: number, nextStatus: OptimizationItemStatus) => {
    const next = c.page_metadata.map((p, i) => (i === idx ? { ...p, status: nextStatus } : p));
    onSaveSection("page_metadata", next, `Updated status for ${c.page_metadata[idx].id}.`);
  };

  return (
    <div className="space-y-6">
      {/* SEO Strategy */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
        <h2 className="text-base font-semibold text-white">1. SEO Strategy & Indexing Policy</h2>
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          <TextAreaField
            label="Primary Search Intent"
            value={intent}
            disabled={readOnly}
            onChange={(e) => setIntent(e.target.value)}
          />
          <TextAreaField
            label="Crawl & Indexing Policy"
            value={policy}
            disabled={readOnly}
            onChange={(e) => setPolicy(e.target.value)}
          />
        </div>
        {!readOnly && (
          <div className="mt-3">
            <Button
              variant="secondary"
              onClick={() =>
                onSaveSection(
                  "seo_strategy",
                  { ...c.seo_strategy, primary_search_intent: intent, crawl_and_indexing_policy: policy },
                  "Saved SEO strategy."
                )
              }
            >
              Save SEO Strategy
            </Button>
          </div>
        )}
      </div>

      {/* Route & Page Metadata */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5" data-testid="seo-page-metadata">
        <h2 className="text-base font-semibold text-white">2. Route Metadata, Indexability & Structured Data</h2>
        <div className="mt-3 space-y-3">
          {c.page_metadata.map((page, idx) => (
            <div key={page.id} className="rounded-lg border border-slate-800 bg-slate-950/60 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-indigo-300">{page.id}</span>
                  <span className="font-mono text-sm font-semibold text-white">{page.route_path}</span>
                  <Badge tone={page.visibility === "public" ? "success" : "warning"}>
                    {page.visibility}
                  </Badge>
                  <Badge tone={page.robots_index === "index" ? "info" : "neutral"}>
                    {page.robots_index},{page.robots_follow}
                  </Badge>
                  <Badge tone={page.include_in_sitemap ? "success" : "neutral"}>
                    {page.include_in_sitemap ? "In Sitemap" : "Excluded from Sitemap"}
                  </Badge>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={page.status === "confirmed" ? "success" : "warning"}>{page.status}</Badge>
                  {!readOnly && page.status !== "confirmed" && (
                    <Button variant="secondary" onClick={() => togglePageStatus(idx, "confirmed")}>
                      Confirm
                    </Button>
                  )}
                </div>
              </div>
              <div className="mt-2 grid gap-2 text-xs text-slate-300 md:grid-cols-2">
                <div>
                  <span className="text-slate-500">Title:</span> {page.title_template}
                </div>
                <div>
                  <span className="text-slate-500">H1:</span> {page.h1_heading}
                </div>
                <div className="md:col-span-2">
                  <span className="text-slate-500">Meta Description:</span> {page.meta_description}
                </div>
                <div>
                  <span className="text-slate-500">Canonical:</span> {page.canonical_path} ·{" "}
                  <span className="text-slate-500">Schema.org:</span> {page.structured_data_type}
                </div>
                <div>
                  <span className="text-slate-500">Screen:</span> {page.screen_id} ·{" "}
                  <span className="text-slate-500">Requirements:</span> {page.linked_requirement_ids.join(", ")}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Generated XML Sitemap & robots.txt Previews */}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
          <h3 className="text-sm font-semibold text-white">Sitemap XML Preview ({c.sitemap_spec.sitemap_path})</h3>
          <p className="mt-1 text-xs text-slate-400">
            Included public routes: {c.sitemap_spec.included_routes.join(", ") || "None"} · Excluded private routes:{" "}
            {c.sitemap_spec.excluded_routes.join(", ") || "None"}
          </p>
          <pre className="mt-2 max-h-48 overflow-auto rounded bg-slate-950 p-3 font-mono text-xs text-emerald-300">
            {state.sitemap_xml_preview ?? ""}
          </pre>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
          <h3 className="text-sm font-semibold text-white">robots.txt Preview</h3>
          <p className="mt-1 text-xs text-slate-400">{c.robots_spec.rationale}</p>
          <pre className="mt-2 max-h-48 overflow-auto rounded bg-slate-950 p-3 font-mono text-xs text-indigo-300">
            {state.robots_txt_preview ?? ""}
          </pre>
        </div>
      </div>

      {/* Deterministic HTML Metadata & Heading Verifier */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5" data-testid="seo-html-verifier">
        <h3 className="text-sm font-semibold text-white">3. Deterministic HTML Metadata & Semantic Verifier</h3>
        <p className="mt-1 text-xs text-slate-400">
          Inspect rendered HTML against the approved route metadata contract (title, meta description, canonical, robots directive, single H1, and semantic landmarks).
        </p>
        <div className="mt-3">
          <TextAreaField
            label={`HTML Document for ${c.page_metadata[0]?.route_path ?? "/"}`}
            value={htmlSample}
            onChange={(e) => setHtmlSample(e.target.value)}
          />
          <div className="mt-2 flex items-center gap-3">
            <Button
              variant="secondary"
              onClick={async () => {
                const res = await optimizationApi.verifyHtml(
                  pid,
                  c.page_metadata[0]?.route_path ?? "/",
                  htmlSample
                );
                setHtmlCheckResult(res);
              }}
            >
              Verify HTML Against Spec
            </Button>
            {htmlCheckResult && (
              <Badge tone={htmlCheckResult.status === "passed" ? "success" : "danger"}>
                Verification: {htmlCheckResult.status.toUpperCase()} ({htmlCheckResult.findings.length} findings)
              </Badge>
            )}
          </div>
          {htmlCheckResult && htmlCheckResult.findings.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-xs text-rose-300">
              {htmlCheckResult.findings.map((f, i) => (
                <li key={i}>
                  [{f.code}] {f.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function AnalyticsSectionView({
  doc,
  readOnly,
  onSaveSection,
}: {
  doc: OptimizationDocument;
  readOnly: boolean;
  onSaveSection: (section: string, value: unknown, msg: string) => void;
}) {
  const c = doc.content as AnalyticsContent;
  const [objective, setObjective] = useState(c.measurement_plan.measurement_objective);
  const [retention, setRetention] = useState(c.measurement_plan.data_retention_policy);

  const confirmEvent = (idx: number) => {
    const next = c.events.map((ev, i) => (i === idx ? { ...ev, status: "confirmed" as const } : ev));
    onSaveSection("events", next, `Confirmed event ${c.events[idx].event_name}.`);
  };

  return (
    <div className="space-y-6">
      {/* Measurement Plan */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
        <h2 className="text-base font-semibold text-white">1. Measurement Plan & KPIs</h2>
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          <TextAreaField
            label="Measurement Objective"
            value={objective}
            disabled={readOnly}
            onChange={(e) => setObjective(e.target.value)}
          />
          <TextAreaField
            label="Data Retention & Minimization Policy"
            value={retention}
            disabled={readOnly}
            onChange={(e) => setRetention(e.target.value)}
          />
        </div>
        <div className="mt-3 text-xs text-slate-300">
          <span className="text-slate-500">Primary KPIs:</span> {c.measurement_plan.primary_kpis.join(" · ")}
        </div>
        {!readOnly && (
          <div className="mt-3">
            <Button
              variant="secondary"
              onClick={() =>
                onSaveSection(
                  "measurement_plan",
                  {
                    ...c.measurement_plan,
                    measurement_objective: objective,
                    data_retention_policy: retention,
                  },
                  "Saved analytics measurement plan."
                )
              }
            >
              Save Measurement Plan
            </Button>
          </div>
        )}
      </div>

      {/* Event Taxonomy */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5" data-testid="analytics-events-list">
        <h2 className="text-base font-semibold text-white">2. Structured Event Taxonomy ({c.events.length} events)</h2>
        <div className="mt-3 space-y-3">
          {c.events.map((ev, idx) => (
            <div key={ev.id} className="rounded-lg border border-slate-800 bg-slate-950/60 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-indigo-300">{ev.id}</span>
                  <span className="font-mono text-sm font-semibold text-white">{ev.event_name}</span>
                  <Badge tone="info">{ev.category}</Badge>
                  <Badge tone={ev.requires_opt_in ? "warning" : "neutral"}>
                    Consent: {ev.consent_category} {ev.requires_opt_in ? "(Opt-in Required)" : ""}
                  </Badge>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={ev.status === "confirmed" ? "success" : "warning"}>{ev.status}</Badge>
                  {!readOnly && ev.status !== "confirmed" && (
                    <Button variant="secondary" onClick={() => confirmEvent(idx)}>
                      Confirm
                    </Button>
                  )}
                </div>
              </div>
              <p className="mt-2 text-xs text-slate-300">{ev.trigger_description}</p>
              <div className="mt-2 flex flex-wrap gap-4 text-xs text-slate-400">
                <span>Screen: {ev.screen_id}</span>
                {ev.journey_id && <span>Journey: {ev.journey_id}</span>}
                {ev.interaction_id && <span>Interaction: {ev.interaction_id}</span>}
                <span>Requirements: {ev.linked_requirement_ids.join(", ")}</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {ev.properties.map((p) => (
                  <span
                    key={p.name}
                    className="rounded bg-slate-900 px-2 py-0.5 font-mono text-[11px] text-slate-300"
                  >
                    {p.name}: {p.data_type} ({p.pii_classification})
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Consent & Privacy Controls */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5" data-testid="analytics-privacy-controls">
        <h2 className="text-base font-semibold text-white">3. Consent, Privacy & PII Exclusion Guardrails</h2>
        <div className="mt-2 grid gap-3 text-xs text-slate-300 md:grid-cols-2">
          <div>
            <span className="text-slate-500">Consent Mode:</span> {c.consent_and_privacy.consent_mode} (Banner required:{" "}
            {c.consent_and_privacy.banner_required ? "Yes" : "No"})
          </div>
          <div>
            <span className="text-slate-500">Third-Party Transmission:</span>{" "}
            {c.consent_and_privacy.third_party_transmission_enabled ? "Enabled" : "Disabled by default (Provider-Neutral)"}
          </div>
          <div className="md:col-span-2">
            <span className="text-slate-500">Excluded Sensitive Fields:</span>{" "}
            <span className="font-mono text-emerald-300">
              {c.consent_and_privacy.excluded_sensitive_fields.join(", ")}
            </span>
          </div>
          <div className="md:col-span-2">
            <span className="text-slate-500">User Deletion & Opt-Out Flow:</span>{" "}
            {c.consent_and_privacy.user_deletion_and_opt_out_flow}
          </div>
        </div>
      </div>
    </div>
  );
}

function PerformanceSectionView({
  pid,
  doc,
  readOnly,
  onSaveSection,
}: {
  pid: string;
  doc: OptimizationDocument;
  readOnly: boolean;
  onSaveSection: (section: string, value: unknown, msg: string) => void;
}) {
  const c = doc.content as PerformanceContent;
  const [lcp, setLcp] = useState(String(c.core_web_vitals.lcp_max_ms));
  const [inp, setInp] = useState(String(c.core_web_vitals.inp_max_ms));
  const [cls, setCls] = useState(String(c.core_web_vitals.cls_max_score));
  const verification = useAsync(() => optimizationApi.verification(pid), [pid, doc.content_hash]);

  return (
    <div className="space-y-6">
      {/* Core Web Vitals Budgets */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5" data-testid="performance-cwv-budgets">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-semibold text-white">1. Core Web Vitals & Responsiveness Budgets</h2>
          <Badge tone={c.core_web_vitals.measurement_status === "measured_observation" ? "success" : "info"}>
            Status: {c.core_web_vitals.measurement_status}
          </Badge>
        </div>
        <div className="mt-3 grid gap-4 md:grid-cols-3">
          <TextField
            label="LCP Max Budget (ms)"
            value={lcp}
            disabled={readOnly}
            onChange={(e) => setLcp(e.target.value)}
          />
          <TextField
            label="INP Max Budget (ms)"
            value={inp}
            disabled={readOnly}
            onChange={(e) => setInp(e.target.value)}
          />
          <TextField
            label="CLS Max Score"
            value={cls}
            disabled={readOnly}
            onChange={(e) => setCls(e.target.value)}
          />
        </div>
        <p className="mt-2 text-xs text-slate-400">{c.core_web_vitals.rationale}</p>
        {!readOnly && (
          <div className="mt-3">
            <Button
              variant="secondary"
              onClick={() =>
                onSaveSection(
                  "core_web_vitals",
                  {
                    ...c.core_web_vitals,
                    lcp_max_ms: Number(lcp),
                    inp_max_ms: Number(inp),
                    cls_max_score: Number(cls),
                  },
                  "Saved Core Web Vitals budgets."
                )
              }
            >
              Save CWV Budgets
            </Button>
          </div>
        )}
      </div>

      {/* Route Asset & Loading Budgets */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
        <h2 className="text-base font-semibold text-white">
          2. Route Asset Budgets & Loading Strategies ({c.route_budgets.length} routes)
        </h2>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="border-b border-slate-800 text-slate-400">
              <tr>
                <th className="py-2 pr-3">ID</th>
                <th className="py-2 pr-3">Route</th>
                <th className="py-2 pr-3">Screen</th>
                <th className="py-2 pr-3">Initial JS (gzip)</th>
                <th className="py-2 pr-3">Initial CSS (gzip)</th>
                <th className="py-2 pr-3">Loading Strategy</th>
                <th className="py-2 pr-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {c.route_budgets.map((rb) => (
                <tr key={rb.id}>
                  <td className="py-2 pr-3 font-mono text-indigo-300">{rb.id}</td>
                  <td className="py-2 pr-3 font-mono">{rb.route_path}</td>
                  <td className="py-2 pr-3">{rb.screen_id}</td>
                  <td className="py-2 pr-3">{rb.initial_js_kb_gzip} KB</td>
                  <td className="py-2 pr-3">{rb.initial_css_kb_gzip} KB</td>
                  <td className="py-2 pr-3">{rb.loading_strategy}</td>
                  <td className="py-2 pr-3">
                    <Badge tone={rb.status === "confirmed" ? "success" : "warning"}>{rb.status}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Backend API Latency Budgets */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
        <h2 className="text-base font-semibold text-white">
          3. Backend API Latency & Payload Budgets ({c.api_budgets.length} endpoints)
        </h2>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="border-b border-slate-800 text-slate-400">
              <tr>
                <th className="py-2 pr-3">ID</th>
                <th className="py-2 pr-3">Endpoint</th>
                <th className="py-2 pr-3">Route Pattern</th>
                <th className="py-2 pr-3">p95 / p99 Latency</th>
                <th className="py-2 pr-3">Max Payload</th>
                <th className="py-2 pr-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {c.api_budgets.map((ab) => (
                <tr key={ab.id}>
                  <td className="py-2 pr-3 font-mono text-indigo-300">{ab.id}</td>
                  <td className="py-2 pr-3 font-mono">{ab.endpoint_id}</td>
                  <td className="py-2 pr-3 font-mono">{ab.route_pattern}</td>
                  <td className="py-2 pr-3">
                    {ab.p95_latency_ms}ms / {ab.p99_latency_ms}ms
                  </td>
                  <td className="py-2 pr-3">{ab.max_payload_kb} KB</td>
                  <td className="py-2 pr-3">
                    <Badge tone={ab.status === "confirmed" ? "success" : "warning"}>{ab.status}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Measurement Evidence & Limitations */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5" data-testid="performance-evidence-table">
        <h2 className="text-base font-semibold text-white">
          4. Recorded Measurement Evidence vs. Target Budgets
        </h2>
        <div className="mt-3 space-y-2">
          {c.measurement_evidence.map((ev) => (
            <div key={ev.id} className="rounded border border-slate-800 bg-slate-950/60 p-3 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold text-white">
                  [{ev.id}] {ev.metric_name} — Target: {ev.target_value} {ev.unit}
                  {ev.measured_value ? ` · Measured: ${ev.measured_value} ${ev.unit}` : " · (Unmeasured Target Budget)"}
                </span>
                <Badge tone={ev.status === "measured_pass" ? "success" : "info"}>{ev.status}</Badge>
              </div>
              <p className="mt-1 text-slate-400">
                Tool: {ev.measurement_tool} · Environment: {ev.environment} · Scope: {ev.scope_description}
              </p>
              <p className="mt-1 text-slate-500">Limitations: {ev.limitations}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Automated Verification Report */}
      {verification.data && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5" data-testid="optimization-verification-report">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-white">
              5. Automated Phase 16 Verification Checks ({verification.data.passed_checks}/{verification.data.total_checks} Passed)
            </h2>
            <Badge tone={verification.data.overall_status === "passed" ? "success" : "warning"}>
              {verification.data.overall_status.toUpperCase()}
            </Badge>
          </div>
          <div className="mt-3 space-y-2">
            {verification.data.checks.map((chk) => (
              <div key={chk.id} className="rounded bg-slate-950/60 p-3 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-white">
                    [{chk.id}] {chk.title}
                  </span>
                  <Badge tone={chk.status === "passed" ? "success" : chk.status === "warning" ? "warning" : "danger"}>
                    {chk.status}
                  </Badge>
                </div>
                <p className="mt-1 text-slate-300">{chk.evidence}</p>
                <p className="mt-0.5 text-slate-500">Limitation: {chk.limitation}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ApproveOptimizationDialog({
  doc,
  unverifiedCount,
  onClose,
  onConfirm,
}: {
  doc: OptimizationDocument;
  unverifiedCount: number;
  onClose: () => void;
  onConfirm: (ack: boolean, note: string) => void;
}) {
  const [ack, setAck] = useState(unverifiedCount === 0);
  const [note, setNote] = useState("");

  return (
    <Dialog title={`Approve ${doc.area.toUpperCase()} v${doc.version}`} onClose={onClose}>
      <div className="space-y-4 text-sm text-slate-300">
        <p>
          Approving v{doc.version} locks its content hash (<code className="text-xs text-indigo-300">{doc.content_hash.slice(0, 16)}…</code>) as immutable and updates the Project Brain.
        </p>
        {unverifiedCount > 0 && (
          <label className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-950/30 p-3 text-xs text-amber-200">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              Acknowledge {unverifiedCount} item(s) still marked as <code>proposed</code> so they can be promoted upon approval.
            </span>
          </label>
        )}
        <TextAreaField
          label="Approval Note (optional)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={unverifiedCount > 0 && !ack} onClick={() => onConfirm(ack, note)}>
            Confirm Approval
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

export function SeoPage() {
  return <OptimizationWorkspace area="seo" />;
}

export function AnalyticsPage() {
  return <OptimizationWorkspace area="analytics" />;
}

export function PerformancePage() {
  return <OptimizationWorkspace area="performance" />;
}

export default SeoPage;
