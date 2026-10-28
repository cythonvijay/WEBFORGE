import { useRef, useState } from "react";
import { ErrorState, LoadingState } from "../components/feedback/States";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { UxWorkspaceShell, type UxNotice } from "../features/ux/UxWorkspaceShell";
import { uxApi } from "../features/ux/api";
import { ApiError } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import type { IaContent, IaNode, UxArtifactState, UxDocument, UxEditResponse } from "../types/ux";
import { useProject } from "./ProjectLayout";

function describe(e: unknown): UxNotice {
  if (e instanceof ApiError) {
    if (Array.isArray(e.detail)) return { tone: "error", title: (e.detail as { msg?: string }[]).map((d) => d.msg).join("; ") };
    return { tone: "error", title: e.message };
  }
  return { tone: "error", title: "Something went wrong." };
}

function depthOf(node: IaNode, byId: Map<string, IaNode>): number {
  let d = 0;
  let cur = node.parent_id;
  const seen = new Set<string>([node.id]);
  while (cur && byId.has(cur) && !seen.has(cur)) {
    seen.add(cur);
    d += 1;
    cur = byId.get(cur)!.parent_id;
  }
  return d;
}

export default function IaPage() {
  const { project } = useProject();
  const pid = project.id;
  const load = useAsync(() => uxApi.get<IaContent>(pid, "ia"), [pid]);
  const [override, setOverride] = useState<UxArtifactState<IaContent>>();
  const [viewing, setViewing] = useState<number | null>(null);
  const viewed = useAsync(() => (viewing ? uxApi.version<IaContent>(pid, "ia", viewing) : Promise.resolve(null)), [pid, viewing]);
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

  if (load.loading && !state) return <LoadingState label="Loading information architecture…" />;
  if (!state) return <ErrorState message={load.error?.message ?? "We couldn't load information architecture."} onRetry={load.reload} />;

  const doc: UxDocument<IaContent> | null = viewing ? (viewed.data ?? null) : state.current;
  const content = doc?.content ?? null;
  const hash = doc?.content_hash ?? "";
  const canEdit = viewing === null && !!doc && ["draft", "in_review", "approved"].includes(doc.status);
  const applyEdit = (r: UxEditResponse<IaContent>) => {
    setOverride(r.state);
    if (r.document.version !== doc?.version) setNotice({ tone: "success", title: `Saved as new draft version ${r.document.version}.` });
  };
  const byId = new Map((content?.nodes ?? []).map((n) => [n.id, n]));

  return (
    <UxWorkspaceShell
      projectId={pid}
      title="Information Architecture"
      subtitle="Hierarchical sitemap, navigation groups, key page actions, and PRD requirement traceability."
      state={state}
      doc={doc}
      viewing={viewing}
      onViewVersion={setViewing}
      busy={busy}
      notice={notice}
      onGenerate={(sup) => void run("generate", () => uxApi.generate<IaContent>(pid, "ia", sup), (s) => { setOverride(s); setViewing(null); })}
      onSubmit={() => void run("submit", () => uxApi.submit<IaContent>(pid, "ia", doc!.version, hash), setOverride)}
      onApprove={(ack, note) => uxApi.approve<IaContent>(pid, "ia", doc!.version, hash, ack, note).then(setOverride)}
    >
      {content && (
        <section aria-labelledby="ia-tree-h" className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
          <h2 id="ia-tree-h" className="text-base font-semibold">Sitemap hierarchy ({content.nodes.length} nodes)</h2>
          <div className="grid gap-2 sm:grid-cols-3 text-xs bg-slate-50 p-3 rounded border border-slate-200">
            <div><strong>Primary nav:</strong> {content.navigation_model.primary_nav.join(", ") || "—"}</div>
            <div><strong>Secondary nav:</strong> {content.navigation_model.secondary_nav.join(", ") || "—"}</div>
            <div><strong>Utility nav:</strong> {content.navigation_model.utility_nav.join(", ") || "—"}</div>
          </div>
          <ul className="space-y-2" aria-label="Sitemap nodes">
            {content.nodes.map((n) => {
              const depth = depthOf(n, byId);
              return (
                <li key={n.id} style={{ marginLeft: `${depth * 1.25}rem` }} className="rounded border border-slate-200 p-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge>{n.id}</Badge>
                      <span className="font-semibold">{n.name}</span>
                      <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{n.path}</code>
                      <Badge tone="info">{n.navigation_group}</Badge>
                      <Badge tone="neutral">{n.access_role}</Badge>
                    </div>
                    {canEdit && (
                      <label className="flex items-center gap-1 text-xs text-slate-600">
                        <span>Parent:</span>
                        <select
                          aria-label={`Parent node for ${n.id}`}
                          value={n.parent_id ?? ""}
                          disabled={!!busy}
                          onChange={(e) => {
                            const val = e.target.value;
                            void run("edit", () => uxApi.patchIaNode(pid, doc!.version, hash, n.id, val ? { parent_id: val } : { clear_parent: true }), applyEdit);
                          }}
                          className="h-7 rounded border border-slate-300 bg-white px-1.5 text-xs"
                        >
                          <option value="">(Root)</option>
                          {content.nodes.filter((x) => x.id !== n.id).map((x) => (
                            <option key={x.id} value={x.id}>{x.id}: {x.name}</option>
                          ))}
                        </select>
                      </label>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-slate-700">{n.purpose}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    Content groups: {n.content_groups.join(", ")} · Key actions: {n.key_actions.join(", ")} · PRD: {n.prd_requirement_ids.join(", ")}
                  </p>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </UxWorkspaceShell>
  );
}
