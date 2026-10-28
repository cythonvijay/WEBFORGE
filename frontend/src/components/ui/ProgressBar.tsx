export function ProgressBar({ value, label }: { value: number; label: string }) {
  const v = Math.max(0, Math.min(100, value));
  return (
    <div className="flex items-center gap-3">
      <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={v}
        className="h-2 flex-1 overflow-hidden rounded-full bg-slate-200">
        <div className="h-full bg-blue-600" style={{ width: `${v}%` }} />
      </div>
      <span className="w-10 text-right text-sm font-medium tabular-nums">{v}%</span>
    </div>
  );
}
