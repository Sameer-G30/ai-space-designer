"use client"; // Selecting a point and drawing WebGL happen in the browser.

// What-if overlay state.
import { useState } from "react";

// Load the box view only in the browser.
import dynamic from "next/dynamic";

// Bill of materials.
import { BomTable } from "@/components/bom-table";

// Explanation, what-if, and versions.

// Generated image, scene-graph maps, and the advisory critic note.

// Pareto scatter.
import { ParetoChart } from "@/components/pareto-chart";

// Top-down plan.
import { PlanView } from "@/components/plan-view";

// Sustainability disclosure.
import { SUSTAINABILITY_NOTE, WEIGHT_LABELS, WEIGHT_NAMES } from "@/lib/constants";

// Durations and rupees.
import { formatInr, formatMs } from "@/lib/format";

// Result shapes.
import type {
  CounterfactualDesign,
  InfeasibleBody,
  ParetoBody,
  Requirement,
  SceneGraph,
} from "@/lib/types";

// Panels shown only after a solve are split into their own chunks.
const ExplainPanel = dynamic(() => import("@/components/explain-panel").then((m) => m.ExplainPanel));
// Generated image panel, loaded on demand.
const VisualizePanel = dynamic(() =>
  import("@/components/visualize-panel").then((m) => m.VisualizePanel),
);

// Box view. The server does not render the canvas.
const BoxView = dynamic(() => import("@/components/box-view"), {
  // WebGL is browser-only.
  ssr: false,
  // Placeholder while the module loads.
  loading: () => <p className="p-4 text-sm text-stone-600">Loading the 3D view.</p>,
});

