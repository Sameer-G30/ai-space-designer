"use client"; // The plan is drawn in the browser from the selected design.

// Inset distance and the frame note.
import { LOW_CONFIDENCE_INSET_M, PLAN_NOTE, planColor, readableToken } from "@/lib/constants";

// Footprint math shared with the box view.
import { footprintRect } from "@/lib/geometry";

// Scene and object shapes.
import type { SceneGraph, SceneObject } from "@/lib/types";

// Props. Openings come from the scene. Furniture comes from the selected design.
type PlanViewProps = {
  // Stored room, including openings and confidence.
  scene: SceneGraph;
  // Objects in the selected design.
  objects: SceneObject[];
};

// Margin around the room, in metres, so the north mark fits.
const PAD = 0.55;

// Top-down plan in the solver frame. North is up.
export function PlanView({ scene, objects }: PlanViewProps) {
  // Room length, the x axis.
  const length = scene.dimensions.length;
  // Room width, the y axis.
  const width = scene.dimensions.width;
  // SVG width in metre units.
  const viewWidth = length + PAD * 2;
  // SVG height in metre units.
  const viewHeight = width + PAD * 2;
  // Whole-metre grid lines along x, excluding the walls.
  const verticalMetres: number[] = [];
  // Step one metre at a time inside the room.
  for (let metre = 1; metre < length; metre += 1) {
    // Record this grid line.
    verticalMetres.push(metre);
  }
  // Whole-metre grid lines along y.
  const horizontalMetres: number[] = [];
  // Step one metre at a time inside the room.
  for (let metre = 1; metre < width; metre += 1) {
    // Record this grid line.
    horizontalMetres.push(metre);
  }
  // Draw the inset only when both axes can hold it.
  const showInset = length > LOW_CONFIDENCE_INSET_M * 2 && width > LOW_CONFIDENCE_INSET_M * 2;
  // The drawing plus a text table of the same coordinates.
  return (
    // Section wrapper.
    <section className="flex flex-col gap-3">
      {/* Heading. */}
      <h3 className="text-base font-semibold text-zinc-900">2D plan</h3>
      {/* Frame reminder. */}
      <p className="text-sm text-zinc-600">{PLAN_NOTE}</p>
      {/* The plan. */}
      <svg
        viewBox={`0 0 ${viewWidth} ${viewHeight}`}
        role="img"
        aria-label={`Top view of ${readableToken(scene.room_type)} with ${objects.length} objects`}
        className="h-auto w-full rounded-lg border border-zinc-300 bg-white"
      >
        {/* North mark. */}
        <text x={PAD + length / 2} y={PAD * 0.55} textAnchor="middle" fontSize="0.22" fill="#3f3f46">
          N
        </text>
        {/* One-metre grid. */}
        {verticalMetres.map((metre) => (
          // A north-south grid line.
          <line
            key={`x-${metre}`}
            x1={PAD + metre}
            y1={PAD}
            x2={PAD + metre}
            y2={PAD + width}
            stroke="#e4e4e7"
            strokeWidth="0.015"
          />
        ))}
        {/* East-west grid lines. SVG y is flipped, so floor y = metre is near the bottom when metre is small. */}
        {horizontalMetres.map((metre) => (
          // A grid line at this floor y.
          <line
            key={`y-${metre}`}
            x1={PAD}
            y1={PAD + (width - metre)}
            x2={PAD + length}
            y2={PAD + (width - metre)}
            stroke="#e4e4e7"
            strokeWidth="0.015"
          />
        ))}
        {/* Room boundary. */}
        <rect
          x={PAD}
          y={PAD}
          width={length}
          height={width}
          fill="#fafafa"
          stroke="#111111"
          strokeWidth="0.06"
        />
        {/* Low-confidence inset. The solver keeps furniture inside this dashed rectangle. */}
        {scene.dimensions.confidence === "low" && showInset ? (
          <rect
            x={PAD + LOW_CONFIDENCE_INSET_M}
            y={PAD + LOW_CONFIDENCE_INSET_M}
            width={length - LOW_CONFIDENCE_INSET_M * 2}
            height={width - LOW_CONFIDENCE_INSET_M * 2}
            fill="none"
            stroke="#a16207"
            strokeDasharray="0.08 0.06"
            strokeWidth="0.03"
          />
        ) : null}
        {/* Openings, drawn on the wall they belong to. */}
        {scene.openings.map((opening, index) => {
          // Windows and doors use different colours.
          const stroke = opening.type.toLowerCase() === "window" ? "#4895ef" : "#9b2226";
          // North and south run along x.
          const horizontal = opening.wall.toLowerCase() === "north" || opening.wall.toLowerCase() === "south";
          // North is the top edge. South is the bottom edge.
          const wallY =
            opening.wall.toLowerCase() === "north" ? PAD : opening.wall.toLowerCase() === "south" ? PAD + width : null;
          // East is the right edge. West is the left edge.
          const wallX =
            opening.wall.toLowerCase() === "east"
              ? PAD + length
              : opening.wall.toLowerCase() === "west"
                ? PAD
                : null;
          // Skip a wall name this plan does not know.
          if (horizontal && wallY === null) {
            // Nothing to draw.
            return null;
          }
          // Skip an unknown vertical wall.
          if (!horizontal && wallX === null) {
            // Nothing to draw.
            return null;
          }
          // Horizontal opening.
          if (horizontal && wallY !== null) {
            // Line along the wall.
            return (
              <line
                key={`opening-${index}`}
                x1={PAD + opening.position}
                y1={wallY}
                x2={PAD + opening.position + opening.width}
                y2={wallY}
                stroke={stroke}
                strokeWidth="0.14"
                strokeLinecap="butt"
              />
            );
          }
          // Vertical opening. Floor y grows north, which is up, so the SVG y is flipped.
          const yStart = PAD + (width - (opening.position + opening.width));
          // Far end of the opening.
          const yEnd = PAD + (width - opening.position);
          // Line along the east or west wall.
          return (
            <line
              key={`opening-${index}`}
              x1={wallX ?? 0}
              y1={yStart}
              x2={wallX ?? 0}
              y2={yEnd}
              stroke={stroke}
              strokeWidth="0.14"
              strokeLinecap="butt"
            />
          );
        })}
        {/* Furniture footprints, including rotation. */}
        {objects.map((obj, index) => {
          // Floor rectangle after rotation.
          const rect = footprintRect(obj);
          // SVG x of the west edge.
          const sx = PAD + rect.x;
          // SVG y of the north edge.
          const sy = PAD + (width - (rect.y + rect.height));
          // Stable colour.
          const fill = planColor(index);
          // Footprint plus its class name.
          return (
            <g key={`${obj.id}-${index}`}>
              {/* Footprint. A kept object uses a dashed stroke. */}
              <rect
                x={sx}
                y={sy}
                width={rect.width}
                height={rect.height}
                fill={fill}
                stroke="#222222"
                strokeWidth="0.03"
                strokeDasharray={obj.must_keep ? "0.08 0.05" : undefined}
              >
                {/* Hover text is the object id and class, not a parsed catalog id. */}
                <title>{`${obj.id} ${obj.type}`}</title>
              </rect>
              {/* Class name at the centre. */}
              <text
                x={sx + rect.width / 2}
                y={sy + rect.height / 2}
                fontSize="0.16"
                textAnchor="middle"
                dominantBaseline="middle"
                fill="#18181b"
              >
                {readableToken(obj.type)}
              </text>
            </g>
          );
        })}
      </svg>
      {/* Legend for openings and the inset. */}
      <p className="text-sm text-zinc-600">
        Red marks a door. Blue marks a window. A dashed furniture edge is kept. A dashed amber rectangle is the 0.10 m low-confidence inset.
      </p>
      {/* Coordinates as text, so the selected design can be checked without reading the drawing. */}
      <div className="overflow-x-auto">
        {/* Placement table. */}
        <table className="w-full min-w-[36rem] border-collapse text-left text-sm">
          {/* Column names. */}
          <thead>
            {/* Header row. */}
            <tr className="border-b border-zinc-300 text-zinc-600">
              {/* Object id. */}
              <th className="px-2 py-1 font-medium">id</th>
              {/* Class. */}
              <th className="px-2 py-1 font-medium">type</th>
              {/* Centre. */}
              <th className="px-2 py-1 font-medium">centre x, y (m)</th>
              {/* Rotation. */}
              <th className="px-2 py-1 font-medium">rotation</th>
              {/* Local size. */}
              <th className="px-2 py-1 font-medium">length, width, height (m)</th>
            </tr>
          </thead>
          {/* One row per placed object. */}
          <tbody>
            {/* Design objects in solver order. */}
            {objects.map((obj, index) => (
              <tr key={`${obj.id}-${index}`} className="border-b border-zinc-200">
                {/* Id, shown whole. */}
                <td className="px-2 py-1">{obj.id}</td>
                {/* Class, with a colour swatch that matches the plan and the boxes. */}
                <td className="px-2 py-1">
                  {/* Swatch. */}
                  <span
                    className="mr-2 inline-block h-3 w-3 rounded-sm border border-zinc-400"
                    style={{ backgroundColor: planColor(index) }}
                  />
                  {/* Class name. */}
                  {obj.type}
                </td>
                {/* Centre, two decimals. */}
                <td className="px-2 py-1">
                  {obj.position[0].toFixed(2)}, {obj.position[1].toFixed(2)}
                </td>
                {/* Degrees. */}
                <td className="px-2 py-1">{obj.rotation}</td>
                {/* Local dimensions. Rotation is a separate column. */}
                <td className="px-2 py-1">
                  {obj.dimensions[0].toFixed(2)}, {obj.dimensions[1].toFixed(2)}, {obj.dimensions[2].toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
