// Floor geometry shared by the plan and the box view.
// Room length is x. Room width is y. Position is the footprint centre.
// A quarter turn of 90 or 270 swaps length and width. Height is never swapped.

// Scene records the plan and the boxes both read.
import type { SceneObject, SceneOpening } from "@/lib/types";

// Visual wall thickness in metres. It sits outside the room so it does not cover furniture.
const WALL_THICKNESS_M = 0.08;

// One axis-aligned box in three.js space: x, height y, floor-y as z.
export type Box3 = {
  // Centre of the box.
  position: [number, number, number];
  // Full size of the box.
  size: [number, number, number];
};

// A door or window filling a gap in a wall.
export type OpeningBox = Box3 & {
  // Which paint to use.
  kind: "door" | "window";
};

// A span along one wall, in metres from that wall's start.
type Span = {
  // Inclusive start.
  start: number;
  // Exclusive end.
  end: number;
};

// Floor extents after a right-angle rotation. Matches the solver and the checker.
export function worldFootprint(
  rotationDegrees: number,
  length: number,
  width: number,
): { x: number; y: number } {
  // Reduce degrees to a quarter turn.
  const quarter = Math.round(rotationDegrees / 90);
  // JavaScript remainder can be negative, so shift it into 0..3.
  const turn = ((quarter % 4) + 4) % 4;
  // 90 and 270 put local width on x and local length on y.
  if (turn === 1 || turn === 3) {
    // Swapped footprint.
    return { x: width, y: length };
  }
  // 0 and 180 keep local length on x and local width on y.
  return { x: length, y: width };
}

// Axis-aligned footprint in floor coordinates, origin at the south-west corner.
export function footprintRect(obj: SceneObject): {
  x: number;
  y: number;
  width: number;
  height: number;
} {
  // Rotated floor edges.
  const footprint = worldFootprint(obj.rotation, obj.dimensions[0], obj.dimensions[1]);
  // Minimum x of the rectangle.
  const x = obj.position[0] - footprint.x / 2;
  // Minimum y of the rectangle.
  const y = obj.position[1] - footprint.y / 2;
  // Return the rectangle the plan draws.
  return { x, y, width: footprint.x, height: footprint.y };
}

// Box for one piece of furniture. Floor x is world X, floor y is world Z, height is world Y.
export function furnitureBox(obj: SceneObject): Box3 {
  // Rotated floor edges.
  const footprint = worldFootprint(obj.rotation, obj.dimensions[0], obj.dimensions[1]);
  // Centre x, half the height, centre z.
  return {
    // The box sits on the floor because its centre is at half its height.
    position: [obj.position[0], obj.dimensions[2] / 2, obj.position[1]],
    // World size. Local length and width may be swapped. Height is not.
    size: [footprint.x, obj.dimensions[2], footprint.y],
  };
}

// Solid parts of a wall after openings are cut out.
function solidSpans(wallLength: number, cuts: Span[]): Span[] {
  // Clip every opening to the wall and drop empty cuts.
  const clipped = cuts
    // Clamp each cut.
    .map((cut) => ({
      // Do not start before the wall.
      start: Math.max(0, Math.min(wallLength, cut.start)),
      // Do not end after the wall.
      end: Math.max(0, Math.min(wallLength, cut.end)),
    }))
    // Drop cuts that missed the wall.
    .filter((cut) => cut.end > cut.start)
    // Walk the wall from its start.
    .sort((left, right) => left.start - right.start);
  // Solid pieces collected so far.
  const spans: Span[] = [];
  // Next free metre along the wall.
  let cursor = 0;
  // Leave a gap for each opening.
  for (const cut of clipped) {
    // There is solid wall before this opening.
    if (cut.start > cursor + 1e-9) {
      // Record that solid piece.
      spans.push({ start: cursor, end: cut.start });
    }
    // Move past the opening. Overlapping openings share one gap.
    cursor = Math.max(cursor, cut.end);
  }
  // Solid wall after the last opening.
  if (cursor < wallLength - 1e-9) {
    // Record the remaining piece.
    spans.push({ start: cursor, end: wallLength });
  }
  // Return the pieces to extrude.
  return spans;
}

// Openings on one wall, as spans along that wall.
function cutsFor(openings: SceneOpening[], wall: string): Span[] {
  // Keep openings whose wall name matches, ignoring case.
  return openings
    // This wall only.
    .filter((opening) => opening.wall.toLowerCase() === wall)
    // Position is the start. Width extends toward the other end.
    .map((opening) => ({
      // Start metre.
      start: opening.position,
      // End metre.
      end: opening.position + opening.width,
    }));
}

// Vertical size of a door or window mark. This is only a drawing. It is not a solver input.
function markHeight(
  kind: "door" | "window",
  roomHeight: number,
): { height: number; centerY: number } | null {
  // A door stands on the floor.
  if (kind === "door") {
    // Cap the drawn door at 2.05 m, and never taller than the room.
    const height = Math.min(2.05, roomHeight);
    // A non-positive room cannot draw a door.
    if (height <= 0) {
      // Skip the mark.
      return null;
    }
    // Centre is half the drawn height.
    return { height, centerY: height / 2 };
  }
  // A window sits above a sill.
  const sill = 0.9;
  // Head is below the ceiling and at most 2.15 m.
  const head = Math.min(roomHeight - 0.15, 2.15);
  // Drawn window height.
  const height = head - sill;
  // Skip a window that does not fit this ceiling.
  if (height <= 0.05) {
    // No mark.
    return null;
  }
  // Centre between sill and head.
  return { height, centerY: sill + height / 2 };
}

