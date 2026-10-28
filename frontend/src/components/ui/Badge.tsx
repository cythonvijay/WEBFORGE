import type { StageStatus } from "../../types/lifecycle";
import { STATUS_LABELS, cn } from "../../lib/utils";

const TONE = {
  neutral: "bg-slate-100 text-slate-700 ring-slate-200",
  info: "bg-blue-50 text-blue-800 ring-blue-200",
  warning: "bg-amber-50 text-amber-900 ring-amber-200",
  success: "bg-green-50 text-green-800 ring-green-200",
  danger: "bg-red-50 text-red-800 ring-red-200",
};

export function Badge({ tone = "neutral", children }: { tone?: keyof typeof TONE; children: React.ReactNode }) {
  return <span className={cn("inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset", TONE[tone])}>{children}</span>;
}

const STATUS_TONE: Record<StageStatus, keyof typeof TONE> = {
  not_started: "neutral", in_progress: "info", needs_review: "warning", complete: "success", blocked: "danger",
};
const GLYPH: Record<StageStatus, string> = { not_started: "○", in_progress: "◐", needs_review: "◑", complete: "●", blocked: "✕" };

/** Text label + glyph, so state never relies on color alone. */
export function StatusBadge({ status }: { status: StageStatus }) {
  return <Badge tone={STATUS_TONE[status]}><span aria-hidden className="mr-1">{GLYPH[status]}</span>{STATUS_LABELS[status]}</Badge>;
}
