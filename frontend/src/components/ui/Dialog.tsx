import { useEffect, useId, useRef } from "react";

export function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const focusable = () => [...(ref.current?.querySelectorAll<HTMLElement>("a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled])") ?? [])];
    focusable()[0]?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") return closeRef.current();
      if (e.key !== "Tab") return;
      const f = focusable();
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1], active = document.activeElement;
      const outside = !ref.current?.contains(active);
      if (e.shiftKey && (active === first || outside)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && (active === last || outside)) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); prev?.focus(); };
  }, []);
  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center bg-slate-900/40 p-4 pt-24" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-5 shadow-xl">
        <h2 id={titleId} className="mb-3 text-base font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  );
}
