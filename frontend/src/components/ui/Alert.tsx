import { cn } from "../../lib/utils";

const TONE = {
  error: "border-red-200 bg-red-50 text-red-900",
  warning: "border-amber-200 bg-amber-50 text-amber-900",
  info: "border-blue-200 bg-blue-50 text-blue-900",
  success: "border-green-200 bg-green-50 text-green-900",
};

export function Alert({ tone = "info", title, children }: { tone?: keyof typeof TONE; title?: string; children?: React.ReactNode }) {
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cn("rounded-md border px-3 py-2 text-sm", TONE[tone])}>
      {title && <p className="font-medium">{title}</p>}
      {children && <div className={title ? "mt-0.5" : ""}>{children}</div>}
    </div>
  );
}
