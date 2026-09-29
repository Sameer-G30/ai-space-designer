// Turn the form into a SceneGraph and a Requirement. Extra keys are not sent.

// Closed lists and the requirement id helper.
import {
  CONFIDENCE_LEVELS,
  FURNITURE_CLASSES,
  MUST_HAVE_CLASSES,
  OPENING_TYPES,
  ROOM_TYPES,
  SCENE_VERSION,
  STYLES,
  WALLS,
  WEIGHT_NAMES,
  requirementIdFor,
} from "@/lib/constants";

// Draft and wire types.
import type {
  BuiltRequest,
  ConfidenceName,
  ObjectDraft,
  OpeningDraft,
  RequestDraft,
  SceneObject,
  SceneOpening,
} from "@/lib/types";

// Parse one typed number. Empty and non-finite text become null.
function readFinite(value: string): number | null {
  // Trim spaces before parsing.
  const trimmed = value.trim();
  // An empty field is missing.
  if (trimmed === "") {
    // Caller writes the field-specific message.
    return null;
  }
  // Number accepts the usual decimal form.
  const parsed = Number(trimmed);
  // Reject NaN and infinities.
  if (!Number.isFinite(parsed)) {
    // Caller writes the message.
    return null;
  }
  // Return the number.
  return parsed;
}

// True when the value is one of a readonly list.
function isListed(value: string, allowed: readonly string[]): boolean {
  // Include works on the widened list.
  return allowed.includes(value);
}

// Collect opening errors and the wire rows.
function readOpenings(
  drafts: OpeningDraft[],
  roomLength: number | null,
  roomWidth: number | null,
  errors: string[],
): SceneOpening[] {
  // Wire rows.
  const openings: SceneOpening[] = [];
  // Walk the rows in form order.
  drafts.forEach((draft, index) => {
    // Human row number.
    const row = index + 1;
    // Type must be door or window.
    if (!isListed(draft.type, OPENING_TYPES)) {
      // Record the error.
      errors.push(`Opening ${row} needs a type of door or window.`);
    }
    // Wall must be one of the four.
    if (!isListed(draft.wall, WALLS)) {
      // Record the error.
      errors.push(`Opening ${row} needs a wall of north, south, east, or west.`);
    }
    // Position.
    const position = readFinite(draft.position);
    // Width.
    const width = readFinite(draft.width);
    // Position is required.
    if (position === null) {
      // Record the error.
      errors.push(`Opening ${row} needs a position in metres.`);
    }
    // Width must be positive.
    if (width === null || width <= 0) {
      // Record the error.
      errors.push(`Opening ${row} needs a width greater than 0.`);
    }
    // Fit the opening on the wall once the room size and the numbers are valid.
    if (position !== null && width !== null && width > 0 && roomLength !== null && roomWidth !== null) {
      // North and south run along length. East and west run along width.
      const span = draft.wall === "east" || draft.wall === "west" ? roomWidth : roomLength;
      // The opening must start on the wall and end on the wall.
      if (position < 0 || position + width > span + 1e-9) {
        // Record the error.
        errors.push(`Opening ${row} does not lie on its wall.`);
      }
    }
    // Keep the row only when this opening is complete.
    if (
      isListed(draft.type, OPENING_TYPES) &&
      isListed(draft.wall, WALLS) &&
      position !== null &&
      width !== null &&
      width > 0
    ) {
      // Append the wire object. No extra keys.
      openings.push({
        // Type token.
        type: draft.type,
        // Wall token.
        wall: draft.wall,
        // Position in metres.
        position,
        // Width in metres.
        width,
      });
    }
  });
  // Return whatever was valid. The caller discards the list when errors is non-empty.
  return openings;
}

