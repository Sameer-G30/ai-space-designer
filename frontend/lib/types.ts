// Shapes the form edits and the shapes the API returns. Field names stay snake_case.

// One objective weight name.
import type { WEIGHT_NAMES } from "@/lib/constants";

// The six weight names.
export type WeightName = (typeof WEIGHT_NAMES)[number];

// Confidence stored on a room and on an object.
export type ConfidenceName = "low" | "medium" | "high";

// One opening while the user is still typing.
export type OpeningDraft = {
  // React key. Not sent to the API.
  key: string;
  // Door or window.
  type: "door" | "window";
  // Wall that holds the opening.
  wall: "north" | "south" | "east" | "west";
  // Metres from the start of the wall, as typed text.
  position: string;
  // Opening width in metres, as typed text.
  width: string;
};

// One existing object while the user is still typing.
export type ObjectDraft = {
  // React key. Not sent to the API.
  key: string;
  // Scene object id.
  id: string;
  // Taxonomy class.
  type: string;
  // Footprint centre x, as typed text.
  x: string;
  // Footprint centre y, as typed text.
  y: string;
  // Rotation in degrees, as typed text.
  rotation: string;
  // Local length in metres, as typed text.
  length: string;
  // Local width in metres, as typed text.
  width: string;
  // Height in metres, as typed text.
  height: string;
  // True when the solver must keep this pose.
  mustKeep: boolean;
};

// The whole form, before numbers are parsed.
export type RequestDraft = {
  // Scene id typed by the user.
  sceneId: string;
  // Room type token.
  roomType: string;
  // Room length text.
  length: string;
  // Room width text.
  width: string;
  // Room height text.
  height: string;
  // Room confidence token.
  confidence: string;
  // Scene version to send. A corrected photo estimate is saved as the next version.
  sceneVersion?: number;
  // Opening rows.
  openings: OpeningDraft[];
  // Existing object rows.
  objects: ObjectDraft[];
  // Budget text, in INR.
  budget: string;
  // Checked catalog classes. Order is ignored; the builder uses taxonomy order.
  mustHave: string[];
  // Occupant count text.
  occupants: string;
  // Style token.
  style: string;
  // Whether the turning-space constraint is on.
  accessibility: boolean;
  // The six weights as typed text.
  weights: Record<WeightName, string>;
  // Sentence box. Sent as raw_text. It does not by itself change the structured fields.
  rawText: string;
};

// The six weights after they have been parsed.
export type ObjectiveWeights = Record<WeightName, number>;

// One opening on the wire.
export type SceneOpening = {
  // Door or window.
  type: string;
  // Wall name.
  wall: string;
  // Metres from the start of that wall.
  position: number;
  // Opening width in metres.
  width: number;
};

// One scene object on the wire and in a design.
export type SceneObject = {
  // Stable id.
  id: string;
  // Taxonomy class.
  type: string;
  // Footprint centre [x, y] in metres.
  position: [number, number];
  // Rotation in degrees.
  rotation: number;
  // Local [length, width, height] in metres.
  dimensions: [number, number, number];
  // True when the object may be moved. Kept objects are sent as false.
  movable: boolean;
  // True when this pose is fixed.
  must_keep: boolean;
  // Confidence for this object.
  confidence: ConfidenceName;
};

// A scene graph posted to /scenes.
export type SceneGraph = {
  // Scene id.
  scene_id: string;
  // Version. This form always sends 1.
  version: number;
  // Room type token.
  room_type: string;
  // Room size and confidence.
  dimensions: {
    // Length along x, in metres.
    length: number;
    // Width along y, in metres.
    width: number;
    // Floor-to-ceiling height, in metres.
    height: number;
    // Confidence for the three edges together.
    confidence: ConfidenceName;
  };
  // Doors and windows.
  openings: SceneOpening[];
  // Existing objects.
  objects: SceneObject[];
};

// A structured requirement posted inside /designs/optimize.
export type Requirement = {
  // Derived from the scene id.
  requirement_id: string;
  // Must equal the scene id.
  scene_id: string;
  // The sentence the user typed. Empty when the sentence box is empty.
  raw_text: string;
  // Budget ceiling in INR.
  budget_inr: number;
  // Catalog classes that must be present.
  must_have: string[];
  // Ids of objects marked keep.
  must_keep_object_ids: string[];
  // People the room must hold.
  occupant_count: number;
  // Style token.
  style: string;
  // Turning-space constraint.
  accessibility_required: boolean;
  // All six weights, each in [0, 1].
  objective_weights: ObjectiveWeights;
};

