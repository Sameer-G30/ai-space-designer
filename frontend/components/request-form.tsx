"use client"; // The form collects a scene and a requirement, then asks the page to post them.

// Form event type.
import { useState } from "react";

// Form event type, imported separately so the value import stays the hook.
import type { FormEvent } from "react";

// Validate and build the two JSON bodies.
import { buildRequest } from "@/lib/build-request";

// Reader for POST /api/requirements. A failure does not fill the form.
import { parseRequirementPayload } from "@/lib/parse-requirement";

// Lists, notes, and classes.
import {
  ABSENT_NOTE,
  CONFIDENCE_LEVELS,
  DOOR_NOTE,
  FURNITURE_CLASSES,
  MUST_HAVE_CLASSES,
  OPENING_TYPES,
  PARSER_NOTE,
  POSITION_NOTE,
  PRICE_NOTE,
  ROOM_TYPES,
  STYLE_NOTE,
  STYLES,
  WALLS,
  WEIGHT_LABELS,
  WEIGHT_NAMES,
  inputClassName,
  labelClassName,
  readableToken,
  requirementIdFor,
} from "@/lib/constants";

// Draft shapes and the built request.
import type { BuiltRequest, ObjectDraft, OpeningDraft, ParseSuccess, WeightName } from "@/lib/types";

// Props.
type RequestFormProps = {
  // True while a solve is in flight.
  pending: boolean;
  // Called with a schema-shaped body after the local checks pass.
  onSolve: (value: BuiltRequest) => void;
};

// Starting weights. Each one is 1. They are not scaled to sum to 1.
function initialWeights(): Record<WeightName, string> {
  // All six fields.
  return {
    // Layout.
    layout: "1",
    // Circulation.
    circulation: "1",
    // Ergonomics.
    ergonomics: "1",
    // Budget.
    budget: "1",
    // Aesthetics.
    aesthetics: "1",
    // Sustainability.
    sustainability: "1",
  };
}

