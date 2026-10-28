import { safeHttpUrl } from "../../lib/utils";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import type { Finding, Source } from "../../types/research";
import { EVIDENCE } from "./labels";

export function FindingCard({ f, sources, canEdit, busy, onEdit, onFollowUp, onDelete }: {
  f: Finding; sources: Source[]; canEdit: boolean; busy: boolean; onEdit: () => void; onFollowUp: () => void; onDelete: () => void;
}) {
  const ev = EVIDENCE[f.evidence];
  return (
    <li className="rounded-lg border border-slate-200 bg-white p-4" aria-label={`Finding ${f.id}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span title={ev.help}><Badge tone={ev.tone}>{ev.label}</Badge></span>
        <Badge>{f.origin === "ai" ? "AI-generated" : "Added by you"}</Badge>
        {f.edited_by_user && <Badge>Edited by you</Badge>}
        {f.follow_up && <Badge tone="warning">Needs follow-up</Badge>}
      </div>
      <p className="mt-2 font-medium [overflow-wrap:anywhere]">{f.statement}</p>
      {f.detail && <p className="mt-1 text-slate-600 [overflow-wrap:anywhere]">{f.detail}</p>}
      {f.note && <p className="mt-1 text-xs text-amber-800">{f.note}</p>}
      {f.follow_up_note && <p className="mt-1 text-xs text-slate-600">Follow-up: {f.follow_up_note}</p>}
      {f.citations.length > 0 ? (
        <ul className="mt-2 space-y-1.5 border-l-2 border-slate-200 pl-3" aria-label="Sources for this finding">
          {f.citations.map((c) => {
            const s = sources.find((x) => x.id === c.source_id);
            return (
              <li key={c.source_id} className="text-sm">
                <span className="text-slate-700">{c.claim}</span>{" "}
                {s && <a href={safeHttpUrl(s.url)} target="_blank" rel="noopener noreferrer" className="text-blue-700 underline [overflow-wrap:anywhere]">{s.title}</a>}
                <span className="block text-xs text-slate-500">{s?.examined ? `Examined by you${s.accessed_on ? ` on ${s.accessed_on}` : ""}` : "Not examined"}{s?.publisher ? ` · ${s.publisher}` : ""}</span>
              </li>
            );
          })}
        </ul>
      ) : f.evidence !== "user_provided" && <p className="mt-2 text-xs text-slate-500">No source attached.</p>}
      {canEdit && (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" disabled={busy} onClick={onEdit} aria-label={`Edit finding ${f.id}`}>Edit</Button>
          <Button size="sm" disabled={busy || f.evidence === "unsupported"} title={f.evidence === "unsupported" ? "Unsupported claims always need follow-up" : undefined} onClick={onFollowUp} aria-label={`${f.follow_up ? "Clear follow-up on" : "Flag for follow-up:"} finding ${f.id}`}>{f.follow_up ? "Clear follow-up" : "Flag for follow-up"}</Button>
          <Button size="sm" variant="ghost" className="text-red-700" disabled={busy} onClick={onDelete} aria-label={`Delete finding ${f.id}`}>Delete</Button>
        </div>
      )}
    </li>
  );
}