// Collect object errors and the wire rows. Duplicate ids are left for the API so it can return 422.
function readObjects(
  drafts: ObjectDraft[],
  confidence: ConfidenceName | null,
  errors: string[],
): SceneObject[] {
  // Wire rows.
  const objects: SceneObject[] = [];
  // Walk the rows in form order.
  drafts.forEach((draft, index) => {
    // Human row number.
    const row = index + 1;
    // Trim the id once.
    const id = draft.id.trim();
    // Id is required.
    if (id === "") {
      // Record the error.
      errors.push(`Enter an id for object ${row}.`);
    }
    // Type must be a taxonomy class.
    if (!isListed(draft.type, FURNITURE_CLASSES)) {
      // Record the error.
      errors.push(`Object ${row} needs a furniture class from the list.`);
    }
    // Centre and size.
    const x = readFinite(draft.x);
    // Centre y.
    const y = readFinite(draft.y);
    // Rotation.
    const rotation = readFinite(draft.rotation);
    // Local length.
    const length = readFinite(draft.length);
    // Local width.
    const width = readFinite(draft.width);
    // Height.
    const height = readFinite(draft.height);
    // Centre is required.
    if (x === null || y === null) {
      // Record the error.
      errors.push(`Object ${row} needs a centre x and y.`);
    }
    // Rotation is required. 180 and 270 are allowed.
    if (rotation === null) {
      // Record the error.
      errors.push(`Object ${row} needs a rotation in degrees.`);
    }
    // Every edge must be positive.
    if (length === null || width === null || height === null || length <= 0 || width <= 0 || height <= 0) {
      // Record the error.
      errors.push(`Object ${row} needs a positive length, width, and height.`);
    }
    // Append a complete row. Duplicate ids are intentionally still appended.
    if (
      id !== "" &&
      isListed(draft.type, FURNITURE_CLASSES) &&
      x !== null &&
      y !== null &&
      rotation !== null &&
      length !== null &&
      width !== null &&
      height !== null &&
      length > 0 &&
      width > 0 &&
      height > 0 &&
      confidence !== null
    ) {
      // Wire object. Kept objects are not movable.
      objects.push({
        // Trimmed id.
        id,
        // Class token.
        type: draft.type,
        // Footprint centre.
        position: [x, y],
        // Degrees.
        rotation,
        // Local size. Rotation is applied by the viewer, not by rewriting these edges.
        dimensions: [length, width, height],
        // A kept object stays fixed.
        movable: !draft.mustKeep,
        // The checkbox.
        must_keep: draft.mustKeep,
        // Objects use the room confidence. The form does not collect a second one.
        confidence,
      });
    }
  });
  // Return the rows.
  return objects;
}

