import { useEffect, useRef, useState } from "react";
import { Link, Outlet, useLocation, useMatch } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthProvider";
import { cn } from "../../lib/utils";
import { SidebarNav } from "../navigation/SidebarNav";
import { Button } from "../ui/Button";

export default function AppShell() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const projectId = useMatch("/projects/:projectId/*")?.params.projectId;
  const { pathname } = useLocation();
  const toggleRef = useRef<HTMLButtonElement>(null);
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); toggleRef.current?.focus(); } };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="flex h-full flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-1.5">Skip to content</a>
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-3">
        <button ref={toggleRef} type="button" className="rounded-md p-1.5 hover:bg-slate-100 md:hidden" aria-label="Toggle navigation" aria-expanded={open} aria-controls="sidebar" onClick={() => setOpen((o) => !o)}>
          <svg aria-hidden viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
        </button>
        <Link to="/projects" className="font-semibold tracking-tight">WebForge</Link>
        <div className="ml-auto flex items-center gap-3">
          <span className="hidden max-w-56 truncate text-slate-600 sm:inline" title={user?.email}>{user?.email}</span>
          <Button size="sm" onClick={() => void logout()}>Sign out</Button>
        </div>
      </header>
      <div className="relative flex min-h-0 flex-1">
        {open && <div aria-hidden="true" role="presentation" data-testid="sidebar-backdrop" className="fixed inset-x-0 bottom-0 top-12 z-20 bg-slate-900/30 md:hidden" onClick={() => setOpen(false)} />}
        <aside id="sidebar" className={cn("w-60 shrink-0 overflow-y-auto border-r border-slate-200 bg-white", open ? "fixed bottom-0 left-0 top-12 z-30 block shadow-lg" : "hidden", "md:static md:block md:shadow-none")}>
          <SidebarNav projectId={projectId} />
        </aside>
        <main id="main" className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-6xl p-4 md:p-6"><Outlet /></div>
        </main>
      </div>
    </div>
  );
}
