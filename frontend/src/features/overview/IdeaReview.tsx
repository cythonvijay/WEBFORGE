import { Button } from "../../components/ui/Button";
import type { BrainResponse } from "../../types/project";

const show = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v));

function List({ title, items }: { title: string; items: unknown[] }) {
  if (!items.length) return null;
  return (
    <div>
      <h3 className="text-xs font-medium text-slate-500">{title}</h3>
      <ul className="mt-0.5 list-disc space-y-0.5 pl-5">{items.map((x, i) => <li key={i}>{show(x)}</li>)}</ul>
    </div>
  );
}

export function IdeaReview({ data, onReanalyze }: { data: BrainResponse; onReanalyze: () => void }) {
  const { idea, target_users, goals } = data.brain;
  return (
    <section aria-labelledby="idea-h" className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 id="idea-h" className="text-sm font-semibold">Product idea</h2>
          <p className="text-xs text-slate-500">From Project Brain v{data.version}. Review before building on it.</p>
        </div>
        <Button size="sm" onClick={onReanalyze}>Analyze again</Button>
      </div>
      <div className="space-y-3">
        {(idea.product_name || idea.product_type) && (
          <div><h3 className="text-xs font-medium text-slate-500">Product</h3>
            <p className="text-base font-medium">{idea.product_name}{idea.product_type && <span className="ml-2 text-sm font-normal text-slate-600">{idea.product_type}</span>}</p></div>
        )}
        {idea.problem && <div><h3 className="text-xs font-medium text-slate-500">Problem</h3><p>{idea.problem}</p></div>}
        <List title="Target users" items={target_users} />
        <List title="Goals" items={goals} />
        <List title="Features" items={idea.features} />
        <List title="Assumptions" items={idea.assumptions} />
        <List title="Open questions" items={idea.open_questions} />
        <details><summary className="cursor-pointer text-xs text-slate-500">Your original description</summary><p className="mt-1 whitespace-pre-wrap text-slate-700">{idea.raw}</p></details>
      </div>
    </section>
  );
}
