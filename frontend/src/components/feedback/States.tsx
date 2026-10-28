import { Link } from "react-router-dom";
import { Button } from "../ui/Button";

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return <svg aria-hidden viewBox="0 0 24 24" className={`${className} animate-spin`} fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity=".25" strokeWidth="3" /><path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" /></svg>;
}

export function LoadingState({ label }: { label: string }) {
  return <div role="status" className="flex items-center gap-2 py-10 text-slate-600"><Spinner />{label}</div>;
}

export function ErrorState({ title = "Something went wrong.", message, onRetry, backTo }: { title?: string; message: string; onRetry?: () => void; backTo?: { to: string; label: string } }) {
  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-white p-6">
      <h2 className="font-semibold text-red-900">{title}</h2>
      <p className="mt-1 text-slate-700">{message}</p>
      <div className="mt-4 flex gap-2">
        {onRetry && <Button onClick={onRetry}>Retry</Button>}
        {backTo && <Link to={backTo.to} className="inline-flex h-9 items-center rounded-md border border-slate-300 bg-white px-3.5 text-sm font-medium hover:bg-slate-50">{backTo.label}</Link>}
      </div>
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
      <h2 className="font-semibold">{title}</h2>
      {children && <p className="mx-auto mt-1 max-w-md text-slate-600">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
