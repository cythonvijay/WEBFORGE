import { useState } from "react";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { TextAreaField, TextField } from "../../components/ui/Fields";
import { ApiError } from "../../lib/api";
import type { Evidence, Finding, Source, Topic } from "../../types/research";
import type { FindingBody, SourceBody } from "./api";
import { EVIDENCE, EVIDENCE_ORDER, TOPIC_ORDER, TOPICS } from "./labels";

export function messagesOf(e: unknown): string[] {
  if (e instanceof ApiError && Array.isArray(e.detail)) return (e.detail as { msg?: string }[]).map((d) => d.msg ?? "Invalid value.");
  return [e instanceof Error ? e.message : "Something went wrong."];
}

const Select = ({ label, value, onChange, children }: { label: string; value: string; onChange: (v: string) => void; children: React.ReactNode }) => (
  <label className="block"><span className="mb-1 block text-xs font-medium text-slate-700">{label}</span>
    <select value={value} onChange={(e) => onChange(e.target.value)} className="h-9 w-full rounded-md border border-slate-300 bg-white px-2 text-sm">{children}</select></label>
);

function Form({ title, onClose, onSubmit, children, submitLabel }: { title: string; onClose: () => void; onSubmit: () => Promise<void>; children: React.ReactNode; submitLabel: string }) {
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  return (
    <Dialog title={title} onClose={onClose}>
      <form noValidate className="space-y-3" onSubmit={async (e) => { e.preventDefault(); setBusy(true); setErrors([]); try { await onSubmit(); } catch (err) { setErrors(messagesOf(err)); setBusy(false); } }}>
        {errors.length > 0 && <Alert tone="error">{errors.map((m) => <p key={m}>{m}</p>)}</Alert>}
        {children}
        <div className="flex justify-end gap-2 pt-1"><Button onClick={onClose} disabled={busy}>Cancel</Button><Button type="submit" variant="primary" loading={busy}>{submitLabel}</Button></div>
      </form>
    </Dialog>
  );
}