// The room form and the structured requirement form.
export function RequestForm({ pending, onSolve }: RequestFormProps) {
  // Scene id.
  const [sceneId, setSceneId] = useState("room-1");
  // Room type.
  const [roomType, setRoomType] = useState("home_office");
  // Length text.
  const [length, setLength] = useState("6");
  // Width text.
  const [width, setWidth] = useState("6");
  // Height text.
  const [height, setHeight] = useState("2.8");
  // Confidence.
  const [confidence, setConfidence] = useState("high");
  // Opening rows. One feasible door is filled in so the plan has an opening.
  const [openings, setOpenings] = useState<OpeningDraft[]>([
    {
      // Stable key.
      key: "opening-1",
      // Door.
      type: "door",
      // South wall.
      wall: "south",
      // Metres from the west end.
      position: "0.4",
      // Wider than the 0.815 m door limit.
      width: "0.9",
    },
  ]);
  // Next opening key number.
  const [nextOpening, setNextOpening] = useState(2);
  // Existing objects. None by default.
  const [objects, setObjects] = useState<ObjectDraft[]>([]);
  // Next object key number.
  const [nextObject, setNextObject] = useState(1);
  // Budget text.
  const [budget, setBudget] = useState("80000");
  // Checked catalog classes.
  const [mustHave, setMustHave] = useState<string[]>(["desk", "chair"]);
  // Occupant text.
  const [occupants, setOccupants] = useState("1");
  // Style.
  const [style, setStyle] = useState("modern");
  // Accessibility flag.
  const [accessibility, setAccessibility] = useState(false);
  // Six weights.
  const [weights, setWeights] = useState(initialWeights);
  // Local problems. These are shown before any request.
  const [errors, setErrors] = useState<string[]>([]);
  // The sentence. Parsing fills the structured fields. Editing them stays possible.
  const [sentence, setSentence] = useState("");
  // True while POST /api/requirements is in flight.
  const [parsing, setParsing] = useState(false);
  // Parser error. Fields are not changed when this is set from a failed parse.
  const [parseError, setParseError] = useState<string | null>(null);
  // True only after a response this form accepted.
  const [parseOk, setParseOk] = useState(false);
  // Retrieved numbers from the last successful parse.
  const [retrieved, setRetrieved] = useState<ParseSuccess["retrieved"]>([]);
  // Unchanged solver constants from that response.
  const [solverConstants, setSolverConstants] = useState<ParseSuccess["solver_constants_m"]>([]);
  // Why the retrieved list is empty, or ok.
  const [retrievalNote, setRetrievalNote] = useState("");
  // Add a window row.
  const addOpening = (): void => {
    // Next key.
    const key = `opening-${nextOpening}`;
    // Advance the counter.
    setNextOpening(nextOpening + 1);
    // Append a window on the north wall.
    setOpenings([
      ...openings,
      { key, type: "window", wall: "north", position: "0.4", width: "1.2" },
    ]);
  };
  // Remove one opening row.
  const removeOpening = (key: string): void => {
    // Keep the other rows.
    setOpenings(openings.filter((opening) => opening.key !== key));
  };
  // Patch one opening field.
  const patchOpening = (key: string, patch: Partial<OpeningDraft>): void => {
    // Replace the matching row.
    setOpenings(openings.map((opening) => (opening.key === key ? { ...opening, ...patch } : opening)));
  };
  // Add a kept object row.
  const addObject = (): void => {
    // Next key.
    const key = `object-${nextObject}`;
    // Advance the counter.
    setNextObject(nextObject + 1);
    // Append a chair the user can edit.
    setObjects([
      ...objects,
      {
        // Key.
        key,
        // Default id.
        id: `kept-${nextObject}`,
        // Chair.
        type: "chair",
        // Centre x.
        x: "1",
        // Centre y.
        y: "1",
        // Degrees.
        rotation: "0",
        // Local length.
        length: "0.5",
        // Local width.
        width: "0.5",
        // Height.
        height: "0.9",
        // Kept by default.
        mustKeep: true,
      },
    ]);
  };
  // Remove one object row.
  const removeObject = (key: string): void => {
    // Keep the other rows.
    setObjects(objects.filter((obj) => obj.key !== key));
  };
  // Patch one object field.
  const patchObject = (key: string, patch: Partial<ObjectDraft>): void => {
    // Replace the matching row.
    setObjects(objects.map((obj) => (obj.key === key ? { ...obj, ...patch } : obj)));
  };
  // Toggle one catalog class.
  const toggleMustHave = (name: string): void => {
    // Remove it when it is already checked.
    if (mustHave.includes(name)) {
      // Uncheck.
      setMustHave(mustHave.filter((item) => item !== name));
      // Done.
      return;
    }
    // Check it.
    setMustHave([...mustHave, name]);
  };
  // Change one weight.
  const setWeight = (name: WeightName, value: string): void => {
    // Replace that field only.
    setWeights({ ...weights, [name]: value });
  };
  // Validate, then hand the bodies to the page.
  const onSubmit = (event: FormEvent<HTMLFormElement>): void => {
    // The page posts through a route. The browser must not navigate.
    event.preventDefault();
    // Build both bodies.
    const built = buildRequest({
      // Scene id.
      sceneId,
      // Room type.
      roomType,
      // Length.
      length,
      // Width.
      width,
      // Height.
      height,
      // Confidence.
      confidence,
      // Openings.
      openings,
      // Objects.
      objects,
      // Budget.
      budget,
      // Must-have classes.
      mustHave,
      // Occupants.
      occupants,
      // Style.
      style,
      // Accessibility.
      accessibility,
      // Weights.
      weights,
      // The sentence they typed. Empty when the box is empty.
      rawText: sentence,
    });
    // Show local problems and do not post.
    if (built.value === null) {
      // Keep the messages.
      setErrors(built.errors);
      // Stop.
      return;
    }
    // Clear local problems.
    setErrors([]);
    // Ask the page to save the scene and solve.
    onSolve(built.value);
  };
  // Format a whole number without a trailing .0, and leave other numbers as text.
  const numberText = (value: number): string => {
    // Integers stay integers so the budget field does not show 80000.0.
    if (Number.isInteger(value)) {
      // Decimal-free text.
      return String(value);
    }
    // A fractional weight or budget.
    return String(value);
  };
  // Copy a successful parse into the structured fields.
  const applyParse = (result: ParseSuccess): void => {
    // Budget.
    setBudget(numberText(result.requirement.budget_inr));
    // People.
    setOccupants(numberText(result.requirement.occupant_count));
    // Style token. The reader already checked the closed list.
    setStyle(result.requirement.style);
    // Accessibility flag.
    setAccessibility(result.requirement.accessibility_required);
    // Catalog classes, in the order the API returned.
    setMustHave(result.requirement.must_have);
    // The six weights.
    setWeights({
      // Layout.
      layout: numberText(result.requirement.objective_weights.layout),
      // Circulation.
      circulation: numberText(result.requirement.objective_weights.circulation),
      // Ergonomics.
      ergonomics: numberText(result.requirement.objective_weights.ergonomics),
      // Budget.
      budget: numberText(result.requirement.objective_weights.budget),
      // Aesthetics.
      aesthetics: numberText(result.requirement.objective_weights.aesthetics),
      // Sustainability.
      sustainability: numberText(result.requirement.objective_weights.sustainability),
    });
    // Check keep on objects whose ids the parser named. Other rows stay, unchecked.
    const keepIds = new Set(result.requirement.must_keep_object_ids);
    // Update the flag only.
    setObjects(objects.map((obj) => ({ ...obj, mustKeep: keepIds.has(obj.id) })));
    // Numbers and constants from this response.
    setRetrieved(result.retrieved);
    // Unchanged solver constants.
    setSolverConstants(result.solver_constants_m);
    // Note, including an empty-index explanation.
    setRetrievalNote(result.retrieval_note);
    // The fields now came from the parser.
    setParseOk(true);
    // Clear a previous parser error.
    setParseError(null);
  };
  // Post the sentence. Do not change the structured fields unless the body validates.
  const parseSentence = async (): Promise<void> => {
    // A blank sentence is a local error.
    if (sentence.trim() === "") {
      // Show it.
      setParseError("Type a sentence before parsing.");
      // Do not claim a parse.
      setParseOk(false);
      // Stop.
      return;
    }
    // The requirement is tied to the scene id.
    if (sceneId.trim() === "") {
      // Show it.
      setParseError("Enter a scene id before parsing.");
      // Do not claim a parse.
      setParseOk(false);
      // Stop.
      return;
    }
    // In flight.
    setParsing(true);
    // Clear the previous error. Fields stay until a success replaces them.
    setParseError(null);
    // Post the same-origin route.
    try {
      // Objects the sentence may keep. Empty ids are omitted.
      const objectRefs = objects
        .filter((obj) => obj.id.trim() !== "" && obj.type.trim() !== "")
        .map((obj) => ({ id: obj.id.trim(), type: obj.type }));
      // Same-origin request. The route calls FastAPI.
      const response = await fetch("/api/requirements", {
        // Parse.
        method: "POST",
        // JSON.
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        // Sentence, scene, and object ids.
        body: JSON.stringify({
          scene_id: sceneId.trim(),
          raw_text: sentence,
          requirement_id: requirementIdFor(sceneId),
          objects: objectRefs,
        }),
        // Do not reuse an older parse.
        cache: "no-store",
      });
      // Body, or null when it is not JSON.
      let body: unknown = null;
      // Parse when possible.
      try {
        // Route JSON.
        body = await response.json();
      } catch {
        // Leave body null. The reader turns that into an HTTP line.
        body = null;
      }
      // Classify the body.
      const read = parseRequirementPayload(body, response.status);
      // 422 and other errors. Do not copy fields.
      if (read.kind === "failure") {
        // Show the parser error.
        setParseError(read.failure.detail);
        // This sentence was not parsed.
        setParseOk(false);
        // Stop.
        return;
      }
      // A 200 body this form will not edit from.
      if (read.kind === "bad") {
        // Show that text.
        setParseError(read.detail);
        // This sentence was not parsed.
        setParseOk(false);
        // Stop.
        return;
      }
      // The scene id on the requirement must be the one in the form.
      if (read.result.requirement.scene_id !== sceneId.trim()) {
        // Do not apply a mismatched scene.
        setParseError("The parser returned a different scene id. The fields were not changed.");
        // Not applied.
        setParseOk(false);
        // Stop.
        return;
      }
      // Copy the structured fields.
      applyParse(read.result);
    } catch (error) {
      // The browser could not reach this Next.js route.
      const detail = error instanceof Error ? error.message : "unknown error";
      // Show it. Do not copy fields.
      setParseError(detail);
      // Not parsed.
      setParseOk(false);
    } finally {
      // Re-enable the button.
      setParsing(false);
    }
  };
  // Solving or parsing disables the fields.
  const busy = pending || parsing;
  // The form.
  return (
    // noValidate lets the page show its own messages, including API 422 text.
    <form className="flex flex-col gap-8" onSubmit={onSubmit} noValidate>
      {/* Room measurements. */}
      <fieldset className="flex flex-col gap-4">
        {/* Section title. */}
        <legend className="text-lg font-semibold text-zinc-900">Room</legend>
        {/* Version is fixed. */}
        <p className="text-sm text-zinc-600">Scene version is 1. This form does not upload a photo.</p>
        {/* Measurement grid. */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {/* Scene id. */}
          <label className={labelClassName}>
            Scene id
            {/* Text field. */}
            <input
              className={inputClassName}
              value={sceneId}
              onChange={(event) => setSceneId(event.target.value)}
              disabled={busy}
              autoComplete="off"
            />
          </label>
          {/* Room type. */}
          <label className={labelClassName}>
            Room type
            {/* The 15 taxonomy types. */}
            <select
              className={inputClassName}
              value={roomType}
              onChange={(event) => setRoomType(event.target.value)}
              disabled={busy}
            >
              {/* One option per room type. */}
              {ROOM_TYPES.map((name) => (
                <option key={name} value={name}>
                  {readableToken(name)}
                </option>
              ))}
            </select>
          </label>
          {/* Confidence. */}
          <label className={labelClassName}>
            Confidence
            {/* low, medium, or high. */}
            <select
              className={inputClassName}
              value={confidence}
              onChange={(event) => setConfidence(event.target.value)}
              disabled={busy}
            >
              {/* One option per level. */}
              {CONFIDENCE_LEVELS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          {/* Length. */}
          <label className={labelClassName}>
            Room length (m)
            {/* Metres along x. */}
            <input
              className={inputClassName}
              inputMode="decimal"
              value={length}
              onChange={(event) => setLength(event.target.value)}
              disabled={busy}
            />
          </label>
          {/* Width. */}
          <label className={labelClassName}>
            Room width (m)
            {/* Metres along y. */}
            <input
              className={inputClassName}
              inputMode="decimal"
              value={width}
              onChange={(event) => setWidth(event.target.value)}
              disabled={busy}
            />
          </label>
          {/* Height. */}
          <label className={labelClassName}>
            Room height (m)
            {/* Floor to ceiling. */}
            <input
              className={inputClassName}
              inputMode="decimal"
              value={height}
              onChange={(event) => setHeight(event.target.value)}
              disabled={busy}
            />
          </label>
        </div>
        {/* Low confidence changes the solver, so say so while it is selected. */}
        {confidence === "low" ? (
          <p className="text-sm text-amber-900">Low confidence insets every wall by 0.10 m.</p>
        ) : null}
      </fieldset>
      {/* Openings. */}
      <fieldset className="flex flex-col gap-4">
        {/* Section title. */}
        <legend className="text-lg font-semibold text-zinc-900">Openings</legend>
        {/* How position is measured. */}
        <p className="text-sm text-zinc-600">{POSITION_NOTE}</p>
        {/* Narrow doors are a readable infeasible result. */}
        <p className="text-sm text-zinc-600">{DOOR_NOTE}</p>
        {/* One card per opening. */}
        {openings.map((opening, index) => (
          <div key={opening.key} className="grid grid-cols-1 gap-3 rounded-lg border border-zinc-200 p-3 sm:grid-cols-2 lg:grid-cols-5">
            {/* Type. */}
            <label className={labelClassName}>
              {`Opening ${index + 1} type`}
              {/* Door or window. */}
              <select
                className={inputClassName}
                value={opening.type}
                onChange={(event) =>
                  patchOpening(opening.key, { type: event.target.value === "window" ? "window" : "door" })
                }
                disabled={busy}
              >
                {/* Both kinds. */}
                {OPENING_TYPES.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            {/* Wall. */}
            <label className={labelClassName}>
              {`Opening ${index + 1} wall`}
              {/* Four walls. */}
              <select
                className={inputClassName}
                value={opening.wall}
                onChange={(event) => {
                  // Only the four known walls are written back.
                  const wall = WALLS.find((name) => name === event.target.value);
                  // Ignore anything else.
                  if (wall !== undefined) {
                    // Store it.
                    patchOpening(opening.key, { wall });
                  }
                }}
                disabled={busy}
              >
                {/* One option per wall. */}
                {WALLS.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            {/* Position. */}
            <label className={labelClassName}>
              {`Opening ${index + 1} position (m)`}
              {/* Metres from the start of the wall. */}
              <input
                className={inputClassName}
                inputMode="decimal"
                value={opening.position}
                onChange={(event) => patchOpening(opening.key, { position: event.target.value })}
                disabled={busy}
              />
            </label>
            {/* Width. */}
            <label className={labelClassName}>
              {`Opening ${index + 1} width (m)`}
              {/* Opening width. */}
              <input
                className={inputClassName}
                inputMode="decimal"
                value={opening.width}
                onChange={(event) => patchOpening(opening.key, { width: event.target.value })}
                disabled={busy}
              />
            </label>
            {/* Remove. */}
            <div className="flex items-end">
              {/* Does not submit the form. */}
              <button
                type="button"
                className="rounded-md border border-zinc-300 px-3 py-2 text-sm"
                onClick={() => removeOpening(opening.key)}
                disabled={busy}
              >
                Remove opening
              </button>
            </div>
          </div>
        ))}
        {/* Add a row. */}
        <button
          type="button"
          className="w-fit rounded-md border border-zinc-300 px-3 py-2 text-sm"
          onClick={addOpening}
          disabled={busy}
        >
          Add opening
        </button>
      </fieldset>
      {/* Existing objects the user may keep. */}
      <fieldset className="flex flex-col gap-4">
        {/* Section title. */}
        <legend className="text-lg font-semibold text-zinc-900">Existing objects</legend>
        {/* What keep means. */}
        <p className="text-sm text-zinc-600">
          Only objects marked keep are held in place. Their ids are sent as must-keep ids. Unchecked objects are stored on the scene and are not held in place. Kept objects use the room confidence.
        </p>
        {/* Duplicate ids are rejected by the API so the error panel can show HTTP 422. */}
        <p className="text-sm text-zinc-600">Object ids must be unique. The API rejects duplicates.</p>
        {/* One card per object. */}
        {objects.map((obj, index) => (
          <div key={obj.key} className="grid grid-cols-1 gap-3 rounded-lg border border-zinc-200 p-3 sm:grid-cols-2 lg:grid-cols-4">
            {/* Id. */}
            <label className={labelClassName}>
              {`Object ${index + 1} id`}
              {/* Free text. */}
              <input
                className={inputClassName}
                value={obj.id}
                onChange={(event) => patchObject(obj.key, { id: event.target.value })}
                disabled={busy}
                autoComplete="off"
              />
            </label>
            {/* Class. All 26 classes, including ones that are not catalog choices. */}
            <label className={labelClassName}>
              {`Object ${index + 1} type`}
              {/* Taxonomy list. */}
              <select
                className={inputClassName}
                value={obj.type}
                onChange={(event) => patchObject(obj.key, { type: event.target.value })}
                disabled={busy}
              >
                {/* One option per class. */}
                {FURNITURE_CLASSES.map((name) => (
                  <option key={name} value={name}>
                    {readableToken(name)}
                  </option>
                ))}
              </select>
            </label>
            {/* Centre x. */}
            <label className={labelClassName}>
              {`Object ${index + 1} centre x (m)`}
              {/* Floor x. */}
              <input
                className={inputClassName}
                inputMode="decimal"
                value={obj.x}
                onChange={(event) => patchObject(obj.key, { x: event.target.value })}
                disabled={busy}
              />
            </label>
            {/* Centre y. */}
            <label className={labelClassName}>
              {`Object ${index + 1} centre y (m)`}
              {/* Floor y. */}
              <input
                className={inputClassName}
                inputMode="decimal"
                value={obj.y}
                onChange={(event) => patchObject(obj.key, { y: event.target.value })}
                disabled={busy}
              />
            </label>
            {/* Rotation. */}
            <label className={labelClassName}>
              {`Object ${index + 1} rotation (degrees)`}
              {/* 180 and 270 are allowed for a kept object. */}
              <input
                className={inputClassName}
                inputMode="decimal"
                value={obj.rotation}
                onChange={(event) => patchObject(obj.key, { rotation: event.target.value })}
                disabled={busy}
              />
            </label>
            {/* Length. */}
            <label className={labelClassName}>
              {`Object ${index + 1} length (m)`}
              {/* Local length. */}
              <input
                className={inputClassName}
                inputMode="decimal"
                value={obj.length}
                onChange={(event) => patchObject(obj.key, { length: event.target.value })}
                disabled={busy}
              />
            </label>
            {/* Width. */}
            <label className={labelClassName}>
              {`Object ${index + 1} width (m)`}
              {/* Local width. */}
              <input
                className={inputClassName}
                inputMode="decimal"
                value={obj.width}
                onChange={(event) => patchObject(obj.key, { width: event.target.value })}
                disabled={busy}
              />
            </label>
            {/* Height. */}
            <label className={labelClassName}>
              {`Object ${index + 1} height (m)`}
              {/* Height. */}
              <input
                className={inputClassName}
                inputMode="decimal"
                value={obj.height}
                onChange={(event) => patchObject(obj.key, { height: event.target.value })}
                disabled={busy}
              />
            </label>
            {/* Keep checkbox. */}
            <label className="flex items-center gap-2 text-sm text-zinc-800">
              {/* Checkbox. */}
              <input
                type="checkbox"
                checked={obj.mustKeep}
                onChange={(event) => patchObject(obj.key, { mustKeep: event.target.checked })}
                disabled={busy}
              />
              Keep this object
            </label>
            {/* Remove. */}
            <div className="flex items-end">
              {/* Does not submit the form. */}
              <button
                type="button"
                className="rounded-md border border-zinc-300 px-3 py-2 text-sm"
                onClick={() => removeObject(obj.key)}
                disabled={busy}
              >
                Remove object
              </button>
            </div>
          </div>
        ))}
        {/* Add a row. */}
        <button
          type="button"
          className="w-fit rounded-md border border-zinc-300 px-3 py-2 text-sm"
          onClick={addObject}
          disabled={busy}
        >
          Add kept object
        </button>
      </fieldset>
      {/* Sentence. A successful parse fills the structured fields. A failure does not. */}
      <fieldset className="flex flex-col gap-4">
        {/* Section title. */}
        <legend className="text-lg font-semibold text-zinc-900">Sentence</legend>
        {/* What the button does, and what a failure does not do. */}
        <p className="text-sm text-zinc-600">{PARSER_NOTE}</p>
        {/* The sentence. */}
        <label className={labelClassName}>
          Room sentence
          {/* Free text. The browser posts it to this app, not to port 8001. */}
          <textarea
            className={`${inputClassName} min-h-28`}
            value={sentence}
            onChange={(event) => {
              // Keep the typed sentence.
              setSentence(event.target.value);
              // The previous parse no longer matches this text.
              setParseOk(false);
              // Drop numbers from the previous sentence.
              setRetrieved([]);
              // Drop the previous constants list too.
              setSolverConstants([]);
              // Drop the previous note.
              setRetrievalNote("");
              // A stale error should not sit under a sentence the user is rewriting.
              setParseError(null);
            }}
            disabled={busy}
            rows={4}
          />
        </label>
        {/* Parse. This does not solve the room. */}
        <button
          type="button"
          className="w-fit rounded-md border border-zinc-300 px-3 py-2 text-sm disabled:opacity-50"
          onClick={() => {
            // Errors are stored in state.
            void parseSentence();
          }}
          disabled={busy}
        >
          {parsing ? "Parsing" : "Parse sentence"}
        </button>
        {/* Parser error. The structured fields were not replaced. */}
        {parseError ? (
          <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">
            {parseError}
          </p>
        ) : null}
        {/* Success. The user can still edit every structured field. */}
        {parseOk ? (
          <p className="text-sm text-zinc-700">
            Parsed. The structured fields came from this sentence. Edit any field before solving.
          </p>
        ) : null}
        {/* Retrieved numbers. Passages are not shown. */}
        {parseOk && retrieved.length > 0 ? (
          <div className="flex flex-col gap-2">
            {/* What the list is. */}
            <p className="text-sm text-zinc-600">
              Retrieved clearances and ergonomic numbers. They did not change the solver constants.
            </p>
            {/* One row per number. */}
            <ul className="flex flex-col gap-1 text-sm text-zinc-800">
              {retrieved.map((item) => (
                <li key={`${item.chunk_id}-${item.name}-${item.value_m}`}>
                  {`${item.name.replaceAll("_", " ")}: ${item.value_m.toFixed(3)} m, ${item.source.replaceAll("_", " ")}, ${item.page === null ? "no page" : `page ${item.page}`}, ${item.topic.replaceAll("_", " ")}`}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {/* Retrieval note when the search ran but found no number, or could not run. */}
        {parseOk && retrievalNote !== "" && retrievalNote !== "ok" ? (
          <p className="text-sm text-zinc-600">{retrievalNote}</p>
        ) : null}
        {/* Constants recorded beside the parse. */}
        {parseOk && solverConstants.length > 0 ? (
          <p className="text-sm text-zinc-600">
            {`Solver constants unchanged: ${solverConstants.map((item) => `${item.name.replaceAll("_", " ")} ${item.value_m} m`).join(", ")}.`}
          </p>
        ) : null}
      </fieldset>
      {/* Structured requirement. It stays visible after a parse so the user can edit it. */}
      <fieldset className="flex flex-col gap-4">
        {/* Section title. */}
        <legend className="text-lg font-semibold text-zinc-900">Requirement</legend>
        {/* The same note, beside the fields the parser fills. */}
        <p className="text-sm text-zinc-600">{PARSER_NOTE}</p>
        {/* Derived requirement id. */}
        <p className="text-sm text-zinc-700">Requirement id: {requirementIdFor(sceneId) || "(scene id)"}</p>
        {/* Budget and occupants. */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {/* Budget. */}
          <label className={labelClassName}>
            Budget (INR)
            {/* Rupees. */}
            <input
              className={inputClassName}
              inputMode="decimal"
              value={budget}
              onChange={(event) => setBudget(event.target.value)}
              disabled={busy}
            />
          </label>
          {/* Occupants. */}
          <label className={labelClassName}>
            Occupant count
            {/* Whole number. */}
            <input
              className={inputClassName}
              inputMode="numeric"
              value={occupants}
              onChange={(event) => setOccupants(event.target.value)}
              disabled={busy}
            />
          </label>
          {/* Style. */}
          <label className={labelClassName}>
            Style
            {/* Generator style list. */}
            <select
              className={inputClassName}
              value={style}
              onChange={(event) => setStyle(event.target.value)}
              disabled={busy}
            >
              {/* One option per style. */}
              {STYLES.map((name) => (
                <option key={name} value={name}>
                  {readableToken(name)}
                </option>
              ))}
            </select>
          </label>
          {/* Accessibility. */}
          <label className="flex items-center gap-2 self-end text-sm text-zinc-800">
            {/* Checkbox. */}
            <input
              type="checkbox"
              checked={accessibility}
              onChange={(event) => setAccessibility(event.target.checked)}
              disabled={busy}
            />
            Accessibility required
          </label>
        </div>
        {/* Price and style disclosures. */}
        <p className="text-sm text-zinc-600">{PRICE_NOTE}</p>
        {/* Style disclosure. */}
        <p className="text-sm text-zinc-600">{STYLE_NOTE}</p>
        {/* Must-have classes. */}
        <div className="flex flex-col gap-2">
          {/* Group label. */}
          <p className="text-sm font-medium text-zinc-800">Must-have categories</p>
          {/* Why three classes are missing. */}
          <p className="text-sm text-zinc-600">{ABSENT_NOTE}</p>
          {/* Checkbox grid. */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {/* One checkbox per catalog class. */}
            {MUST_HAVE_CLASSES.map((name) => (
              <label key={name} className="flex items-center gap-2 text-sm text-zinc-800">
                {/* Checkbox. */}
                <input
                  type="checkbox"
                  checked={mustHave.includes(name)}
                  onChange={() => toggleMustHave(name)}
                  disabled={busy}
                />
                {readableToken(name)}
              </label>
            ))}
          </div>
        </div>
        {/* Weights. */}
        <div className="flex flex-col gap-2">
          {/* Group label. */}
          <p className="text-sm font-medium text-zinc-800">Objective weights</p>
          {/* They are not normalised. */}
          <p className="text-sm text-zinc-600">Each weight is from 0 to 1. They are not rescaled to sum to 1.</p>
          {/* Six number fields. */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {/* One field per weight. */}
            {WEIGHT_NAMES.map((name) => (
              <label key={name} className={labelClassName}>
                {WEIGHT_LABELS[name]}
                {/* The value as typed. */}
                <input
                  className={inputClassName}
                  inputMode="decimal"
                  value={weights[name]}
                  onChange={(event) => setWeight(name, event.target.value)}
                  disabled={busy}
                />
              </label>
            ))}
          </div>
        </div>
      </fieldset>
      {/* Local problems. */}
      {errors.length > 0 ? (
        <ul className="list-disc rounded-lg border border-red-200 bg-red-50 p-4 pl-8 text-sm text-red-800" role="alert">
          {/* One message. */}
          {errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      ) : null}
      {/* Submit both requests. */}
      <button
        type="submit"
        className="w-fit rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        disabled={busy}
      >
        {pending ? "Solving" : "Save room and solve"}
      </button>
    </form>
  );
}
