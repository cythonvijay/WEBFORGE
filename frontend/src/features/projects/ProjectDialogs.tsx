import { useState } from "react";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { TextAreaField, TextField } from "../../components/ui/Fields";
import type { Project } from "../../types/project";

export function ProjectFormDialog({ mode, project, onSubmit, onClose }: {
  mode: "create" | "rename"; project?: Project;
  onSubmit: (v: { name: string; description: string }) => Promise<void>; onClose: () => void;
}) {
  const [name, setName] = useState(project?.name ?? "");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [nameError, setNameError] = useState("");
  const [busy, setBusy] = useState(false);
  const create = mode === "create";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return setNameError("Give the project a name.");
    setNameError(""); setError(""); setBusy(true);
    try { await onSubmit({ name: name.trim(), description: description.trim() }); }
    catch (err) { setError(err instanceof Error ? err.message : "Something went wrong."); setBusy(false); }
  }

  return (
    <Dialog title={create ? "Create a project" : "Rename project"} onClose={onClose}>
      <form onSubmit={submit} noValidate className="space-y-3">
        {error && <Alert tone="error">{error}</Alert>}
        <TextField label="Project name" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} error={nameError} />
        {create && <TextAreaField label="Description" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} hint="Optional. You'll describe the product in detail next." />}
        <div className="flex justify-end gap-2 pt-1">
          <Button onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" variant="primary" loading={busy}>{create ? (busy ? "Creating…" : "Create project") : (busy ? "Saving…" : "Save")}</Button>
        </div>
      </form>
    </Dialog>
  );
}

export function ConfirmDeleteDialog({ project, onConfirm, onClose }: { project: Project; onConfirm: () => Promise<void>; onClose: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function go() {
    setBusy(true); setError("");
    try { await onConfirm(); } catch (err) { setError(err instanceof Error ? err.message : "Something went wrong."); setBusy(false); }
  }
  return (
    <Dialog title="Delete project?" onClose={onClose}>
      <div className="space-y-3">
        {error && <Alert tone="error">{error}</Alert>}
        <p className="[overflow-wrap:anywhere]"><strong>{project.name}</strong> will be permanently deleted, including its Project Brain and revision history. This can't be undone. Archive it instead if you may need it later.</p>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant="danger" onClick={go} loading={busy}>{busy ? "Deleting…" : "Delete project"}</Button>
        </div>
      </div>
    </Dialog>
  );
}