// Validate the draft and build both request bodies.
export function buildRequest(draft: RequestDraft): { errors: string[]; value: BuiltRequest | null } {
  // Messages shown above the results. The request is not sent when this is non-empty.
  const errors: string[] = [];
  // Trim the scene id.
  const sceneId = draft.sceneId.trim();
  // Scene id is required.
  if (sceneId === "") {
    // Record the error.
    errors.push("Enter a scene id.");
  }
  // Room type must be one of the 15.
  if (!isListed(draft.roomType, ROOM_TYPES)) {
    // Record the error.
    errors.push("Choose a room type.");
  }
  // Room edges.
  const length = readFinite(draft.length);
  // Width.
  const width = readFinite(draft.width);
  // Height.
  const height = readFinite(draft.height);
  // Length must be positive.
  if (length === null || length <= 0) {
    // Record the error.
    errors.push("Room length must be greater than 0.");
  }
  // Width must be positive.
  if (width === null || width <= 0) {
    // Record the error.
    errors.push("Room width must be greater than 0.");
  }
  // Height must be positive.
  if (height === null || height <= 0) {
    // Record the error.
    errors.push("Room height must be greater than 0.");
  }
  // Confidence token.
  const confidence = isListed(draft.confidence, CONFIDENCE_LEVELS)
    ? (draft.confidence as ConfidenceName)
    : null;
  // Confidence is required.
  if (confidence === null) {
    // Record the error.
    errors.push("Choose a confidence of low, medium, or high.");
  }
  // Openings.
  const openings = readOpenings(
    draft.openings,
    length !== null && length > 0 ? length : null,
    width !== null && width > 0 ? width : null,
    errors,
  );
  // Objects.
  const objects = readObjects(draft.objects, confidence, errors);
  // Budget.
  const budget = readFinite(draft.budget);
  // Budget must be zero or positive.
  if (budget === null || budget < 0) {
    // Record the error.
    errors.push("Budget must be 0 or greater.");
  }
  // Occupants.
  const occupants = readFinite(draft.occupants);
  // Occupants must be an integer of at least 1.
  if (occupants === null || !Number.isInteger(occupants) || occupants < 1) {
    // Record the error.
    errors.push("Occupant count must be a whole number of at least 1.");
  }
  // Style.
  if (!isListed(draft.style, STYLES)) {
    // Record the error.
    errors.push("Choose a style.");
  }
  // Must-have classes in taxonomy order. Unknown names are dropped.
  const mustHave = MUST_HAVE_CLASSES.filter((name) => draft.mustHave.includes(name));
  // At least one catalog class is required.
  if (mustHave.length === 0) {
    // Record the error.
    errors.push("Choose at least one must-have category.");
  }
  // Weights.
  const weights = {} as BuiltRequest["requirement"]["objective_weights"];
  // Every weight is required and must lie in [0, 1].
  for (const name of WEIGHT_NAMES) {
    // Typed text for this weight.
    const parsed = readFinite(draft.weights[name]);
    // Range check.
    if (parsed === null || parsed < 0 || parsed > 1) {
      // Record the error.
      errors.push(`${name} weight must be between 0 and 1.`);
    } else {
      // Store the parsed weight.
      weights[name] = parsed;
    }
  }
  // Stop before building a partial body.
  if (
    errors.length > 0 ||
    sceneId === "" ||
    !isListed(draft.roomType, ROOM_TYPES) ||
    length === null ||
    width === null ||
    height === null ||
    length <= 0 ||
    width <= 0 ||
    height <= 0 ||
    confidence === null ||
    budget === null ||
    budget < 0 ||
    occupants === null ||
    !Number.isInteger(occupants) ||
    occupants < 1 ||
    !isListed(draft.style, STYLES) ||
    mustHave.length === 0 ||
    WEIGHT_NAMES.some((name) => weights[name] === undefined)
  ) {
    // The form shows errors and does not post.
    return { errors, value: null };
  }
  // Ids marked keep, in form order.
  const mustKeepIds = objects.filter((obj) => obj.must_keep).map((obj) => obj.id);
  // Scene body. Version is always 1.
  const scene: BuiltRequest["scene"] = {
    // Trimmed id.
    scene_id: sceneId,
    // First version.
    version: SCENE_VERSION,
    // Room type token.
    room_type: draft.roomType,
    // Dimensions object.
    dimensions: {
      // Length.
      length,
      // Width.
      width,
      // Height.
      height,
      // Confidence.
      confidence,
    },
    // Openings.
    openings,
    // Objects.
    objects,
  };
  // Requirement body. raw_text stays empty.
  const requirement: BuiltRequest["requirement"] = {
    // Derived id.
    requirement_id: requirementIdFor(sceneId),
    // Same scene id. The API returns 422 when these differ.
    scene_id: sceneId,
    // No natural-language text.
    raw_text: "",
    // Budget.
    budget_inr: budget,
    // Catalog classes. Copy so the draft cannot mutate the body.
    must_have: [...mustHave],
    // Kept ids.
    must_keep_object_ids: mustKeepIds,
    // Occupants. The integer check above makes this a whole number.
    occupant_count: occupants,
    // Style token.
    style: draft.style,
    // Accessibility flag.
    accessibility_required: draft.accessibility,
    // All six weights.
    objective_weights: weights,
  };
  // Both bodies are ready.
  return { errors: [], value: { scene, requirement } };
}