// A validated scene plus requirement ready to post.
export type BuiltRequest = {
  // Body for POST /scenes.
  scene: SceneGraph;
  // Requirement nested in POST /designs/optimize.
  requirement: Requirement;
};

// One bill-of-material line. item_id comes from this line, not from the object id.
export type BomLine = {
  // Catalog id.
  item_id: string;
  // Taxonomy class.
  category: string;
  // Unit count.
  qty: number;
  // Price of one unit, synthetic INR.
  unit_price: number;
  // qty times unit_price.
  line_total: number;
};

// One binding constraint on a trace.
export type BindingConstraint = {
  // Short name.
  name: string;
  // Recorded fact.
  detail: string;
};

// Trace stored beside a design, never inside it.
export type OptimizerTrace = {
  // Design this trace belongs to.
  design_id: string;
  // Constraints that held with equality.
  binding_constraints: BindingConstraint[];
  // Counted in the UI. The full list is not printed.
  rejected_items: { item_id: string; reason: string }[];
  // The six terms, each in [0, 1].
  objective_terms: ObjectiveWeights;
};

// One design inside a Pareto point.
export type Design = {
  // Design id.
  design_id: string;
  // Scene id.
  scene_id: string;
  // Requirement id.
  requirement_id: string;
  // Weights used for this point.
  weights: ObjectiveWeights;
  // Combined score.
  score: number;
  // Total cost in INR. The BOM total matches this.
  cost: number;
  // Placed objects, including kept ones.
  objects: SceneObject[];
  // Earlier design, when the API sends one.
  parent_design_id: string | null;
};

// One labelled Pareto point.
export type ParetoPoint = {
  // One or more labels. A point may carry several.
  labels: string[];
  // The design.
  design: Design;
  // The trace beside the design.
  trace: OptimizerTrace;
  // Purchased lines.
  bom: BomLine[];
  // Time spent placing this point, in milliseconds.
  solve_time_ms: number;
};

// A feasible optimize body.
export type ParetoBody = {
  // Discriminator.
  feasible: true;
  // One to eight points. Fewer than four is valid.
  points: ParetoPoint[];
  // Selections that were placed.
  candidates_evaluated: number;
  // Placed selections that lost the dominance filter.
  dominated_removed: number;
  // CLIP checkpoint name, or tag_overlap_fallback.
  style_backend: string;
  // Time for the whole sweep, in milliseconds.
  solve_time_ms: number;
};

// An infeasible optimize body. It has no design.
export type InfeasibleBody = {
  // Discriminator.
  feasible: false;
  // Solver reason.
  reason: string;
  // Time spent before giving up, in milliseconds.
  solve_time_ms: number;
};

// GET /health as shown on the page.
export type HealthView = {
  // HTTP status, or null when the process could not be reached.
  statusCode: number | null;
  // Status word from the API, or unreachable.
  status: string;
  // Failure text. Empty when the check succeeded.
  detail: string;
};

// One retrieved clearance or ergonomic number. The chunk text is not included.
export type RetrievedNumber = {
  // Short name such as door_clear_width.
  name: string;
  // Metres.
  value_m: number;
  // Document id.
  source: string;
  // PDF page, or null for a project summary.
  page: number | null;
  // Chunk topic.
  topic: string;
  // Chunk id. The page does not have to show it.
  chunk_id: string;
};

// One named solver constant copied into the parse response.
export type SolverConstant = {
  // Constant name.
  name: string;
  // Value in metres. The parser does not change it.
  value_m: number;
};

// A successful POST /requirements body.
export type ParseSuccess = {
  // Validated requirement.
  requirement: Requirement;
  // Retrieved numbers. May be empty.
  retrieved: RetrievedNumber[];
  // The five named constants, unchanged.
  solver_constants_m: SolverConstant[];
  // ok, or why retrieved is empty.
  retrieval_note: string;
  // Model attempts used.
  attempts: number;
};

// A failed proxy call shown in the error panel.
export type FailureView = {
  // HTTP status, or null when the browser could not reach this Next.js app.
  statusCode: number | null;
  // Readable detail. FastAPI validation text is kept. Unexpected bodies are not.
  detail: string;
};

// Confidence label on one dimension of a photo estimate.
export type PhotoConfidence = {
  // Length confidence.
  length: ConfidenceName;
  // Width confidence.
  width: ConfidenceName;
  // Height confidence.
  height: ConfidenceName;
};

