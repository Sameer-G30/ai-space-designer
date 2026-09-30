// Reader for the POST /api/scenes/photo reply. A reply that does not match is not applied.

// Result types.
import type { ConfidenceName, PhotoResult, SceneGraph } from "@/lib/types";

// A plain object check.
function isRecord(value: unknown): value is Record<string, unknown> {
  // Arrays and null are not records.
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// One confidence token.
function conf(value: unknown): ConfidenceName | null {
  // Only the three locked tokens.
  return value === "low" || value === "medium" || value === "high" ? value : null;
}

// What the reader returns.
export type PhotoRead =
  // A reply the form can apply.
  | { kind: "ok"; result: PhotoResult }
  // An API or network failure with its text.
  | { kind: "failure"; detail: string };

// Read the route body.
export function parsePhotoPayload(body: unknown, status: number): PhotoRead {
  // Error envelope from the route.
  if (isRecord(body) && body.ok === false) {
    // Show the API sentence.
    return { kind: "failure", detail: String(body.detail ?? `HTTP ${status}`) };
  }
  // Anything other than a wrapped estimate.
  if (!isRecord(body) || body.ok !== true || !isRecord(body.photo)) {
    // Do not apply it.
    return { kind: "failure", detail: `The photo reply was not readable (HTTP ${status}).` };
  }
  // The estimate.
  const photo = body.photo;
  // Scene, checked only for what the form copies.
  const scene = photo.scene as SceneGraph | undefined;
  // Per-dimension confidence.
  const dims = photo.dimension_confidence;
  // A malformed estimate is refused.
  if (
    !isRecord(scene) ||
    !isRecord(scene.dimensions) ||
    !Array.isArray(scene.openings) ||
    !Array.isArray(scene.objects) ||
    typeof scene.version !== "number" ||
    !isRecord(dims) ||
    conf(dims.length) === null ||
    conf(dims.width) === null ||
    conf(dims.height) === null
  ) {
    // Do not apply it.
    return { kind: "failure", detail: "The photo estimate had an unexpected shape." };
  }
  // Room guesses, tolerating a missing list.
  const guesses = Array.isArray(photo.room_guesses) ? photo.room_guesses : [];
  // Build the typed result.
  return {
    kind: "ok",
    result: {
      scene,
      dimensionConfidence: {
        length: dims.length as ConfidenceName,
        width: dims.width as ConfidenceName,
        height: dims.height as ConfidenceName,
      },
      scaleSource: String(photo.scale_source ?? ""),
      scaleFactor: Number(photo.scale_factor ?? 1),
      roomGuesses: guesses
        .filter(isRecord)
        .map((g) => ({ roomType: String(g.room_type), probability: Number(g.probability) })),
      detections: Array.isArray(photo.detections) ? photo.detections.map(String) : [],
      facesBlurred: Number(photo.faces_blurred ?? 0),
      warnings: Array.isArray(photo.warnings) ? photo.warnings.map(String) : [],
    },
  };
}
