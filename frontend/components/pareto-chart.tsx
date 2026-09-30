"use client"; // Chart clicks stay in the browser. The points come from the API.

import { memo } from "react"; // Skip re-renders when props are unchanged.

// Mouse and keyboard events.
import type { KeyboardEvent } from "react";

// Axis and button text.
import { formatInr, formatInrTick } from "@/lib/format";

// Point shape.
import type { ParetoPoint } from "@/lib/types";

// Props for one returned set. The length is whatever the API sent.
type ParetoChartProps = {
  // One to eight points is normal. The chart does not assume four.
  points: ParetoPoint[];
  // Index of the design that drives the plan, the bill, and the boxes.
  selected: number;
  // Choose a point.
  onSelect: (index: number) => void;
};

// SVG size in pixels.
const WIDTH = 520;

// SVG size in pixels.
const HEIGHT = 300;

// Room for the score labels.
const PAD_LEFT = 52;

// Room on the right.
const PAD_RIGHT = 20;

// Room above the highest point.
const PAD_TOP = 18;

// Room for the cost labels.
const PAD_BOTTOM = 36;

// Widen a domain so a single point is not stuck on the border.
function paddedDomain(min: number, max: number): [number, number] {
  // Equal values need an artificial span.
  if (min === max) {
    // A fraction of the value, or 1 when the value is 0.
    const delta = Math.abs(min) * 0.08 || 1;
    // Centre the point.
    return [min - delta, max + delta];
  }
  // Twelve percent padding on each side.
  const pad = (max - min) * 0.12;
  // Expanded domain.
  return [min - pad, max + pad];
}