// A photo estimate the form accepted from POST /api/scenes/photo.
export type PhotoResult = {
  // Scene the API stored, already validated by the API.
  scene: SceneGraph;
  // Confidence on every dimension.
  dimensionConfidence: PhotoConfidence;
  // "user_length" or "metric_depth".
  scaleSource: string;
  // Factor applied to the metric depth estimate.
  scaleFactor: number;
  // Best room type guesses.
  roomGuesses: { roomType: string; probability: number }[];
  // Detected classes with scores.
  detections: string[];
  // Faces blurred before any model ran.
  facesBlurred: number;
  // Plain-language notes.
  warnings: string[];
};

// One templated fact. The ref is the source shown beside the sentence.
export type TemplatedFact = {
  // Trace or design field, such as design.cost.
  ref: string;
  // Sentence the checker allows the model to rephrase.
  text: string;
};

// One stored explanation claim.
export type ExplanationClaim = {
  // Row id.
  explanation_id: string;
  // Sentence.
  claim_text: string;
  // Source pointer, or the closest fact when the claim failed the check.
  supporting_trace_ref: string;
  // True when every number and domain word is in the facts.
  verified: boolean;
};

// GET /designs/{id}/explanation.
export type ExplanationBody = {
  // Design that was explained.
  design_id: string;
  // Sources.
  facts: TemplatedFact[];
  // Stored claims.
  claims: ExplanationClaim[];
  // Fraction of claims that verified.
  verified_rate: number;
  // True when a model wrote the claims.
  rephrased: boolean;
  // Why the model did or did not rephrase.
  rephrase_note: string;
};

// One object that kept its id and changed pose.
export type MovedItem = {
  // Object id.
  id: string;
  // Category.
  type: string;
  // Previous centre.
  from_position: [number, number];
  // New centre.
  to_position: [number, number];
  // Previous rotation in degrees.
  from_rotation: number;
  // New rotation in degrees.
  to_rotation: number;
};

// Diff stored on a design version and returned by a what-if.
export type VersionDiff = {
  // Object ids present only in the later design.
  items_added: string[];
  // Object ids present only in the earlier design.
  items_removed: string[];
  // Objects that kept their id and changed pose.
  items_moved: MovedItem[];
  // Later cost minus earlier cost.
  cost_change: number;
  // Later score minus earlier score.
  score_change: number;
};

// One append-only version row.
export type DesignVersionRow = {
  // Design this row belongs to.
  design_id: string;
  // Scene this row belongs to.
  scene_id: string;
  // Version number, starting at 1.
  version: number;
  // Previous version of the same design, or null for version 1.
  parent_version: number | null;
  // Diff payload.
  diff: VersionDiff;
  // Score stored with this version.
  score: number;
  // ISO timestamp.
  timestamp: string;
};

// GET /designs/{id}/versions.
export type VersionsBody = {
  // Design the rows belong to.
  design_id: string;
  // Ordered versions.
  versions: DesignVersionRow[];
};

// A feasible what-if.
export type CounterfactualDesign = {
  // Discriminator.
  feasible: true;
  // New design.
  design: Design;
  // Trace of the warm-started solve.
  trace: OptimizerTrace;
  // Bill of materials.
  bom: BomLine[];
  // Scene the new design was solved against.
  scene: SceneGraph;
  // Design the what-if started from.
  parent_design_id: string;
  // CP-SAT time in milliseconds.
  solve_time_ms: number;
  // New score minus the parent score.
  score_change: number;
  // New cost minus the parent cost.
  cost_change: number;
  // New budget minus the parent budget.
  budget_change_inr: number;
  // score_change / budget_change_inr, or null when the budget did not change.
  sensitivity_score_per_inr: number | null;
  // How many previous poses were passed as hints.
  hint_count: number;
  // True when at least one hint was passed.
  warm_started: boolean;
  // The diff stored on the version row.
  diff: VersionDiff;
};

// An infeasible what-if. No design is drawn.
export type CounterfactualRejected = {
  // Discriminator.
  feasible: false;
  // Solver or selection reason.
  reason: string;
  // Design the what-if started from.
  parent_design_id: string;
  // Time spent, in milliseconds.
  solve_time_ms: number;
  // True when hints were passed.
  warm_started: boolean;
  // Hints passed.
  hint_count: number;
};
