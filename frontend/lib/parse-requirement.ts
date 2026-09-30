// Read the requirements proxy. A bad body does not fill the form.

// Closed lists used to reject a requirement this page cannot edit.
import { MUST_HAVE_CLASSES, STYLES, WEIGHT_NAMES } from "@/lib/constants";

// Wire shapes.
import type { FailureView, ParseSuccess, Requirement, RetrievedNumber, SolverConstant } from "@/lib/types";

// A parsed requirements call.
export type RequirementRead =
  // The form may copy these fields.
  | { kind: "ok"; result: ParseSuccess }
  // HTTP or proxy failure. The form must not copy fields.
  | { kind: "failure"; failure: FailureView }
  // A 200 body this page does not understand. The form must not copy fields.
  | { kind: "bad"; detail: string };

// True for a plain object.
function isRecord(value: unknown): value is Record<string, unknown> {
  // Arrays are objects in JavaScript. Reject them.
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// A finite number.
function readNumber(value: unknown): number | null {
  // Reject non-numbers and infinities.
  if (typeof value !== "number" || !Number.isFinite(value)) {
    // Not usable.
    return null;
  }
  // Return it.
  return value;
}

// A string that may be empty. raw_text is allowed to be empty only before this route.
function readString(value: unknown): string | null {
  // Only strings.
  if (typeof value !== "string") {
    // Reject.
    return null;
  }
  // Keep the text.
  return value;
}

// A non-empty string.
function readRequired(value: unknown): string | null {
  // Read the string first.
  const text = readString(value);
  // Empty is not an id or a style.
  if (text === null || text.trim() === "") {
    // Reject.
    return null;
  }
  // Return it.
  return text;
}

// Read the proxy failure envelope.
function readFailure(body: unknown, httpStatus: number): FailureView {
  // Our routes send detail.
  if (isRecord(body) && typeof body.detail === "string" && body.detail.trim() !== "") {
    // Prefer the envelope status when it is a number or null.
    const statusCode =
      typeof body.statusCode === "number" || body.statusCode === null ? body.statusCode : httpStatus;
    // Panel contents.
    return { statusCode, detail: body.detail };
  }
  // No usable detail.
  return { statusCode: httpStatus, detail: `HTTP ${httpStatus}` };
}

// True when every weight is a finite number in [0, 1].
function readWeights(value: unknown): Requirement["objective_weights"] | null {
  // The weights are one object.
  if (!isRecord(value)) {
    // Reject.
    return null;
  }
  // Built object.
  const weights = {} as Requirement["objective_weights"];
  // Every name is required.
  for (const name of WEIGHT_NAMES) {
    // This weight.
    const parsed = readNumber(value[name]);
    // Range check.
    if (parsed === null || parsed < 0 || parsed > 1) {
      // Reject the whole object.
      return null;
    }
    // Store it.
    weights[name] = parsed;
  }
  // Complete.
  return weights;
}

// A string list whose entries are non-empty.
function readStringList(value: unknown): string[] | null {
  // Only arrays.
  if (!Array.isArray(value)) {
    // Reject.
    return null;
  }
  // Entries.
  const items: string[] = [];
  // Each entry.
  for (const item of value) {
    // Non-empty string.
    const text = readRequired(item);
    // A blank entry is invalid.
    if (text === null) {
      // Reject.
      return null;
    }
    // Keep it.
    items.push(text);
  }
  // Done.
  return items;
}

// Read a Requirement. Extra keys are ignored by the form, but the required keys must be present.
function readRequirement(value: unknown): Requirement | null {
  // Object.
  if (!isRecord(value)) {
    // Reject.
    return null;
  }
  // Ids and the sentence.
  const requirementId = readRequired(value.requirement_id);
  // Scene id.
  const sceneId = readRequired(value.scene_id);
  // The sentence may contain spaces. It must be a string.
  const rawText = readString(value.raw_text);
  // Budget.
  const budget = readNumber(value.budget_inr);
  // Classes.
  const mustHave = readStringList(value.must_have);
  // Keep ids.
  const mustKeep = readStringList(value.must_keep_object_ids);
  // People.
  const occupants = readNumber(value.occupant_count);
  // Style.
  const style = readRequired(value.style);
  // Flag.
  const accessibility = value.accessibility_required;
  // Weights.
  const weights = readWeights(value.objective_weights);
  // Required pieces.
  if (
    requirementId === null ||
    sceneId === null ||
    rawText === null ||
    budget === null ||
    budget < 0 ||
    mustHave === null ||
    mustKeep === null ||
    occupants === null ||
    !Number.isInteger(occupants) ||
    occupants < 1 ||
    style === null ||
    typeof accessibility !== "boolean" ||
    weights === null
  ) {
    // Not a requirement this form can edit.
    return null;
  }
  // Classes must be catalog choices. Rug, door, and window are rejected.
  if (mustHave.some((name) => !MUST_HAVE_CLASSES.includes(name as (typeof MUST_HAVE_CLASSES)[number]))) {
    // Do not fill the checkboxes from an illegal class.
    return null;
  }
  // Style must be a generator word.
  if (!STYLES.includes(style as (typeof STYLES)[number])) {
    // Do not fill the select from an unknown style.
    return null;
  }
  // Usable requirement.
  return {
    requirement_id: requirementId,
    scene_id: sceneId,
    raw_text: rawText,
    budget_inr: budget,
    must_have: mustHave,
    must_keep_object_ids: mustKeep,
    occupant_count: occupants,
    style,
    accessibility_required: accessibility,
    objective_weights: weights,
  };
}

// One retrieved number. Text is not read, even if a future body adds it.
function readRetrieved(value: unknown): RetrievedNumber | null {
  // Object.
  if (!isRecord(value)) {
    // Reject.
    return null;
  }
  // Name.
  const name = readRequired(value.name);
  // Metres.
  const metres = readNumber(value.value_m);
  // Source.
  const source = readRequired(value.source);
  // Topic.
  const topic = readRequired(value.topic);
  // Chunk id.
  const chunkId = readRequired(value.chunk_id);
  // Page is a number or null.
  const page =
    value.page === null ? null : readNumber(value.page) !== null ? readNumber(value.page) : undefined;
  // Required pieces, and a page that is either null or a number.
  if (name === null || metres === null || source === null || topic === null || chunkId === null || page === undefined) {
    // Skip a malformed row by rejecting the whole list later.
    return null;
  }
  // Structured number. No passage.
  return { name, value_m: metres, source, page, topic, chunk_id: chunkId };
}

// One solver constant.
function readConstant(value: unknown): SolverConstant | null {
  // Object.
  if (!isRecord(value)) {
    // Reject.
    return null;
  }
  // Name.
  const name = readRequired(value.name);
  // Metres.
  const metres = readNumber(value.value_m);
  // Both are required.
  if (name === null || metres === null) {
    // Reject.
    return null;
  }
  // Copy.
  return { name, value_m: metres };
}

// Read the success body inside { ok: true, result }.
function readSuccess(body: unknown): ParseSuccess | null {
  // Envelope.
  if (!isRecord(body) || body.ok !== true) {
    // Not the success shape.
    return null;
  }
  // Result object.
  if (!isRecord(body.result)) {
    // Reject.
    return null;
  }
  // Requirement.
  const requirement = readRequirement(body.result.requirement);
  // Note.
  const note = readString(body.result.retrieval_note);
  // Attempts.
  const attempts = readNumber(body.result.attempts);
  // Lists.
  if (!Array.isArray(body.result.retrieved) || !Array.isArray(body.result.solver_constants_m)) {
    // Reject.
    return null;
  }
  // Numbers.
  const retrieved: RetrievedNumber[] = [];
  // Each row.
  for (const item of body.result.retrieved) {
    // Parse one.
    const number = readRetrieved(item);
    // A bad row rejects the body so the form does not fill from a partial parse.
    if (number === null) {
      // Reject.
      return null;
    }
    // Keep it.
    retrieved.push(number);
  }
  // Constants.
  const constants: SolverConstant[] = [];
  // Each constant.
  for (const item of body.result.solver_constants_m) {
    // Parse one.
    const constant = readConstant(item);
    // A bad row rejects the body.
    if (constant === null) {
      // Reject.
      return null;
    }
    // Keep it.
    constants.push(constant);
  }
  // Required pieces.
  if (requirement === null || note === null || attempts === null || !Number.isInteger(attempts) || attempts < 1) {
    // Reject.
    return null;
  }
  // Success.
  return {
    requirement,
    retrieved,
    solver_constants_m: constants,
    retrieval_note: note,
    attempts,
  };
}

// Public reader used by the sentence button.
export function parseRequirementPayload(body: unknown, httpStatus: number): RequirementRead {
  // Non-200 is a parser error or a proxy error. Do not treat it as a filled form.
  if (httpStatus !== 200) {
    // Failure panel inside the form.
    return { kind: "failure", failure: readFailure(body, httpStatus) };
  }
  // 200 must be the success envelope.
  const result = readSuccess(body);
  // A 200 body we cannot edit from.
  if (result === null) {
    // The form shows this and does not copy fields.
    return { kind: "bad", detail: "The parser response was not a requirement this form can edit." };
  }
  // Fill from this.
  return { kind: "ok", result };
}
