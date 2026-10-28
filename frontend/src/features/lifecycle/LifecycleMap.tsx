import { useMemo, useState } from "react";
import { Alert } from "../../components/ui/Alert";
import { StatusBadge } from "../../components/ui/Badge";
import { ApiError } from "../../lib/api";
import { STATUS_LABELS, cn, stageLabel } from "../../lib/utils";
import type { StageInfo, StageStatus } from "../../types/lifecycle";

/** Presentation only: rows are the dependency depth of each stage, derived from the backend's `depends_on`. */
function tiers(stages: StageInfo[]): StageInfo[][] {
  const by = new Map(stages.map((s) => [s.stage, s]));
  const memo = new Map<string, number>();
  const depth = (name: string, seen = new Set<string>()): number => {
    if (memo.has(name)) return memo.get(name)!;
    if (seen.has(name)) return 0;
    seen.add(name);
    const deps = by.get(name)?.depends_on ?? [];
    const d = deps.length ? 1 + Math.max(...deps.map((x) => depth(x, seen))) : 0;
    memo.set(name, d);
    return d;
  };
  const rows: StageInfo[][] = [];
  for (const s of stages) (rows[depth(s.stage)] ??= []).push(s);
  return rows.filter(Boolean);
}

export function LifecycleMap({ stages, onChangeStatus }: { stages: StageInfo[]; onChangeStatus: (stage: string, status: StageStatus) => Promise<void> }) {
  const rows = useMemo(() => tiers(stages), [stages]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function change(s: StageInfo, status: StageStatus) {
    setBusy(s.stage); setError("");
    try { await onChangeStatus(s.stage, status); }
    catch (e) {
      if (e instanceof ApiError && e.kind === "conflict" && s.unmet_dependencies.length)
        setError(`Can't set ${stageLabel(s.stage)} to ${STATUS_LABELS[status].toLowerCase()} yet. Complete ${s.unmet_dependencies.map(stageLabel).join(", ")} first.`);
      else setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally { setBusy(null); }
  }

  return (
    <section aria-labelledby="lifecycle-h" className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="lifecycle-h" className="text-sm font-semibold">Lifecycle</h2>
      <p className="mb-3 text-xs text-slate-500">Pre-lifecycle setup (Phases 1–8: Overview, AI Intake and Discovery) feeds your Project Brain. The 19 engineering lifecycle stages below (Phases 9–17) proceed row by row once dependencies above them are complete.</p>
      {error && <div className="mb-3"><Alert tone="error">{error}</Alert></div>}
      <ol className="space-y-1">
        {rows.map((row, i) => (
          <li key={i}>
            {i > 0 && <div aria-hidden className="py-1 text-center text-slate-300">↓</div>}
            <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {row.map((s) => {
                const waiting = s.unmet_dependencies.length > 0 && s.status !== "complete";
                return (
                  <li key={s.stage} className={cn("rounded-md border p-2.5", s.status === "blocked" ? "border-red-200" : "border-slate-200")}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">{stageLabel(s.stage)}</span>
                      <StatusBadge status={s.status} />
                    </div>
                    {s.depends_on.length > 0 && <p className="mt-1 text-xs text-slate-500">Requires {s.depends_on.map(stageLabel).join(", ")}</p>}
                    {waiting && <p className="mt-0.5 text-xs text-amber-800">Complete {s.unmet_dependencies.map(stageLabel).join(", ")} before starting {stageLabel(s.stage)}.</p>}
                    <label className="mt-2 block text-xs text-slate-600">
                      <span className="sr-only">Set status for {stageLabel(s.stage)}</span>
                      <select aria-label={`Set status for ${stageLabel(s.stage)}`} value={s.status} disabled={busy === s.stage}
                        onChange={(e) => void change(s, e.target.value as StageStatus)}
                        className="h-7 w-full rounded-md border border-slate-300 bg-white px-1.5 text-xs">
                        {(Object.keys(STATUS_LABELS) as StageStatus[]).map((k) => <option key={k} value={k}>{STATUS_LABELS[k]}</option>)}
                      </select>
                    </label>
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ol>
    </section>
  );
}
