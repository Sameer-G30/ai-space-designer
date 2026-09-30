// Read proxy JSON into the shapes the page draws. A bad body is not drawn.

// Wire shapes.
import type {
  BomLine,
  ConfidenceName,
  Design,
  FailureView,
  InfeasibleBody,
  ObjectiveWeights,
  OptimizerTrace,
  ParetoBody,
  ParetoPoint,
  SceneGraph,
  SceneObject,
  SceneOpening,
} from "@/lib/types";

// The six weight names, in contract order.
import { WEIGHT_NAMES } from "@/lib/constants";

// A parsed optimize call.
export type OptimizeRead =
  // HTTP or proxy failure. Nothing is drawn.
  | { kind: "failure"; failure: FailureView }
  // Feasible set.
  | { kind: "pareto"; result: ParetoBody }
  // Readable infeasible result. Nothing is drawn.
  | { kind: "infeasible"; result: InfeasibleBody }
  // 200 body this page does not understand. Nothing is drawn.
  | { kind: "bad"; detail: string };

// A parsed scene call.
export type SceneRead =
  // The stored scene.
  | { kind: "scene"; scene: SceneGraph }
  // HTTP or proxy failure.
  | { kind: "failure"; failure: FailureView }
  // 200 body this page does not understand.
  | { kind: "bad"; detail: string };

