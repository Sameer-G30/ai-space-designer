// Read Phase 8 proxy JSON. A bad body is not drawn.

// Failure shape shared with the rest of the page.
import type { FailureView } from "@/lib/types";

// Phase 8 shapes.
import type {
  BomLine,
  CounterfactualDesign,
  CounterfactualRejected,
  DesignVersionRow,
  ExplanationBody,
  ExplanationClaim,
  MovedItem,
  TemplatedFact,
  VersionDiff,
  VersionsBody,
} from "@/lib/types";

// Readers already used for a Pareto point.
import { readBomLine, readDesign, readScene, readTrace } from "@/lib/parse-result";

// A parsed Phase 8 call.
export type Phase8Read<T> =
  // The value.
  | { kind: "ok"; value: T }
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

// A non-empty string.
function readText(value: unknown): string | null {
  // Empty strings are not ids or sentences.
  if (typeof value !== "string" || value.trim() === "") {
    // Reject.
    return null;
  }
  // Keep the string.
  return value;
}

// Proxy failure, or a generic HTTP line.
function readFailure(body: unknown, httpStatus: number): FailureView {
  // Our routes send ok:false plus detail.
  if (isRecord(body) && typeof body.detail === "string" && body.detail.trim() !== "") {
    // Prefer the status stored in the envelope.
    const statusCode =
      typeof body.statusCode === "number" || body.statusCode === null ? body.statusCode : httpStatus;
    // Panel contents.
    return { statusCode, detail: body.detail };
  }
  // No usable envelope.
  return { statusCode: httpStatus, detail: `HTTP ${httpStatus}` };
}

// The result object inside a successful proxy envelope.
function readResult(body: unknown, httpStatus: number): { ok: true; result: unknown } | { ok: false; failure: FailureView } {
  // HTTP errors.
  if (httpStatus < 200 || httpStatus >= 300) {
    // Failure.
    return { ok: false, failure: readFailure(body, httpStatus) };
  }
  // The envelope.
  if (!isRecord(body) || body.ok !== true || !("result" in body)) {
    // A 200 body this page cannot read.
    return { ok: false, failure: { statusCode: httpStatus, detail: "The explanation response was not readable." } };
  }
  // The FastAPI body.
  return { ok: true, result: body.result };
}

// One fact.
function readFact(value: unknown): TemplatedFact | null {
  // Object.
  if (!isRecord(value)) {
    // Reject.
    return null;
  }
  // Ref and sentence.
  const ref = readText(value.ref);
  const text = readText(value.text);
  // Both required.
  if (ref === null || text === null) {
    // Reject.
    return null;
  }
  // Fact.
  return { ref, text };
}

// One claim.
function readClaim(value: unknown): ExplanationClaim | null {
  // Object.
  if (!isRecord(value)) {
    // Reject.
    return null;
  }
  // Fields.
  const explanationId = readText(value.explanation_id);
  const claimText = readText(value.claim_text);
  const ref = readText(value.supporting_trace_ref);
  // verified is a boolean.
  if (explanationId === null || claimText === null || ref === null || typeof value.verified !== "boolean") {
    // Reject.
    return null;
  }
  // Claim.
  return {
    explanation_id: explanationId,
    claim_text: claimText,
    supporting_trace_ref: ref,
    verified: value.verified,
  };
}

// Read an explanation body.
export function parseExplanation(body: unknown, httpStatus: number): Phase8Read<ExplanationBody> {
  // Envelope.
  const envelope = readResult(body, httpStatus);
  // Failure.
  if (!envelope.ok) {
    // Pass it on.
    return { kind: "failure", failure: envelope.failure };
  }
  // FastAPI object.
  const value = envelope.result;
  // Object.
  if (!isRecord(value) || !Array.isArray(value.facts) || !Array.isArray(value.claims)) {
    // Unreadable.
    return { kind: "failure", failure: { statusCode: httpStatus, detail: "The explanation response was not readable." } };
  }
  // Design id and note.
  const designId = readText(value.design_id);
  const note = typeof value.rephrase_note === "string" ? value.rephrase_note : null;
  const rate = readNumber(value.verified_rate);
  // Flags and lists.
  if (designId === null || note === null || rate === null || typeof value.rephrased !== "boolean") {
    // Unreadable.
    return { kind: "failure", failure: { statusCode: httpStatus, detail: "The explanation response was not readable." } };
  }
  // Facts.
  const facts = value.facts.map(readFact);
  // Claims.
  const claims = value.claims.map(readClaim);
  // A null entry rejects the whole body.
  if (facts.some((fact) => fact === null) || claims.some((claim) => claim === null)) {
    // Unreadable.
    return { kind: "failure", failure: { statusCode: httpStatus, detail: "The explanation response was not readable." } };
  }
  // Body.
  return {
    kind: "ok",
    value: {
      design_id: designId,
      facts: facts as TemplatedFact[],
      claims: claims as ExplanationClaim[],
      verified_rate: rate,
      rephrased: value.rephrased,
      rephrase_note: note,
    },
  };
}

