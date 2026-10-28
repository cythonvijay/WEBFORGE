import { useId } from "react";
import type { InputHTMLAttributes, TextareaHTMLAttributes } from "react";
import { cn } from "../../lib/utils";

const BASE = "block w-full rounded-md border bg-white px-3 text-sm text-slate-900 placeholder:text-slate-400 disabled:bg-slate-100";

interface Common { label: string; error?: string; hint?: string }

export function TextField({ label, error, hint, className, ...rest }: Common & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  const desc = error ? `${id}-err` : hint ? `${id}-hint` : undefined;
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-slate-700">{label}</label>
      <input id={id} aria-invalid={!!error} aria-describedby={desc}
        className={cn(BASE, "h-9", error ? "border-red-500" : "border-slate-300", className)} {...rest} />
      {error ? <p id={`${id}-err`} className="mt-1 text-xs text-red-700">{error}</p>
        : hint ? <p id={`${id}-hint`} className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}

export function TextAreaField({ label, error, hint, className, ...rest }: Common & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId();
  const desc = error ? `${id}-err` : hint ? `${id}-hint` : undefined;
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-slate-700">{label}</label>
      <textarea id={id} aria-invalid={!!error} aria-describedby={desc}
        className={cn(BASE, "py-2", error ? "border-red-500" : "border-slate-300", className)} {...rest} />
      {error ? <p id={`${id}-err`} className="mt-1 text-xs text-red-700">{error}</p>
        : hint ? <p id={`${id}-hint`} className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}