// True for a plain object record.
function isRecord(value: unknown): value is Record<string, unknown> {
  // Arrays are objects in JavaScript. Reject them.
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// Read a finite number.
function readNumber(value: unknown): number | null {
  // Only finite numbers.
  if (typeof value !== "number" || !Number.isFinite(value)) {
    // Reject anything else.
    return null;
  }
  // Return it.
  return value;
}

// Read a non-empty string.
function readText(value: unknown): string | null {
  // Empty strings are not ids.
  if (typeof value !== "string" || value.trim() === "") {
    // Reject.
    return null;
  }
  // Return the string unchanged, including surrounding spaces the API may have stored.
  return value;
}

// Read the proxy failure envelope, or a generic HTTP line.
function readFailure(body: unknown, httpStatus: number): FailureView {
  // Our routes send ok:false plus detail.
  if (isRecord(body) && typeof body.detail === "string" && body.detail.trim() !== "") {
    // Prefer the status stored in the envelope.
    const statusCode =
      typeof body.statusCode === "number" || body.statusCode === null ? body.statusCode : httpStatus;
    // Return the panel contents.
    return { statusCode, detail: body.detail };
  }
  // No usable envelope.
  return { statusCode: httpStatus, detail: `HTTP ${httpStatus}` };
}

// Read the six weights.
function readWeights(value: unknown): ObjectiveWeights | null {
  // Weights are an object.
  if (!isRecord(value)) {
    // Reject.
    return null;
  }
  // Accumulator.
  const weights = {} as ObjectiveWeights;
  // Every name is required.
  for (const name of WEIGHT_NAMES) {
    // This term.
    const parsed = readNumber(value[name]);
    // Missing or non-numeric.
    if (parsed === null) {
      // Reject the whole object.
      return null;
    }
    // Store it.
    weights[name] = parsed;
  }
  // All six were present.
  return weights;
}

// Read one confidence token.
function readConfidence(value: unknown): ConfidenceName | null {
  // Only the three tokens.
  if (value === "low" || value === "medium" || value === "high") {
    // Return it.
    return value;
  }
  // Reject.
  return null;
}

// Read one scene object.
function readObject(value: unknown): SceneObject | null {
  // Object shape.
  if (!isRecord(value)) {
    // Reject.
    return null;
  }
  // Id.
  const id = readText(value.id);
  // Type.
  const type = readText(value.type);
  // Position array.
  const position = value.position;
  // Rotation.
  const rotation = readNumber(value.rotation);
  // Dimensions array.
  const dimensions = value.dimensions;
  // Confidence.
  const confidence = readConfidence(value.confidence);
  // Position must be a pair of numbers.
  if (!Array.isArray(position) || position.length !== 2) {
    // Reject.
    return null;
  }
  // Centre x.
  const x = readNumber(position[0]);
  // Centre y.
  const y = readNumber(position[1]);
  // Dimensions must be a triple of numbers.
  if (!Array.isArray(dimensions) || dimensions.length !== 3) {
    // Reject.
    return null;
  }
  // Length.
  const length = readNumber(dimensions[0]);
  // Width.
  const width = readNumber(dimensions[1]);
  // Height.
  const height = readNumber(dimensions[2]);
  // Flags.
  if (typeof value.movable !== "boolean" || typeof value.must_keep !== "boolean") {
    // Reject.
    return null;
  }
  // Every required field must be present.
  if (
    id === null ||
    type === null ||
    x === null ||
    y === null ||
    rotation === null ||
    length === null ||
    width === null ||
    height === null ||
    confidence === null
  ) {
    // Reject.
    return null;
  }
  // Copy the known fields only.
  return {
    // Id.
    id,
    // Type.
    type,
    // Centre.
    position: [x, y],
    // Degrees.
    rotation,
    // Local size.
    dimensions: [length, width, height],
    // Movable flag.
    movable: value.movable,
    // Must-keep flag.
    must_keep: value.must_keep,
    // Confidence.
    confidence,
  };
}

// Read one opening.
function readOpening(value: unknown): SceneOpening | null {
  // Object shape.
  if (!isRecord(value)) {
    // Reject.
    return null;
  }
  // Type.
  const type = readText(value.type);
  // Wall.
  const wall = readText(value.wall);
  // Position.
  const position = readNumber(value.position);
  // Width.
  const width = readNumber(value.width);
  // All four are required. Width must be positive to draw.
  if (type === null || wall === null || position === null || width === null || width <= 0) {
    // Reject.
    return null;
  }
  // Copy the known fields.
  return { type, wall, position, width };
}

// Read a scene graph echo.
export function readScene(value: unknown): SceneGraph | null {
  // Object shape.
  if (!isRecord(value)) {
    // Reject.
    return null;
  }
  // Id.
  const sceneId = readText(value.scene_id);
  // Room type.
  const roomType = readText(value.room_type);
  // Version.
  const version = readNumber(value.version);
  // Dimensions object.
  if (!isRecord(value.dimensions)) {
    // Reject.
    return null;
  }
  // Length.
  const length = readNumber(value.dimensions.length);
  // Width.
  const width = readNumber(value.dimensions.width);
  // Height.
  const height = readNumber(value.dimensions.height);
  // Confidence.
  const confidence = readConfidence(value.dimensions.confidence);
  // Openings and objects must be arrays.
  if (!Array.isArray(value.openings) || !Array.isArray(value.objects)) {
    // Reject.
    return null;
  }
  // Openings.
  const openings: SceneOpening[] = [];
  // Parse each opening.
  for (const item of value.openings) {
    // One opening.
    const opening = readOpening(item);
    // Stop on the first bad row.
    if (opening === null) {
      // Reject the scene.
      return null;
    }
    // Keep it.
    openings.push(opening);
  }
  // Objects.
  const objects: SceneObject[] = [];
  // Parse each object.
  for (const item of value.objects) {
    // One object.
    const obj = readObject(item);
    // Stop on the first bad row.
    if (obj === null) {
      // Reject the scene.
      return null;
    }
    // Keep it.
    objects.push(obj);
  }
  // The room itself must be complete and positive.
  if (
    sceneId === null ||
    roomType === null ||
    version === null ||
    length === null ||
    width === null ||
    height === null ||
    length <= 0 ||
    width <= 0 ||
    height <= 0 ||
    confidence === null
  ) {
    // Reject.
    return null;
  }
  // Copy the known fields.
  return {
    // Id.
    scene_id: sceneId,
    // Version.
    version,
    // Room type.
    room_type: roomType,
    // Size.
    dimensions: { length, width, height, confidence },
    // Openings.
    openings,
    // Objects.
    objects,
  };
}

// Read one BOM line.
export function readBomLine(value: unknown): BomLine | null {
  // Object shape.
  if (!isRecord(value)) {
    // Reject.
    return null;
  }
  // Catalog id.
  const itemId = readText(value.item_id);
  // Category.
  const category = readText(value.category);
  // Quantity.
  const qty = readNumber(value.qty);
  // Unit price.
  const unitPrice = readNumber(value.unit_price);
  // Line total.
  const lineTotal = readNumber(value.line_total);
  // Quantity must be a positive integer.
  if (itemId === null || category === null || qty === null || !Number.isInteger(qty) || qty < 1) {
    // Reject.
    return null;
  }
  // Prices must be finite. Negative prices are rejected.
  if (unitPrice === null || lineTotal === null || unitPrice < 0 || lineTotal < 0) {
    // Reject.
    return null;
  }
  // Copy the known fields.
  return {
    // Catalog id. This is the only item id the table shows.
    item_id: itemId,
    // Category.
    category,
    // Quantity.
    qty,
    // Unit price.
    unit_price: unitPrice,
    // Line total.
    line_total: lineTotal,
  };
}

// Read a trace that sits beside a design.
export function readTrace(value: unknown): OptimizerTrace | null {
  // Object shape.
  if (!isRecord(value)) {
    // Reject.
    return null;
  }
  // Design id.
  const designId = readText(value.design_id);
  // Terms.
  const terms = readWeights(value.objective_terms);
  // Lists.
  if (!Array.isArray(value.binding_constraints) || !Array.isArray(value.rejected_items) || designId === null || terms === null) {
    // Reject.
    return null;
  }
  // Binding constraints.
  const binding = [];
  // Parse each constraint.
  for (const item of value.binding_constraints) {
    // Object shape.
    if (!isRecord(item)) {
      // Reject the trace.
      return null;
    }
    // Name.
    const name = readText(item.name);
    // Detail.
    const detail = readText(item.detail);
    // Both are required.
    if (name === null || detail === null) {
      // Reject the trace.
      return null;
    }
    // Keep it.
    binding.push({ name, detail });
  }
  // Rejected rows are counted, not listed in full.
  const rejected = [];
  // Parse each rejected row.
  for (const item of value.rejected_items) {
    // Object shape.
    if (!isRecord(item)) {
      // Reject the trace.
      return null;
    }
    // Catalog id.
    const itemId = readText(item.item_id);
    // Reason.
    const reason = readText(item.reason);
    // Both are required.
    if (itemId === null || reason === null) {
      // Reject the trace.
      return null;
    }
    // Keep it.
    rejected.push({ item_id: itemId, reason });
  }
  // Copy the trace.
  return {
    // Design id.
    design_id: designId,
    // Binding constraints.
    binding_constraints: binding,
    // Rejected rows.
    rejected_items: rejected,
    // Terms.
    objective_terms: terms,
  };
}

// Read one design. Trace must not be required inside it.
export function readDesign(value: unknown): Design | null {
  // Object shape.
  if (!isRecord(value)) {
    // Reject.
    return null;
  }
  // Ids.
  const designId = readText(value.design_id);
  // Scene id.
  const sceneId = readText(value.scene_id);
  // Requirement id.
  const requirementId = readText(value.requirement_id);
  // Weights.
  const weights = readWeights(value.weights);
  // Score.
  const score = readNumber(value.score);
  // Cost.
  const cost = readNumber(value.cost);
  // Objects.
  if (!Array.isArray(value.objects) || designId === null || sceneId === null || requirementId === null) {
    // Reject.
    return null;
  }
  // Score and cost are required. Cost cannot be negative.
  if (weights === null || score === null || cost === null || cost < 0) {
    // Reject.
    return null;
  }
  // Parent id is optional. Null is valid. Any other type is not.
  let parent: string | null = null;
  // Missing and null both mean no parent.
  if (value.parent_design_id !== undefined && value.parent_design_id !== null) {
    // A parent must be a non-empty string.
    const parentId = readText(value.parent_design_id);
    // Reject a bad parent.
    if (parentId === null) {
      // Reject the design.
      return null;
    }
    // Keep it.
    parent = parentId;
  }
  // Objects.
  const objects: SceneObject[] = [];
  // Parse each object.
  for (const item of value.objects) {
    // One object.
    const obj = readObject(item);
    // Stop on the first bad row.
    if (obj === null) {
      // Reject the design.
      return null;
    }
    // Keep it.
    objects.push(obj);
  }
  // Copy the design. Do not look for a trace inside it.
  return {
    // Design id.
    design_id: designId,
    // Scene id.
    scene_id: sceneId,
    // Requirement id.
    requirement_id: requirementId,
    // Weights.
    weights,
    // Score.
    score,
    // Cost.
    cost,
    // Objects.
    objects,
    // Parent.
    parent_design_id: parent,
  };
}

// Read one Pareto point.
function readPoint(value: unknown): ParetoPoint | null {
  // Object shape.
  if (!isRecord(value)) {
    // Reject.
    return null;
  }
  // Labels.
  if (!Array.isArray(value.labels) || value.labels.length === 0) {
    // Reject.
    return null;
  }
  // Label strings.
  const labels: string[] = [];
  // Each label must be non-empty text.
  for (const label of value.labels) {
    // One label.
    const text = readText(label);
    // Reject a bad label.
    if (text === null) {
      // Reject the point.
      return null;
    }
    // Keep it.
    labels.push(text);
  }
  // Design.
  const design = readDesign(value.design);
  // Trace beside the design.
  const trace = readTrace(value.trace);
  // Point time.
  const solveTime = readNumber(value.solve_time_ms);
  // BOM.
  if (!Array.isArray(value.bom) || design === null || trace === null || solveTime === null || solveTime < 0) {
    // Reject.
    return null;
  }
  // Lines.
  const bom: BomLine[] = [];
  // Parse each line.
  for (const item of value.bom) {
    // One line.
    const line = readBomLine(item);
    // Stop on the first bad line.
    if (line === null) {
      // Reject the point.
      return null;
    }
    // Keep it.
    bom.push(line);
  }
  // Copy the point.
  return {
    // Labels.
    labels,
    // Design.
    design,
    // Trace.
    trace,
    // BOM.
    bom,
    // Time.
    solve_time_ms: solveTime,
  };
}

// Read a feasible or infeasible optimize result.
function readResult(value: unknown): OptimizeRead {
  // Object shape.
  if (!isRecord(value)) {
    // The page cannot draw this.
    return { kind: "bad", detail: "The API returned a body this page cannot draw." };
  }
  // Infeasible results have a reason and no design.
  if (value.feasible === false) {
    // Reason.
    const reason = readText(value.reason);
    // Time.
    const solveTime = readNumber(value.solve_time_ms);
    // Both are required.
    if (reason === null || solveTime === null || solveTime < 0) {
      // Do not invent a reason.
      return { kind: "bad", detail: "The API returned an infeasible body this page cannot draw." };
    }
    // Show the reason and draw nothing else.
    return { kind: "infeasible", result: { feasible: false, reason, solve_time_ms: solveTime } };
  }
  // Feasible results carry a point list.
  if (value.feasible !== true || !Array.isArray(value.points)) {
    // Unknown discriminator.
    return { kind: "bad", detail: "The API returned a body this page cannot draw." };
  }
  // An empty list is not a design.
  if (value.points.length === 0) {
    // Draw nothing.
    return { kind: "bad", detail: "The API returned no designs." };
  }
  // Set fields.
  const styleBackend = readText(value.style_backend);
  // Candidates.
  const candidates = readNumber(value.candidates_evaluated);
  // Dominated removals.
  const dominated = readNumber(value.dominated_removed);
  // Sweep time.
  const solveTime = readNumber(value.solve_time_ms);
  // All four are required.
  if (
    styleBackend === null ||
    candidates === null ||
    dominated === null ||
    solveTime === null ||
    candidates < 1 ||
    dominated < 0 ||
    solveTime < 0
  ) {
    // Do not draw a partial set.
    return { kind: "bad", detail: "The API returned a Pareto body this page cannot draw." };
  }
  // Points.
  const points: ParetoPoint[] = [];
  // Parse each point. One to eight is normal. A longer list is still shown.
  for (const item of value.points) {
    // One point.
    const point = readPoint(item);
    // Stop on the first bad point.
    if (point === null) {
      // Draw nothing.
      return { kind: "bad", detail: "The API returned a Pareto point this page cannot draw." };
    }
    // Keep it.
    points.push(point);
  }
  // Feasible set.
  return {
    // Kind.
    kind: "pareto",
    // Body.
    result: {
      // Discriminator.
      feasible: true,
      // Points.
      points,
      // Candidates.
      candidates_evaluated: candidates,
      // Removals.
      dominated_removed: dominated,
      // Backend string, shown as returned.
      style_backend: styleBackend,
      // Sweep time.
      solve_time_ms: solveTime,
    },
  };
}

// Read the scene proxy response.
export function parseScenePayload(body: unknown, httpStatus: number): SceneRead {
  // Non-2xx is a failure panel.
  if (httpStatus < 200 || httpStatus >= 300) {
    // Format the envelope.
    return { kind: "failure", failure: readFailure(body, httpStatus) };
  }
  // A 200 envelope can still say ok:false.
  if (isRecord(body) && body.ok === false) {
    // Show that failure.
    return { kind: "failure", failure: readFailure(body, httpStatus) };
  }
  // Success envelope.
  if (!isRecord(body) || body.ok !== true) {
    // Do not draw.
    return { kind: "bad", detail: "The API returned a scene body this page cannot draw." };
  }
  // Parse the scene.
  const scene = readScene(body.scene);
  // The echo was not a scene.
  if (scene === null) {
    // Do not draw.
    return { kind: "bad", detail: "The API returned a scene body this page cannot draw." };
  }
  // Use the stored scene for the plan.
  return { kind: "scene", scene };
}

// Read the optimize proxy response.
export function parseOptimizePayload(body: unknown, httpStatus: number): OptimizeRead {
  // 404, 422, and other errors become the error panel.
  if (httpStatus < 200 || httpStatus >= 300) {
    // Format the envelope.
    return { kind: "failure", failure: readFailure(body, httpStatus) };
  }
  // A 200 envelope can still say ok:false.
  if (isRecord(body) && body.ok === false) {
    // Show that failure.
    return { kind: "failure", failure: readFailure(body, httpStatus) };
  }
  // Success envelope.
  if (!isRecord(body) || body.ok !== true) {
    // Do not draw.
    return { kind: "bad", detail: "The API returned a body this page cannot draw." };
  }
  // Parse the result. feasible:false is a normal 200.
  return readResult(body.result);
}