// A list of non-empty strings.
function readStringList(value: unknown): string[] | null {
  // Array.
  if (!Array.isArray(value)) {
    // Reject.
    return null;
  }
  // Every entry is a non-empty string.
  if (!value.every((item) => typeof item === "string" && item !== "")) {
    // Reject.
    return null;
  }
  // Copy.
  return value;
}

// One moved object.
function readMoved(value: unknown): MovedItem | null {
  // Object.
  if (!isRecord(value)) {
    // Reject.
    return null;
  }
  // Id and type.
  const id = readText(value.id);
  const type = readText(value.type);
  // Centres.
  const fromPosition = readPair(value.from_position);
  const toPosition = readPair(value.to_position);
  // Rotations.
  const fromRotation = readNumber(value.from_rotation);
  const toRotation = readNumber(value.to_rotation);
  // All required.
  if (id === null || type === null || fromPosition === null || toPosition === null) {
    // Reject.
    return null;
  }
  // Rotations too.
  if (fromRotation === null || toRotation === null) {
    // Reject.
    return null;
  }
  // Entry.
  return {
    id,
    type,
    from_position: fromPosition,
    to_position: toPosition,
    from_rotation: fromRotation,
    to_rotation: toRotation,
  };
}

// A centre pair.
function readPair(value: unknown): [number, number] | null {
  // Two numbers.
  if (!Array.isArray(value) || value.length !== 2) {
    // Reject.
    return null;
  }
  // X and y.
  const x = readNumber(value[0]);
  const y = readNumber(value[1]);
  // Both finite.
  if (x === null || y === null) {
    // Reject.
    return null;
  }
  // Pair.
  return [x, y];
}

// The five required diff keys. Extra keys are ignored.
function readDiff(value: unknown): VersionDiff | null {
  // Object.
  if (!isRecord(value)) {
    // Reject.
    return null;
  }
  // Lists.
  const added = readStringList(value.items_added);
  const removed = readStringList(value.items_removed);
  // Moved objects.
  if (!Array.isArray(value.items_moved) || added === null || removed === null) {
    // Reject.
    return null;
  }
  // Each move.
  const moved = value.items_moved.map(readMoved);
  // A bad move rejects the diff.
  if (moved.some((item) => item === null)) {
    // Reject.
    return null;
  }
  // Deltas.
  const costChange = readNumber(value.cost_change);
  const scoreChange = readNumber(value.score_change);
  // Both required.
  if (costChange === null || scoreChange === null) {
    // Reject.
    return null;
  }
  // Diff.
  return {
    items_added: added,
    items_removed: removed,
    items_moved: moved as MovedItem[],
    cost_change: costChange,
    score_change: scoreChange,
  };
}

// One version row.
function readVersion(value: unknown): DesignVersionRow | null {
  // Object.
  if (!isRecord(value)) {
    // Reject.
    return null;
  }
  // Ids.
  const designId = readText(value.design_id);
  const sceneId = readText(value.scene_id);
  const timestamp = readText(value.timestamp);
  // Version number.
  const version = readNumber(value.version);
  // Score.
  const score = readNumber(value.score);
  // Diff.
  const diff = readDiff(value.diff);
  // Parent version is null or a positive integer.
  const parent = value.parent_version;
  const parentOk = parent === null || (typeof parent === "number" && Number.isInteger(parent) && parent >= 1);
  // Required fields.
  if (designId === null || sceneId === null || timestamp === null || version === null || score === null) {
    // Reject.
    return null;
  }
  // Version is a positive integer, and the diff parsed.
  if (!Number.isInteger(version) || version < 1 || diff === null || !parentOk) {
    // Reject.
    return null;
  }
  // Row.
  return {
    design_id: designId,
    scene_id: sceneId,
    version,
    parent_version: parent === null ? null : parent,
    diff,
    score,
    timestamp,
  };
}

