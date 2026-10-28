import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="max-w-md">
      <h1 className="text-xl font-semibold">Page not found</h1>
      <p className="mt-2 text-slate-600">That page doesn't exist.</p>
      <Link to="/projects" className="mt-4 inline-flex h-9 items-center rounded-md border border-slate-300 bg-white px-3.5 text-sm font-medium hover:bg-slate-50">Back to projects</Link>
    </div>
  );
}
