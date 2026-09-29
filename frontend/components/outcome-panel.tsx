"use client"; // Selecting a point and drawing WebGL happen in the browser.

// Load the box view only in the browser.
import dynamic from "next/dynamic";

// Bill of materials.
import { BomTable } from "@/components/bom-table";

// Pareto scatter.
import { ParetoChart } from "@/components/pareto-chart";

// Top-down plan.
import { PlanView } from "@/components/plan-view";

// Sustainability disclosure.
import { SUSTAINABILITY_NOTE, WEIGHT_LABELS, WEIGHT_NAMES } from "@/lib/constants";

// Durations and rupees.
import { formatInr, formatMs } from "@/lib/format";

// Result shapes.
import type { InfeasibleBody, ParetoBody, SceneGraph } from "@/lib/types";

// Box view. The server does not render the canvas.
const BoxView = dynamic(() => import("@/components/box-view"), {
  // WebGL is browser-only.
  ssr: false,
  // Placeholder while the module loads.
  loading: () => <p className="p-4 text-sm text-zinc-600">Loading the box view.</p>,
});

// A finished solve: either a set or a reason.
type Outcome =
  // Feasible set plus the scene the plan needs.
  | { kind: "pareto"; scene: SceneGraph; result: ParetoBody; selected: number }
  // Infeasible reason. No design is drawn.
  | { kind: "infeasible"; result: InfeasibleBody };

// Props.
type OutcomePanelProps = {
  // The latest solve.
  outcome: Outcome;
  // Choose a Pareto point.
  onSelect: (index: number) => void;
};

// Render a reason, or the selected design.
export function OutcomePanel({ outcome, onSelect }: OutcomePanelProps) {
  // Infeasible solves stop here.
  if (outcome.kind === "infeasible") {
    // Reason only.
    return (
      // Amber panel, distinct from an HTTP error.
      <section className="rounded-lg border border-amber-300 bg-amber-50 p-4" aria-live="polite">
        {/* Heading. */}
        <h2 className="text-lg font-semibold text-amber-950">No design</h2>
        {/* Solver reason. */}
        <p className="mt-2 whitespace-pre-wrap text-sm text-amber-950">{outcome.result.reason}</p>
        {/* Time spent. */}
        <p className="mt-2 text-sm text-amber-900">Solve time {formatMs(outcome.result.solve_time_ms)}</p>
      </section>
    );
  }
  // Clamp the index so a short list still has a point.
  const index = Math.min(outcome.selected, outcome.result.points.length - 1);
  // The design that drives the rest of the page.
  const point = outcome.result.points[index];
  // A parsed set always has a point. This guard satisfies the type checker.
  if (point === undefined) {
    // Nothing to draw.
    return <p className="text-sm text-red-800">The API returned no designs.</p>;
  }
  // Selected design.
  const design = point.design;
  // The feasible layout.
  return (
    // Results stack.
    <div className="flex flex-col gap-6" aria-live="polite">
      {/* Set summary. */}
      <section className="flex flex-col gap-2">
        {/* Heading. */}
        <h2 className="text-lg font-semibold text-zinc-900">Designs</h2>
        {/* Backend string, shown exactly as returned. */}
        <p className="text-sm text-zinc-700">
          style_backend: <span className="font-mono">{outcome.result.style_backend}</span>
        </p>
        {/* Sweep facts. */}
        <p className="text-sm text-zinc-700">
          {outcome.result.points.length} points, {outcome.result.candidates_evaluated} candidates evaluated,{" "}
          {outcome.result.dominated_removed} dominated removed, sweep {formatMs(outcome.result.solve_time_ms)}
        </p>
      </section>
      {/* Chart and the button list. */}
      <ParetoChart points={outcome.result.points} selected={index} onSelect={onSelect} />
      {/* Facts for the selected point. */}
      <section className="flex flex-col gap-2 rounded-lg border border-zinc-200 bg-white p-4">
        {/* Labels as the API sent them. */}
        <h3 className="text-base font-semibold text-zinc-900">{point.labels.join(", ")}</h3>
        {/* Design id. */}
        <p className="text-sm text-zinc-700">Design id: {design.design_id}</p>
        {/* Parent, only when one was returned. */}
        {design.parent_design_id ? (
          <p className="text-sm text-zinc-700">Parent design: {design.parent_design_id}</p>
        ) : null}
        {/* Score, cost, and this point's solve time. */}
        <p className="text-sm text-zinc-700">
          Score {design.score.toFixed(3)}, cost {formatInr(design.cost)}, point time {formatMs(point.solve_time_ms)}
        </p>
        {/* Weights used for this point. They can differ across the set. */}
        <h4 className="pt-2 text-sm font-semibold text-zinc-900">Weights</h4>
        {/* One line per weight. */}
        <ul className="grid grid-cols-2 gap-1 text-sm text-zinc-700 sm:grid-cols-3">
          {/* The six weights. */}
          {WEIGHT_NAMES.map((name) => (
            <li key={name}>
              {WEIGHT_LABELS[name]}: {design.weights[name].toFixed(2)}
            </li>
          ))}
        </ul>
        {/* Objective terms from the trace. */}
        <h4 className="pt-2 text-sm font-semibold text-zinc-900">Objective terms</h4>
        {/* One line per term. */}
        <ul className="grid grid-cols-2 gap-1 text-sm text-zinc-700 sm:grid-cols-3">
          {/* The six terms. */}
          {WEIGHT_NAMES.map((name) => (
            <li key={name}>
              {WEIGHT_LABELS[name]}: {point.trace.objective_terms[name].toFixed(3)}
            </li>
          ))}
        </ul>
        {/* Sustainability is a lookup, not a certification. */}
        <p className="text-sm text-zinc-600">{SUSTAINABILITY_NOTE}</p>
        {/* Binding constraints recorded on the trace. */}
        <h4 className="pt-2 text-sm font-semibold text-zinc-900">Binding constraints</h4>
        {/* Empty and non-empty lists. */}
        {point.trace.binding_constraints.length === 0 ? (
          <p className="text-sm text-zinc-600">No binding constraints were recorded.</p>
        ) : (
          <ul className="list-disc pl-5 text-sm text-zinc-700">
            {/* One recorded constraint. */}
            {point.trace.binding_constraints.map((item) => (
              <li key={`${item.name}-${item.detail}`}>
                {item.name}: {item.detail}
              </li>
            ))}
          </ul>
        )}
        {/* Rejected rows are counted. The full catalog is not printed. */}
        <p className="text-sm text-zinc-600">Rejected catalog rows: {point.trace.rejected_items.length}</p>
      </section>
      {/* Plan and boxes follow the selected point. */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Top-down plan. */}
        <PlanView scene={outcome.scene} objects={design.objects} />
        {/* Box view. */}
        <BoxView scene={outcome.scene} objects={design.objects} />
      </div>
      {/* Bill of materials for the same point. */}
      <BomTable design={design} lines={point.bom} />
    </div>
  );
}
