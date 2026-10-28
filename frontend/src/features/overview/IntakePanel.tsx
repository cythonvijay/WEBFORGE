import { useState } from "react";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { TextAreaField } from "../../components/ui/Fields";
import { ApiError } from "../../lib/api";
import { projectsApi } from "../projects/api";

const EXAMPLE = "I want to build a platform that helps local businesses create and manage their online stores…";

function describe(e: unknown): { tone: "warning" | "error"; title: string; body?: string } {
  if (e instanceof ApiError) {
    if (e.status === 503) return { tone: "warning", title: "AI analysis is not configured yet.", body: "Your project has not been modified. Configure an AI provider to continue." };
    if (e.status === 502) return { tone: "error", title: "WebForge couldn't validate the AI response.", body: `${e.message} No project data was changed. Please try again.` };
    return { tone: "error", title: e.message };
  }
  return { tone: "error", title: "Something went wrong." };
}

export function IntakePanel({ projectId, initial = "", replacing, onSaved, onCancel }: {
  projectId: string; initial?: string; replacing?: boolean; onSaved: (version: number) => void; onCancel?: () => void;
}) {
  const [text, setText] = useState(initial);
  const [fieldError, setFieldError] = useState("");
  const [fail, setFail] = useState<ReturnType<typeof describe> | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const idea = text.trim();
    if (idea.length < 10) return setFieldError("Describe your idea in at least 10 characters.");
    setFieldError(""); setFail(null); setBusy(true);
    try { onSaved((await projectsApi.intake(projectId, idea)).version); }
    catch (err) { setFail(describe(err)); setBusy(false); }
  }

  return (
    <section aria-labelledby="intake-h" className="rounded-lg border border-slate-200 bg-white p-5">
      <h2 id="intake-h" className="text-lg font-semibold">What are you building?</h2>
      <p className="mt-1 text-slate-600">Tell WebForge about your product in your own words.</p>
      {replacing && <div className="mt-3"><Alert tone="warning">Analyzing again replaces the current idea, target users and goals. Earlier versions stay in the revision history.</Alert></div>}
      <form onSubmit={submit} noValidate className="mt-3 space-y-3">
        {fail && <Alert tone={fail.tone} title={fail.title}>{fail.body}</Alert>}
        <TextAreaField label="Product idea" rows={6} maxLength={5000} value={text} placeholder={EXAMPLE} onChange={(e) => setText(e.target.value)} error={fieldError} disabled={busy} />
        <div className="flex items-center gap-2">
          <Button type="submit" variant="primary" loading={busy}>{busy ? "Analyzing your idea…" : "Analyze idea"}</Button>
          {onCancel && <Button onClick={onCancel} disabled={busy}>Cancel</Button>}
        </div>
      </form>
    </section>
  );
}