// A finished solve: either a set or a reason.
type Outcome =
  // Feasible set plus the scene the plan needs and the requirement the what-if starts from.
  | {
      kind: "pareto";
      scene: SceneGraph;
      result: ParetoBody;
      selected: number;
      requirement: Requirement;
    }
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
  // Pareto design the overlay belongs to. A different point ignores the stored overlay.
  const anchorId =
    outcome.kind === "pareto"
      ? (outcome.result.points[Math.min(outcome.selected, outcome.result.points.length - 1)]?.design
          .design_id ?? "")
      : "";
  // What-if design, remembered with the Pareto id it was started from.
  const [overlay, setOverlay] = useState<{ anchorId: string; result: CounterfactualDesign } | null>(
    null,
  );
  // Ignore an overlay that belongs to a different Pareto point.
  const activeOverlay = overlay !== null && overlay.anchorId === anchorId ? overlay.result : null;
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
  // Selected design from the Pareto set.
  const design = point.design;
  // The what-if replaces the drawn design until the user goes back or picks another point.
  const activeDesign = activeOverlay?.design ?? design;
  // Trace for the drawn design.
  const activeTrace = activeOverlay?.trace ?? point.trace;
  // Bill for the drawn design.
  const activeBom = activeOverlay?.bom ?? point.bom;
  // Scene for the drawn design. A room-size what-if uses a new scene.
  const activeScene = activeOverlay?.scene ?? outcome.scene;
  // The feasible layout.
  return (
    // Results stack.
    <div className="flex flex-col gap-6" aria-live="polite">
      {/* Set summary. */}
      <section className="flex flex-col gap-2">
        {/* Heading. */}
        <h2 className="font-display text-xl font-semibold text-stone-900">Designs</h2>
        {/* Backend string, shown exactly as returned. */}
        <p className="text-sm text-stone-700">
          style_backend: <span className="font-mono">{outcome.result.style_backend}</span>
        </p>
        {/* Sweep facts. */}
        <p className="text-sm text-stone-700">
          {outcome.result.points.length} points, {outcome.result.candidates_evaluated} candidates evaluated,{" "}
          {outcome.result.dominated_removed} dominated removed, sweep {formatMs(outcome.result.solve_time_ms)}
        </p>
      </section>
      {/* Chart and the button list. */}
      <ParetoChart points={outcome.result.points} selected={index} onSelect={onSelect} />
      {/* Facts for the selected point. */}
      <section className="flex flex-col gap-2 rounded-2xl border border-stone-200 bg-white p-5 shadow-card animate-rise">
        {/* Labels as the API sent them. */}
        <h3 className="font-display text-lg font-semibold text-stone-900">{point.labels.join(", ")}</h3>
        {/* Design id of whatever is drawn. */}
        <p className="break-all text-sm text-stone-700">Design id: {activeDesign.design_id}</p>
        {/* Parent, only when one was returned. */}
        {activeDesign.parent_design_id ? (
          <p className="break-all text-sm text-stone-700">Parent design: {activeDesign.parent_design_id}</p>
        ) : null}
        {/* Score, cost, and this point's solve time. A what-if uses its own time. */}
        <p className="text-sm text-stone-700">
          Score {activeDesign.score.toFixed(3)}, cost {formatInr(activeDesign.cost)}, point time{" "}
          {formatMs(activeOverlay ? activeOverlay.solve_time_ms : point.solve_time_ms)}
        </p>
        {/* Weights used for this point. They can differ across the set. */}
        <h4 className="pt-2 text-sm font-semibold text-stone-900">Weights</h4>
        {/* One line per weight. */}
        <ul className="grid grid-cols-2 gap-1 text-sm text-stone-700 sm:grid-cols-3">
          {/* The six weights. */}
          {WEIGHT_NAMES.map((name) => (
            <li key={name}>
              {WEIGHT_LABELS[name]}: {activeDesign.weights[name].toFixed(2)}
            </li>
          ))}
        </ul>
        {/* Objective terms from the trace. */}
        <h4 className="pt-2 text-sm font-semibold text-stone-900">Objective terms</h4>
        {/* One line per term. */}
        <ul className="grid grid-cols-2 gap-1 text-sm text-stone-700 sm:grid-cols-3">
          {/* The six terms. */}
          {WEIGHT_NAMES.map((name) => (
            <li key={name}>
              {WEIGHT_LABELS[name]}: {activeTrace.objective_terms[name].toFixed(3)}
            </li>
          ))}
        </ul>
        {/* Sustainability is a lookup, not a certification. */}
        <p className="text-sm text-stone-600">{SUSTAINABILITY_NOTE}</p>
        {/* Binding constraints recorded on the trace. */}
        <h4 className="pt-2 text-sm font-semibold text-stone-900">Binding constraints</h4>
        {/* Empty and non-empty lists. */}
        {activeTrace.binding_constraints.length === 0 ? (
          <p className="text-sm text-stone-600">No binding constraints were recorded.</p>
        ) : (
          <ul className="list-disc pl-5 text-sm text-stone-700">
            {/* One recorded constraint. */}
            {activeTrace.binding_constraints.map((item) => (
              <li key={`${item.name}-${item.detail}`}>
                {item.name}: {item.detail}
              </li>
            ))}
          </ul>
        )}
        {/* Rejected rows are counted. The full catalog is not printed. */}
        <p className="text-sm text-stone-600">Rejected catalog rows: {activeTrace.rejected_items.length}</p>
        {/* The what-if banner. The Pareto chart above still shows the original set. */}
        {activeOverlay ? (
          <div className="flex flex-col gap-2 rounded-md border border-sky-200 bg-sky-50 p-3">
            <p className="text-sm text-sky-950">Showing the what-if design. The Pareto set above is unchanged.</p>
            <button
              type="button"
              className="w-fit rounded-md border border-sky-300 bg-white px-3 py-2 text-sm"
              onClick={() => {
                // Draw the selected Pareto point again.
                setOverlay(null);
              }}
            >
              Back to this Pareto point
            </button>
          </div>
        ) : null}
      </section>
      {/* Plan and boxes follow the selected point. */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Top-down plan. */}
        <PlanView scene={activeScene} objects={activeDesign.objects} />
        {/* 3D view. A GLB replaces a box only after that mesh has loaded. */}
        <BoxView scene={activeScene} objects={activeDesign.objects} />
      </div>
      {/* Depth, segmentation, the diffusion image or the reason it was not made, and the critic note. */}
      <VisualizePanel key={`visualize-${activeDesign.design_id}`} designId={activeDesign.design_id} />
      {/* Bill of materials for the same drawn design. */}
      <BomTable design={activeDesign} lines={activeBom} />
      {/* Explanation, what-if, and version comparison for this Pareto point. */}
      <ExplainPanel
        key={`explain-${design.design_id}`}
        anchorDesignId={design.design_id}
        viewDesignId={activeDesign.design_id}
        budgetInr={outcome.requirement.budget_inr}
        onCounterfactual={(result) => {
          // Remember which Pareto point this what-if belongs to.
          setOverlay({ anchorId, result });
        }}
      />
    </div>
  );
}