// Scatter of cost against score. Clicking a point selects that design.
function ParetoChartImpl({ points, selected, onSelect }: ParetoChartProps) {
  // Costs of the returned points.
  const costs = points.map((point) => point.design.cost);
  // Scores of the returned points.
  const scores = points.map((point) => point.design.score);
  // Lowest cost.
  const minCost = Math.min(...costs);
  // Highest cost.
  const maxCost = Math.max(...costs);
  // Lowest score.
  const minScore = Math.min(...scores);
  // Highest score.
  const maxScore = Math.max(...scores);
  // Cost domain.
  const [costStart, costEnd] = paddedDomain(minCost, maxCost);
  // Score domain.
  const [scoreStart, scoreEnd] = paddedDomain(minScore, maxScore);
  // Plot width.
  const plotWidth = WIDTH - PAD_LEFT - PAD_RIGHT;
  // Plot height.
  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
  // Map a cost onto an x pixel.
  const xOf = (cost: number): number =>
    PAD_LEFT + ((cost - costStart) / (costEnd - costStart)) * plotWidth;
  // Map a score onto a y pixel. Higher scores sit higher on the page.
  const yOf = (score: number): number =>
    PAD_TOP + (1 - (score - scoreStart) / (scoreEnd - scoreStart)) * plotHeight;
  // Choose a point from the keyboard.
  const onKey = (event: KeyboardEvent<SVGGElement>, index: number): void => {
    // Enter or space selects the point.
    if (event.key === "Enter" || event.key === " ") {
      // Keep the page from scrolling on space.
      event.preventDefault();
      // Select this design.
      onSelect(index);
    }
  };
  // Draw the chart and a button list so small screens can select a point.
  return (
    // Section wrapper.
    <section className="flex flex-col gap-3">
      {/* Heading. */}
      <h3 className="font-display text-lg font-semibold text-stone-900">Pareto set</h3>
      {/* How many designs came back. */}
      <p className="text-sm text-stone-600">{points.length} designs. Cost across, score up.</p>
      {/* The scatter plot. */}
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="group"
        aria-label="Pareto chart of cost and score"
        className="h-auto w-full rounded-lg border border-stone-300 bg-white"
      >
        {/* Plot frame. */}
        <rect
          x={PAD_LEFT}
          y={PAD_TOP}
          width={plotWidth}
          height={plotHeight}
          fill="#fbf5ec"
          stroke="#e7dccb"
        />
        {/* Cost axis title. */}
        <text x={PAD_LEFT + plotWidth / 2} y={HEIGHT - 6} textAnchor="middle" fontSize="12" fill="#5a4e44">
          Cost (synthetic INR)
        </text>
        {/* Score axis title. */}
        <text
          x="16"
          y={PAD_TOP + plotHeight / 2}
          textAnchor="middle"
          fontSize="12"
          fill="#5a4e44"
          transform={`rotate(-90 16 ${PAD_TOP + plotHeight / 2})`}
        >
          Score
        </text>
        {/* Low cost tick. */}
        <text x={PAD_LEFT} y={HEIGHT - 18} fontSize="11" fill="#6b5d52">
          {formatInrTick(minCost)}
        </text>
        {/* High cost tick. */}
        <text x={WIDTH - PAD_RIGHT} y={HEIGHT - 18} textAnchor="end" fontSize="11" fill="#6b5d52">
          {formatInrTick(maxCost)}
        </text>
        {/* High score tick. */}
        <text x={PAD_LEFT - 6} y={PAD_TOP + 4} textAnchor="end" fontSize="11" fill="#6b5d52">
          {maxScore.toFixed(2)}
        </text>
        {/* Low score tick. */}
        <text x={PAD_LEFT - 6} y={PAD_TOP + plotHeight} textAnchor="end" fontSize="11" fill="#6b5d52">
          {minScore.toFixed(2)}
        </text>
        {/* One marker per returned point. */}
        {points.map((point, index) => {
          // Pixel x.
          const cx = xOf(point.design.cost);
          // Pixel y.
          const cy = yOf(point.design.score);
          // This is the design currently shown.
          const active = index === selected;
          // Put the label on the left when the point is near the right edge.
          const labelOnLeft = cx > WIDTH - 130;
          // Joined API labels. One point can carry several.
          const label = point.labels.join(", ");
          // Marker plus its label.
          return (
            <g
              key={point.design.design_id}
              role="button"
              tabIndex={0}
              aria-pressed={active}
              aria-label={label}
              onClick={() => onSelect(index)}
              onKeyDown={(event) => onKey(event, index)}
              className="cursor-pointer"
            >
              {/* Larger invisible hit target. */}
              <circle cx={cx} cy={cy} r={14} fill="transparent" />
              {/* Visible point. */}
              <circle
                cx={cx}
                cy={cy}
                r={active ? 8 : 6}
                fill={active ? "#3b2a20" : "#c8643c"}
                stroke="#3b2a20"
                strokeWidth={active ? 2 : 1}
              />
              {/* API labels beside the point. */}
              <text
                x={labelOnLeft ? cx - 12 : cx + 12}
                y={cy + 4}
                textAnchor={labelOnLeft ? "end" : "start"}
                fontSize="11"
                fill="#18181b"
              >
                {label}
              </text>
            </g>
          );
        })}
      </svg>
      {/* The same choices as buttons, for a small screen and a keyboard. */}
      <ul className="flex flex-col gap-2">
        {/* One button per point. */}
        {points.map((point, index) => {
          // Whether this row is the selected design.
          const active = index === selected;
          // Button row.
          return (
            <li key={point.design.design_id}>
              {/* Selects this design for the plan, the bill, and the boxes. */}
              <button
                type="button"
                aria-pressed={active}
                onClick={() => onSelect(index)}
                className={
                  active
                    ? "w-full rounded-md border border-stone-900 bg-stone-900 px-3 py-2 text-left text-sm text-white"
                    : "w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-left text-sm text-stone-900"
                }
              >
                {/* Raw labels, cost, and score. */}
                {point.labels.join(", ")} · {formatInr(point.design.cost)} · score {point.design.score.toFixed(3)}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// Memoized export: re-renders only when its props change.
export const ParetoChart = memo(ParetoChartImpl);