export function FindingDialog({ finding, sources, onSubmit, onClose }: { finding?: Finding; sources: Source[]; onSubmit: (b: FindingBody) => Promise<void>; onClose: () => void }) {
  const [topic, setTopic] = useState<Topic>(finding?.topic ?? "user_needs");
  const [statement, setStatement] = useState(finding?.statement ?? "");
  const [detail, setDetail] = useState(finding?.detail ?? "");
  const [evidence, setEvidence] = useState<Evidence>(finding?.evidence ?? "user_provided");
  const [cites, setCites] = useState(finding?.citations ?? []);
  const [followUp, setFollowUp] = useState(finding?.follow_up ?? false);
  return (
    <Form title={finding ? `Edit finding ${finding.id}` : "Add a finding"} submitLabel={finding ? "Save finding" : "Add finding"} onClose={onClose}
      onSubmit={() => onSubmit({ topic, statement: statement.trim(), detail: detail.trim() || null, evidence, citations: cites.filter((c) => c.source_id), follow_up: followUp })}>
      <Select label="Topic" value={topic} onChange={(v) => setTopic(v as Topic)}>{TOPIC_ORDER.map((t) => <option key={t} value={t}>{TOPICS[t]}</option>)}</Select>
      <TextAreaField label="Finding" rows={3} value={statement} onChange={(e) => setStatement(e.target.value)} />
      <TextAreaField label="Detail (optional)" rows={2} value={detail} onChange={(e) => setDetail(e.target.value)} />
      <Select label="Evidence" value={evidence} onChange={(v) => setEvidence(v as Evidence)}>{EVIDENCE_ORDER.map((e) => <option key={e} value={e}>{EVIDENCE[e].label}</option>)}</Select>
      <p className="-mt-2 text-xs text-slate-500">{EVIDENCE[evidence].help} “Source examined by you” needs a citation to a source you marked as examined.</p>
      <fieldset className="space-y-2"><legend className="text-xs font-medium text-slate-700">Citations</legend>
        {cites.map((c, i) => (
          <div key={i} className="flex gap-2">
            <select aria-label={`Citation ${i + 1} source`} value={c.source_id} onChange={(e) => setCites(cites.map((x, j) => (j === i ? { ...x, source_id: e.target.value } : x)))} className="h-9 w-40 rounded-md border border-slate-300 bg-white px-2 text-sm">
              <option value="">Choose source…</option>{sources.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
            </select>
            <input aria-label={`Citation ${i + 1} claim supported`} placeholder="What this source supports" value={c.claim} onChange={(e) => setCites(cites.map((x, j) => (j === i ? { ...x, claim: e.target.value } : x)))} className="h-9 min-w-0 flex-1 rounded-md border border-slate-300 px-2 text-sm" />
            <Button size="sm" onClick={() => setCites(cites.filter((_, j) => j !== i))} aria-label={`Remove citation ${i + 1}`}>Remove</Button>
          </div>
        ))}
        <Button size="sm" disabled={sources.length === 0} onClick={() => setCites([...cites, { source_id: "", claim: "" }])}>Add citation</Button>
        {sources.length === 0 && <p className="text-xs text-slate-500">Add a source first to cite it.</p>}
      </fieldset>
      <label className="flex items-center gap-2"><input type="checkbox" className="h-4 w-4" checked={followUp} onChange={(e) => setFollowUp(e.target.checked)} />Needs follow-up</label>
    </Form>
  );
}

export function SourceDialog({ source, onSubmit, onClose }: { source?: Source; onSubmit: (b: SourceBody) => Promise<void>; onClose: () => void }) {
  const [title, setTitle] = useState(source?.title ?? "");
  const [url, setUrl] = useState(source?.url ?? "");
  const [publisher, setPublisher] = useState(source?.publisher ?? "");
  const [accessed, setAccessed] = useState(source?.accessed_on ?? "");
  const [examined, setExamined] = useState(source?.examined ?? false);
  const [note, setNote] = useState(source?.note ?? "");
  return (
    <Form title={source ? `Edit source ${source.id}` : "Add a source"} submitLabel={source ? "Save source" : "Add source"} onClose={onClose}
      onSubmit={() => onSubmit({ title: title.trim(), url: url.trim(), publisher: publisher.trim() || null, accessed_on: accessed || null, examined, note: note.trim() || null })}>
      <TextField label="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
      <TextField label="URL" value={url} onChange={(e) => setUrl(e.target.value)} hint="WebForge checks the format only. It does not open the link or verify that it supports anything." />
      <TextField label="Publisher (optional)" value={publisher} onChange={(e) => setPublisher(e.target.value)} />
      <TextField label="Date you accessed it" type="date" value={accessed} onChange={(e) => setAccessed(e.target.value)} />
      <label className="flex items-start gap-2"><input type="checkbox" className="mt-0.5 h-4 w-4" checked={examined} onChange={(e) => setExamined(e.target.checked)} /><span>I examined this source myself (required for “Source examined by you”)</span></label>
      <TextAreaField label="Note (optional)" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
    </Form>
  );
}

export function ConfirmDialog({ title, body, confirmLabel, onConfirm, onClose }: { title: string; body: React.ReactNode; confirmLabel: string; onConfirm: () => Promise<void>; onClose: () => void }) {
  return (
    <Form title={title} submitLabel={confirmLabel} onClose={onClose} onSubmit={async () => { await onConfirm(); }}>
      <div>{body}</div>
    </Form>
  );
}

export function ApproveDialog({ unverified, onSubmit, onClose }: { unverified: number; onSubmit: (ack: boolean, note: string) => Promise<void>; onClose: () => void }) {
  const [ack, setAck] = useState(false);
  const [note, setNote] = useState("");
  return (
    <Dialog title="Approve this version" onClose={onClose}>
      <ApproveBody unverified={unverified} ack={ack} setAck={setAck} note={note} setNote={setNote} onSubmit={() => onSubmit(ack, note)} onClose={onClose} />
    </Dialog>
  );
}

function ApproveBody({ unverified, ack, setAck, note, setNote, onSubmit, onClose }: { unverified: number; ack: boolean; setAck: (b: boolean) => void; note: string; setNote: (s: string) => void; onSubmit: () => Promise<void>; onClose: () => void }) {
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  return (
    <form noValidate className="space-y-3" onSubmit={async (e) => { e.preventDefault(); setBusy(true); setErrors([]); try { await onSubmit(); } catch (err) { setErrors(messagesOf(err)); setBusy(false); } }}>
      {errors.length > 0 && <Alert tone="error">{errors.map((m) => <p key={m}>{m}</p>)}</Alert>}
      <p>Approval records this exact version and completes the Research stage. If you edit or regenerate later, a new version is created and needs approval again.</p>
      {unverified > 0 && (
        <label className="flex items-start gap-2"><input type="checkbox" className="mt-0.5 h-4 w-4" checked={ack} onChange={(e) => setAck(e.target.checked)} />
          <span>I understand that {unverified} finding{unverified === 1 ? " is" : "s are"} not backed by a source I examined.</span></label>
      )}
      <TextAreaField label="Approval note (optional)" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
      <div className="flex justify-end gap-2"><Button onClick={onClose} disabled={busy}>Cancel</Button>
        <Button type="submit" variant="primary" loading={busy} disabled={unverified > 0 && !ack}>Approve version</Button></div>
    </form>
  );
}
