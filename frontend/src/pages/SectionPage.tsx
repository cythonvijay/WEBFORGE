import { Link, useParams } from "react-router-dom";
import { findNavItem } from "../components/navigation/nav";
import NotFoundPage from "./NotFoundPage";

export default function SectionPage() {
  const { projectId = "", section = "" } = useParams();
  const item = findNavItem(section);
  if (!item || !item.phase) return <NotFoundPage />;
  return (
    <div className="max-w-xl">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Not implemented yet</p>
      <h1 className="mt-1 text-xl font-semibold">{item.label}</h1>
      <p className="mt-3 text-slate-700">This workspace will become available in Phase {item.phase}.</p>
      <p className="mt-2 text-slate-600">{item.blurb}</p>
      <Link to={`/projects/${projectId}/overview`} className="mt-5 inline-flex h-9 items-center rounded-md border border-slate-300 bg-white px-3.5 text-sm font-medium hover:bg-slate-50">Back to Overview</Link>
    </div>
  );
}
