"use client"; // The table renders the selected point. It does not parse object ids.

import { memo } from "react"; // Skip re-renders when props are unchanged.

// Price disclosure.
import { PRICE_NOTE } from "@/lib/constants";

// Rupee formatting.
import { formatInr } from "@/lib/format";

// Line and design shapes.
import type { BomLine, Design } from "@/lib/types";

// Props for one selected design.
type BomTableProps = {
  // Design whose cost is the total.
  design: Design;
  // Lines returned beside that design.
  lines: BomLine[];
};

// Bill of materials. The total is design.cost.
function BomTableImpl({ design, lines }: BomTableProps) {
  // Sum of the line totals, used only to notice a mismatch.
  const sum = lines.reduce((total, line) => total + line.line_total, 0);
  // True when the lines do not add up to the design cost.
  const differs = Math.abs(sum - design.cost) > 0.009;
  // The table and the synthetic-price note.
  return (
    // Section wrapper.
    <section className="flex flex-col gap-3">
      {/* Heading. */}
      <h3 className="font-display text-lg font-semibold text-stone-900">Bill of materials</h3>
      {/* Price disclosure. */}
      <p className="text-sm text-stone-600">{PRICE_NOTE}</p>
      {/* Horizontal scroll on a narrow screen. */}
      <div className="overflow-x-auto">
        {/* BOM table. */}
        <table className="w-full min-w-[36rem] border-collapse text-left text-sm">
          {/* Column names required by this phase. */}
          <thead>
            {/* Header row. */}
            <tr className="border-b border-stone-300 text-stone-600">
              {/* Catalog id from the line. */}
              <th className="px-2 py-1 font-medium">item_id</th>
              {/* Class. */}
              <th className="px-2 py-1 font-medium">category</th>
              {/* Count. */}
              <th className="px-2 py-1 font-medium">qty</th>
              {/* Unit price. */}
              <th className="px-2 py-1 font-medium">unit_price</th>
              {/* Line total. */}
              <th className="px-2 py-1 font-medium">line_total</th>
            </tr>
          </thead>
          {/* Lines plus the total. */}
          <tbody>
            {/* One purchased row. */}
            {lines.map((line) => (
              <tr key={`${line.item_id}-${line.category}`} className="border-b border-stone-200">
                {/* Catalog id. */}
                <td className="px-2 py-1">{line.item_id}</td>
                {/* Category. */}
                <td className="px-2 py-1">{line.category}</td>
                {/* Quantity. */}
                <td className="px-2 py-1">{line.qty}</td>
                {/* Unit price. */}
                <td className="px-2 py-1">{formatInr(line.unit_price)}</td>
                {/* Line total. */}
                <td className="px-2 py-1">{formatInr(line.line_total)}</td>
              </tr>
            ))}
            {/* Total row. The figure is the design cost. */}
            <tr className="font-semibold text-stone-900">
              {/* Label spanning the first four columns. */}
              <th className="px-2 py-2 text-left" colSpan={4}>
                Total
              </th>
              {/* design.cost. */}
              <td className="px-2 py-2">{formatInr(design.cost)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      {/* A mismatch should be visible. The solver's contract says the two are equal. */}
      {differs ? (
        <p className="text-sm text-red-800">
          Line totals sum to {formatInr(sum)}. Design cost is {formatInr(design.cost)}.
        </p>
      ) : null}
    </section>
  );
}

// Memoized export: re-renders only when its props change.
export const BomTable = memo(BomTableImpl);