// Read the version list.
export function parseVersions(body: unknown, httpStatus: number): Phase8Read<VersionsBody> {
  // Envelope.
  const envelope = readResult(body, httpStatus);
  // Failure.
  if (!envelope.ok) {
    // Pass it on.
    return { kind: "failure", failure: envelope.failure };
  }
  // Object.
  const value = envelope.result;
  // Shape.
  if (!isRecord(value) || !Array.isArray(value.versions)) {
    // Unreadable.
    return { kind: "failure", failure: { statusCode: httpStatus, detail: "The version response was not readable." } };
  }
  // Design id.
  const designId = readText(value.design_id);
  // Rows.
  const versions = value.versions.map(readVersion);
  // A bad row rejects the list.
  if (designId === null || versions.some((row) => row === null)) {
    // Unreadable.
    return { kind: "failure", failure: { statusCode: httpStatus, detail: "The version response was not readable." } };
  }
  // Body.
  return { kind: "ok", value: { design_id: designId, versions: versions as DesignVersionRow[] } };
}

// Optional sensitivity. Null is allowed. A missing key is null.
function readSensitivity(value: unknown): number | null | undefined {
  // Absent or null means the budget did not change.
  if (value === null || value === undefined) {
    // No figure.
    return null;
  }
  // A finite number.
  return readNumber(value);
}

// Read a what-if body, feasible or not.
export function parseCounterfactual(
  body: unknown,
  httpStatus: number,
): Phase8Read<CounterfactualDesign | CounterfactualRejected> {
  // Envelope.
  const envelope = readResult(body, httpStatus);
  // Failure.
  if (!envelope.ok) {
    // Pass it on.
    return { kind: "failure", failure: envelope.failure };
  }
  // Object.
  const value = envelope.result;
  // Shape.
  if (!isRecord(value) || typeof value.feasible !== "boolean") {
    // Unreadable.
    return { kind: "failure", failure: { statusCode: httpStatus, detail: "The what-if response was not readable." } };
  }
  // Shared fields.
  const parentId = readText(value.parent_design_id);
  const solveTime = readNumber(value.solve_time_ms);
  const hintCount = readNumber(value.hint_count);
  // Required on both outcomes.
  if (parentId === null || solveTime === null || hintCount === null || typeof value.warm_started !== "boolean") {
    // Unreadable.
    return { kind: "failure", failure: { statusCode: httpStatus, detail: "The what-if response was not readable." } };
  }
  // Hint count is a non-negative integer.
  if (!Number.isInteger(hintCount) || hintCount < 0 || solveTime < 0) {
    // Unreadable.
    return { kind: "failure", failure: { statusCode: httpStatus, detail: "The what-if response was not readable." } };
  }
  // Infeasible branch.
  if (value.feasible === false) {
    // Reason.
    const reason = readText(value.reason);
    // Required.
    if (reason === null) {
      // Unreadable.
      return { kind: "failure", failure: { statusCode: httpStatus, detail: "The what-if response was not readable." } };
    }
    // Rejection.
    return {
      kind: "ok",
      value: {
        feasible: false,
        reason,
        parent_design_id: parentId,
        solve_time_ms: solveTime,
        warm_started: value.warm_started,
        hint_count: hintCount,
      },
    };
  }
  // Feasible pieces.
  const design = readDesign(value.design);
  const trace = readTrace(value.trace);
  const scene = readScene(value.scene);
  const diff = readDiff(value.diff);
  const scoreChange = readNumber(value.score_change);
  const costChange = readNumber(value.cost_change);
  const budgetChange = readNumber(value.budget_change_inr);
  const sensitivity = readSensitivity(value.sensitivity_score_per_inr);
  // Bill lines.
  if (!Array.isArray(value.bom) || design === null || trace === null || scene === null || diff === null) {
    // Unreadable.
    return { kind: "failure", failure: { statusCode: httpStatus, detail: "The what-if response was not readable." } };
  }
  // Deltas.
  if (scoreChange === null || costChange === null || budgetChange === null || sensitivity === undefined) {
    // Unreadable.
    return { kind: "failure", failure: { statusCode: httpStatus, detail: "The what-if response was not readable." } };
  }
  // Lines.
  const bom = value.bom.map(readBomLine);
  // A bad line rejects the body.
  if (bom.some((line) => line === null)) {
    // Unreadable.
    return { kind: "failure", failure: { statusCode: httpStatus, detail: "The what-if response was not readable." } };
  }
  // Feasible what-if.
  return {
    kind: "ok",
    value: {
      feasible: true,
      design,
      trace,
      bom: bom as BomLine[],
      scene,
      parent_design_id: parentId,
      solve_time_ms: solveTime,
      score_change: scoreChange,
      cost_change: costChange,
      budget_change_inr: budgetChange,
      sensitivity_score_per_inr: sensitivity,
      hint_count: hintCount,
      warm_started: value.warm_started,
      diff,
    },
  };
}
