import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { EmptyState, ErrorState, LoadingState } from "../components/feedback/States";
import { Alert } from "../components/ui/Alert";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { ConfirmDeleteDialog, ProjectFormDialog } from "../features/projects/ProjectDialogs";
import { projectsApi } from "../features/projects/api";
import { formatDateTime, timeAgo } from "../lib/utils";
import { useAsync } from "../lib/useAsync";
import type { Project } from "../types/project";

type Dialog = { kind: "create" } | { kind: "rename" | "delete"; project: Project } | null;

export default function ProjectsPage() {
  const navigate = useNavigate();
  const projects = useAsync(() => projectsApi.list(), []);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [actionError, setActionError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  async function toggleArchive(p: Project) {
    setBusyId(p.id); setActionError("");
    try { await projectsApi.update(p.id, { status: p.status === "active" ? "archived" : "active" }); projects.reload(); }
    catch (e) { setActionError(e instanceof Error ? e.message : "Something went wrong."); }
    finally { setBusyId(null); }
  }

  const newButton = <Button variant="primary" onClick={() => setDialog({ kind: "create" })}>New project</Button>;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Projects</h1>
        {projects.data && projects.data.length > 0 && newButton}
      </div>
      {actionError && <div className="mb-3"><Alert tone="error">{actionError}</Alert></div>}

      {projects.loading && !projects.data ? <LoadingState label="Loading projects…" />
        : projects.error ? <ErrorState message={projects.error.message} onRetry={projects.reload} />
        : projects.data && projects.data.length === 0 ? (
          <EmptyState title="No projects yet." action={newButton}>Create your first product and let WebForge guide it from idea to production.</EmptyState>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table role="table" className="w-full text-left max-md:block md:min-w-[40rem]">
              <thead role="rowgroup" className="border-b border-slate-200 bg-slate-50 text-xs text-slate-600 max-md:hidden">
                <tr><th scope="col" className="px-3 py-2 font-medium">Name</th><th scope="col" className="px-3 py-2 font-medium">Status</th>
                  <th scope="col" className="px-3 py-2 font-medium">Updated</th><th scope="col" className="px-3 py-2 font-medium">Created</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Actions</th></tr>
              </thead>
              <tbody role="rowgroup" className="divide-y divide-slate-100 max-md:block">
                {projects.data?.map((p) => (
                  <tr key={p.id} role="row" className={`max-md:grid max-md:grid-cols-[minmax(0,1fr)_auto] max-md:gap-x-3 max-md:gap-y-1.5 max-md:p-3 ${p.status === "archived" ? "bg-slate-50/60 text-slate-600" : ""}`}>
                    <td role="cell" className="max-w-xs px-3 py-2.5 max-md:max-w-none max-md:p-0">
                      <Link to={`/projects/${p.id}`} title={p.name} className="block font-medium text-slate-900 hover:underline [overflow-wrap:anywhere]">{p.name}</Link>
                      {p.description && <p className="truncate text-xs text-slate-500">{p.description}</p>}
                    </td>
                    <td role="cell" className="px-3 py-2.5 max-md:col-start-2 max-md:row-start-1 max-md:justify-self-end max-md:p-0"><Badge tone={p.status === "active" ? "success" : "neutral"}>{p.status === "active" ? "Active" : "Archived"}</Badge></td>
                    <td role="cell" className="whitespace-nowrap px-3 py-2.5 max-md:col-span-2 max-md:p-0 max-md:text-xs max-md:text-slate-500" title={formatDateTime(p.updated_at)}><span className="md:hidden">Updated </span>{timeAgo(p.updated_at)}</td>
                    <td role="cell" className="whitespace-nowrap px-3 py-2.5 max-md:col-span-2 max-md:p-0 max-md:text-xs max-md:text-slate-500"><span className="md:hidden">Created </span>{formatDateTime(p.created_at)}</td>
                    <td role="cell" className="px-3 py-2.5 max-md:col-span-2 max-md:p-0">
                      <div className="flex flex-wrap justify-end gap-1 max-md:justify-start">
                        <Link to={`/projects/${p.id}`} aria-label={`Open ${p.name}`} className="inline-flex h-7 items-center rounded-md border border-slate-300 bg-white px-2.5 text-xs font-medium hover:bg-slate-50">Open</Link>
                        <Button size="sm" variant="ghost" aria-label={`Rename ${p.name}`} onClick={() => setDialog({ kind: "rename", project: p })}>Rename</Button>
                        <Button size="sm" variant="ghost" aria-label={`${p.status === "active" ? "Archive" : "Restore"} ${p.name}`} loading={busyId === p.id} onClick={() => void toggleArchive(p)}>{p.status === "active" ? "Archive" : "Restore"}</Button>
                        <Button size="sm" variant="ghost" aria-label={`Delete ${p.name}`} className="text-red-700" onClick={() => setDialog({ kind: "delete", project: p })}>Delete</Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

      {dialog?.kind === "create" && (
        <ProjectFormDialog mode="create" onClose={() => setDialog(null)}
          onSubmit={async (v) => { const p = await projectsApi.create(v); navigate(`/projects/${p.id}`); }} />
      )}
      {dialog?.kind === "rename" && (
        <ProjectFormDialog mode="rename" project={dialog.project} onClose={() => setDialog(null)}
          onSubmit={async (v) => { await projectsApi.update(dialog.project.id, { name: v.name }); setDialog(null); projects.reload(); }} />
      )}
      {dialog?.kind === "delete" && (
        <ConfirmDeleteDialog project={dialog.project} onClose={() => setDialog(null)}
          onConfirm={async () => { await projectsApi.remove(dialog.project.id); setDialog(null); projects.reload(); }} />
      )}
    </div>
  );
}
