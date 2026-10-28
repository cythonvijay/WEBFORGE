import { NavLink } from "react-router-dom";
import { cn } from "../../lib/utils";
import { PROJECT_NAV } from "./nav";

const link = ({ isActive }: { isActive: boolean }) =>
  cn("flex items-center justify-between rounded-md px-2.5 py-1.5", isActive ? "bg-slate-100 font-medium text-slate-900" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900");

export function SidebarNav({ projectId }: { projectId?: string }) {
  return (
    <nav aria-label="Primary" className="space-y-4 p-3">
      <div className="space-y-0.5">
        <NavLink to="/projects" end className={link}>Projects</NavLink>
        <NavLink to="/settings" className={link}>Settings</NavLink>
      </div>
      {projectId && groups.map((g) => (
        <div key={g.label}>
          {g.label && <p className="mb-1 px-2.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">{g.label}</p>}
          <ul className="space-y-0.5">
            {g.items.map((it) => (
              <li key={it.key}>
                <NavLink to={`/projects/${projectId}/${it.key}`} className={link}>
                  <span>{it.label}</span>
                  {it.phase && <span className="ml-2 shrink-0 whitespace-nowrap text-[11px] text-slate-600"><span className="sr-only">Not implemented, </span>Phase {it.phase}</span>}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}