// Add wall boxes that run along x.
function pushAlongX(walls: Box3[], spans: Span[], roomHeight: number, z: number): void {
  // One box per solid span.
  for (const span of spans) {
    // Length of this solid piece.
    const sizeX = span.end - span.start;
    // Skip a numerical sliver.
    if (sizeX <= 1e-6) {
      // Next span.
      continue;
    }
    // Box outside the floor, full room height.
    walls.push({
      // Midpoint of the span, half the room height, and the wall's z.
      position: [span.start + sizeX / 2, roomHeight / 2, z],
      // Span, room height, and the visual thickness.
      size: [sizeX, roomHeight, WALL_THICKNESS_M],
    });
  }
}

// Add wall boxes that run along z (floor y).
function pushAlongZ(walls: Box3[], spans: Span[], roomHeight: number, x: number): void {
  // One box per solid span.
  for (const span of spans) {
    // Length of this solid piece along z.
    const sizeZ = span.end - span.start;
    // Skip a numerical sliver.
    if (sizeZ <= 1e-6) {
      // Next span.
      continue;
    }
    // Box outside the floor, full room height.
    walls.push({
      // The wall's x, half the room height, and the midpoint along z.
      position: [x, roomHeight / 2, span.start + sizeZ / 2],
      // Thickness, room height, and the span.
      size: [WALL_THICKNESS_M, roomHeight, sizeZ],
    });
  }
}

// Add one opening mark in the wall gap.
function pushMark(
  marks: OpeningBox[],
  opening: SceneOpening,
  roomLength: number,
  roomWidth: number,
  roomHeight: number,
): void {
  // Normalised wall name.
  const wall = opening.wall.toLowerCase();
  // North and south run along length. East and west run along width.
  const along = wall === "east" || wall === "west" ? roomWidth : roomLength;
  // Clip the opening to the wall.
  const start = Math.max(0, opening.position);
  // Clip the far end.
  const end = Math.min(along, opening.position + opening.width);
  // Visible span.
  const span = end - start;
  // Nothing to draw when the opening misses the wall.
  if (span <= 1e-6) {
    // Skip it.
    return;
  }
  // Windows and everything else that is not a window are drawn as doors.
  const kind = opening.type.toLowerCase() === "window" ? "window" : "door";
  // Vertical placement.
  const vertical = markHeight(kind, roomHeight);
  // The ceiling is too low for this mark.
  if (vertical === null) {
    // Skip it.
    return;
  }
  // Midpoint along the wall.
  const mid = start + span / 2;
  // South wall, outside the floor, at negative z.
  if (wall === "south") {
    // Record the mark.
    marks.push({
      // Paint.
      kind,
      // Centre.
      position: [mid, vertical.centerY, -WALL_THICKNESS_M / 2],
      // Size.
      size: [span, vertical.height, WALL_THICKNESS_M],
    });
    // Done with this opening.
    return;
  }
  // North wall, outside the far z edge.
  if (wall === "north") {
    // Record the mark.
    marks.push({
      // Paint.
      kind,
      // Centre.
      position: [mid, vertical.centerY, roomWidth + WALL_THICKNESS_M / 2],
      // Size.
      size: [span, vertical.height, WALL_THICKNESS_M],
    });
    // Done with this opening.
    return;
  }
  // West wall, outside the x origin.
  if (wall === "west") {
    // Record the mark.
    marks.push({
      // Paint.
      kind,
      // Centre. The span runs along z.
      position: [-WALL_THICKNESS_M / 2, vertical.centerY, mid],
      // Size.
      size: [WALL_THICKNESS_M, vertical.height, span],
    });
    // Done with this opening.
    return;
  }
  // East wall, outside the far x edge.
  if (wall === "east") {
    // Record the mark.
    marks.push({
      // Paint.
      kind,
      // Centre.
      position: [roomLength + WALL_THICKNESS_M / 2, vertical.centerY, mid],
      // Size.
      size: [WALL_THICKNESS_M, vertical.height, span],
    });
  }
}

// Walls and opening marks for the box view. Furniture is separate.
export function roomShell(
  roomLength: number,
  roomWidth: number,
  roomHeight: number,
  openings: SceneOpening[],
): { walls: Box3[]; marks: OpeningBox[] } {
  // Wall boxes.
  const walls: Box3[] = [];
  // Opening marks.
  const marks: OpeningBox[] = [];
  // South wall along x, just outside y = 0.
  pushAlongX(walls, solidSpans(roomLength, cutsFor(openings, "south")), roomHeight, -WALL_THICKNESS_M / 2);
  // North wall along x, just outside y = width.
  pushAlongX(
    walls,
    solidSpans(roomLength, cutsFor(openings, "north")),
    roomHeight,
    roomWidth + WALL_THICKNESS_M / 2,
  );
  // West wall along y, just outside x = 0.
  pushAlongZ(walls, solidSpans(roomWidth, cutsFor(openings, "west")), roomHeight, -WALL_THICKNESS_M / 2);
  // East wall along y, just outside x = length.
  pushAlongZ(
    walls,
    solidSpans(roomWidth, cutsFor(openings, "east")),
    roomHeight,
    roomLength + WALL_THICKNESS_M / 2,
  );
  // One mark per opening.
  for (const opening of openings) {
    // Place it in the matching gap.
    pushMark(marks, opening, roomLength, roomWidth, roomHeight);
  }
  // Return both lists.
  return { walls, marks };
}
