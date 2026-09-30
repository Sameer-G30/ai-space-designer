// Read POST /api/designs/[id]/visualize. A bad body is not drawn as an image.

// Failure shape shared with the rest of the page.
import type { FailureView } from "@/lib/types";

// Visualize shapes.
import type { MeshPlacement, VisualizeBody } from "@/lib/types";

// A parsed visualize call.
export type VisualizeRead =
  // The body.
  | { kind: "ok"; value: VisualizeBody }
  // HTTP or proxy failure.
  | { kind: "failure"; failure: FailureView };

// True for a plain object.
function isRecord(value: unknown): value is Record<string, unknown> {
  // Arrays are objects in JavaScript. Reject them.
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// A finite number.
function readNumber(value: unknown): number | null {
  // Only finite numbers.
  if (typeof value !== "number" || !Number.isFinite(value)) {
    // Reject.
    return null;
  }
  // Return it.
  return value;
}

// A string. Empty is allowed for notes.
function readString(value: unknown): string | null {
  // Notes are strings. Empty is a valid note.
  if (typeof value !== "string") {
    // Reject.
    return null;
  }
  // Keep it.
  return value;
}

// A non-empty string.
function readText(value: unknown): string | null {
  // Empty strings are not ids.
  if (typeof value !== "string" || value.trim() === "") {
    // Reject.
    return null;
  }
  // Keep it.
  return value;
}

// Proxy failure, or a generic HTTP line.
function readFailure(body: unknown, httpStatus: number): FailureView {
  // Our routes send ok:false plus detail.
  if (isRecord(body) && body.ok === false && typeof body.detail === "string") {
    // Status from the route, or the HTTP status.
    const statusCode = typeof body.statusCode === "number" ? body.statusCode : httpStatus;
    // Show it.
    return { statusCode, detail: body.detail };
  }
  // Anything else is an HTTP line.
  return { statusCode: httpStatus, detail: `HTTP ${httpStatus}` };
}

// One placement.
function readPlacement(value: unknown): MeshPlacement | null {
  // Object.
  if (!isRecord(value)) {
    // Reject.
    return null;
  }
  // Id.
  const objectId = readText(value.object_id);
  // Class.
  const category = readText(value.category);
  // Kind.
  const kind = value.kind === "glb" || value.kind === "box" ? value.kind : null;
  // Centre.
  const position = value.position;
  // Size.
  const dimensions = value.dimensions;
  // Rotation.
  const rotation = readNumber(value.rotation);
  // Required fields.
  if (
    objectId === null ||
    category === null ||
    kind === null ||
    rotation === null ||
    !Array.isArray(position) ||
    position.length !== 2 ||
    !Array.isArray(dimensions) ||
    dimensions.length !== 3
  ) {
    // Reject.
    return null;
  }
  // Centre numbers.
  const x = readNumber(position[0]);
  // Y.
  const y = readNumber(position[1]);
  // Length.
  const length = readNumber(dimensions[0]);
  // Width.
  const width = readNumber(dimensions[1]);
  // Height.
  const height = readNumber(dimensions[2]);
  // All finite.
  if (x === null || y === null || length === null || width === null || height === null) {
    // Reject.
    return null;
  }
  // Optional catalog id.
  const itemId = value.item_id === null ? null : readText(value.item_id);
  // A non-null bad id is a reject.
  if (value.item_id !== null && itemId === null) {
    // Reject.
    return null;
  }
  // Optional uid.
  const uid = value.objaverse_uid === null ? null : readText(value.objaverse_uid);
  // A non-null bad uid is a reject.
  if (value.objaverse_uid !== null && uid === null) {
    // Reject.
    return null;
  }
  // Placement.
  return {
    object_id: objectId,
    category,
    item_id: itemId,
    kind,
    objaverse_uid: uid,
    position: [x, y],
    rotation,
    dimensions: [length, width, height],
  };
}

// Optional PNG payload.
function readPng(value: unknown): string | null | undefined {
  // Null is allowed.
  if (value === null) {
    // No image.
    return null;
  }
  // A non-empty base64 string.
  if (typeof value === "string" && value.length > 0) {
    // Keep it.
    return value;
  }
  // Reject.
  return undefined;
}

// Read the proxy body.
export function parseVisualize(body: unknown, httpStatus: number): VisualizeRead {
  // HTTP errors.
  if (httpStatus < 200 || httpStatus >= 300) {
    // Failure panel.
    return { kind: "failure", failure: readFailure(body, httpStatus) };
  }
  // Success envelope.
  if (!isRecord(body) || body.ok !== true || !isRecord(body.result)) {
    // Unreadable.
    return { kind: "failure", failure: { statusCode: httpStatus, detail: "The visualize response could not be read." } };
  }
  // Payload.
  const result = body.result;
  // Design id.
  const designId = readText(result.design_id);
  // Status strings.
  const imageStatus = result.image_status === "generated" || result.image_status === "not_run" ? result.image_status : null;
  // Consistency.
  const consistency =
    result.consistency_status === "matched" ||
    result.consistency_status === "mismatched" ||
    result.consistency_status === "not_run"
      ? result.consistency_status
      : null;
  // Critic.
  const critic = result.critic_status === "advisory" || result.critic_status === "not_run" ? result.critic_status : null;
  // Notes.
  const imageNote = readString(result.image_note);
  // Consistency note.
  const consistencyNote = readString(result.consistency_note);
  // Critic note.
  const criticNote = readString(result.critic_note);
  // Attempts.
  const attempts = readNumber(result.consistency_attempts);
  // Flag.
  const unchanged = result.design_unchanged === true;
  // Images.
  const depth = readPng(result.depth_png_base64);
  // Segmentation.
  const segmentation = readPng(result.segmentation_png_base64);
  // Diffusion image. Null is allowed.
  const image = readPng(result.image_png_base64);
  // SSIM.
  const ssim = result.unchanged_ssim === null ? null : readNumber(result.unchanged_ssim);
  // Peak.
  const peak = result.peak_vram_mib === null ? null : readNumber(result.peak_vram_mib);
  // Plausible.
  const plausible =
    result.critic_plausible === null ? null : typeof result.critic_plausible === "boolean" ? result.critic_plausible : undefined;
  // Required fields.
  if (
    designId === null ||
    imageStatus === null ||
    consistency === null ||
    critic === null ||
    imageNote === null ||
    consistencyNote === null ||
    criticNote === null ||
    attempts === null ||
    !unchanged ||
    depth === undefined ||
    depth === null ||
    segmentation === undefined ||
    segmentation === null ||
    image === undefined ||
    ssim === undefined ||
    peak === undefined ||
    plausible === undefined ||
    !Array.isArray(result.placements) ||
    !Array.isArray(result.critic_issues) ||
    !Array.isArray(result.deterministic_violations) ||
    !Array.isArray(result.disagreements)
  ) {
    // Unreadable.
    return { kind: "failure", failure: { statusCode: httpStatus, detail: "The visualize response could not be read." } };
  }
  // Placements.
  const placements: MeshPlacement[] = [];
  // One row.
  for (const row of result.placements) {
    // Parse.
    const placement = readPlacement(row);
    // A bad row rejects the body.
    if (placement === null) {
      // Unreadable.
      return { kind: "failure", failure: { statusCode: httpStatus, detail: "The visualize response could not be read." } };
    }
    // Keep it.
    placements.push(placement);
  }
  // String lists.
  const issues = result.critic_issues.every((item) => typeof item === "string") ? result.critic_issues : null;
  // Checker lines.
  const violations = result.deterministic_violations.every((item) => typeof item === "string")
    ? result.deterministic_violations
    : null;
  // Disagreement lines.
  const disagreements = result.disagreements.every((item) => typeof item === "string") ? result.disagreements : null;
  // A non-string in a list rejects the body.
  if (issues === null || violations === null || disagreements === null) {
    // Unreadable.
    return { kind: "failure", failure: { statusCode: httpStatus, detail: "The visualize response could not be read." } };
  }
  // Body the panel can draw.
  return {
    kind: "ok",
    value: {
      design_id: designId,
      design_unchanged: true,
      placements,
      image_status: imageStatus,
      image_note: imageNote,
      image_png_base64: image,
      depth_png_base64: depth,
      segmentation_png_base64: segmentation,
      unchanged_ssim: ssim,
      consistency_status: consistency,
      consistency_note: consistencyNote,
      consistency_attempts: attempts,
      critic_status: critic,
      critic_note: criticNote,
      critic_plausible: plausible,
      critic_issues: issues,
      deterministic_violations: violations,
      disagreements,
      peak_vram_mib: peak,
    },
  };
}
