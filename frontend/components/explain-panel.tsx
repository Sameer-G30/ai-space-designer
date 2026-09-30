"use client"; // Explanation, what-if, and version requests run in the browser.

// Local form state.
import { useState } from "react";

// Field styles shared with the room form.
import { inputClassName, labelClassName } from "@/lib/constants";

// Rupees and milliseconds.
import { formatInr, formatMs } from "@/lib/format";

// Readers for the three new routes.
import { parseCounterfactual, parseExplanation, parseVersions } from "@/lib/parse-phase8";

// Shapes.
import type {
  CounterfactualDesign,
  CounterfactualRejected,
  ExplanationBody,
  FailureView,
  VersionsBody,
} from "@/lib/types";

// Props. The anchor is the Pareto design the what-if is posted to.
type ExplainPanelProps = {
  // Pareto design id. Version history is stored on this id.
  anchorDesignId: string;
  // Design currently drawn. After a what-if this is the new design.
  viewDesignId: string;
  // Budget of the solved requirement, used as the +10% default.
  budgetInr: number;
  // Replace the drawn plan with a feasible what-if.
  onCounterfactual: (result: CounterfactualDesign) => void;
};

// POST or GET JSON on this origin.
async function callJson(
  path: string,
  method: "GET" | "POST",
  json?: unknown,
): Promise<{ status: number; body: unknown }> {
  // Same-origin request.
  const response = await fetch(path, {
    // GET or POST.
    method,
    // JSON both ways when there is a body.
    headers: { Accept: "application/json", ...(json === undefined ? {} : { "Content-Type": "application/json" }) },
    // Omit the body for GET.
    body: json === undefined ? undefined : JSON.stringify(json),
    // Do not reuse an older explanation.
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
  // Status plus body.
  return { status: response.status, body };
}

// Join object ids for one table cell. An empty list reads as none.
function idList(ids: string[]): string {
  // Empty.
  if (ids.length === 0) {
    // A word, not a blank cell.
    return "none";
  }
  // Comma-separated ids. They wrap inside the cell.
  return ids.join(", ");
}

// The explanation, the what-if form, and the version table.
export function ExplainPanel({
  anchorDesignId,
  viewDesignId,
  budgetInr,
  onCounterfactual,
}: ExplainPanelProps) {
  // Explanation stored with the design id it belongs to, so a new id does not show the old text.
  const [explanationState, setExplanationState] = useState<{
    id: string;
    body: ExplanationBody | null;
    error: FailureView | null;
  }>({ id: viewDesignId, body: null, error: null });
  // Explanation for the design currently drawn.
  const explanation = explanationState.id === viewDesignId ? explanationState.body : null;
  // Explanation error for that same design.
  const explainError = explanationState.id === viewDesignId ? explanationState.error : null;
  // True while the explanation route is in flight.
  const [explaining, setExplaining] = useState(false);
  // Budget field. The default is 10% above the solved budget.
  const [budgetText, setBudgetText] = useState(String(Math.round(budgetInr * 1.1)));
  // Optional new length.
  const [lengthText, setLengthText] = useState("");
  // Optional new width.
  const [widthText, setWidthText] = useState("");
  // Optional new occupant count.
  const [occupantText, setOccupantText] = useState("");
  // Local form error, before a request is sent.
  const [formError, setFormError] = useState<string | null>(null);
  // What-if HTTP error.
  const [counterError, setCounterError] = useState<FailureView | null>(null);
  // Infeasible what-if. The plan stays on the Pareto point.
  const [rejected, setRejected] = useState<CounterfactualRejected | null>(null);
  // Feasible what-if, kept so the diff stays visible after the plan updates.
  const [accepted, setAccepted] = useState<CounterfactualDesign | null>(null);
  // True while the what-if route is in flight.
  const [countering, setCountering] = useState(false);
  // Version rows for the Pareto design.
  const [versions, setVersions] = useState<VersionsBody | null>(null);
  // Version error.
  const [versionError, setVersionError] = useState<FailureView | null>(null);
  // True while versions are loading.
  const [loadingVersions, setLoadingVersions] = useState(false);
  // Load the explanation for the design that is drawn.
  const explain = async (): Promise<void> => {
    // Show the wait.
    setExplaining(true);
    // Clear the previous error for this design.
    setExplanationState({ id: viewDesignId, body: null, error: null });
    // Request.
    try {
      // GET the explanation. The first call may rephrase with the local model.
      const call = await callJson(`/api/designs/${encodeURIComponent(viewDesignId)}/explanation`, "GET");
      // Read it.
      const read = parseExplanation(call.body, call.status);
      // HTTP error.
      if (read.kind === "failure") {
        // Show it. Keep any previous explanation off the page.
        setExplanationState({ id: viewDesignId, body: null, error: read.failure });
        // Stop.
        return;
      }
      // Store the facts and claims.
      setExplanationState({ id: viewDesignId, body: read.value, error: null });
    } catch (error) {
      // The browser could not reach this Next.js route.
      const detail = error instanceof Error ? error.message : "unknown error";
      // Show it.
      setExplanationState({ id: viewDesignId, body: null, error: { statusCode: null, detail } });
    } finally {
      // Re-enable the button.
      setExplaining(false);
    }
  };
  // Load versions for the Pareto design the what-if was posted to.
  const loadVersions = async (): Promise<void> => {
    // Show the wait.
    setLoadingVersions(true);
    // Clear the previous error.
    setVersionError(null);
    // Request.
    try {
      // GET the rows. The first read stores version 1.
      const call = await callJson(`/api/designs/${encodeURIComponent(anchorDesignId)}/versions`, "GET");
      // Read them.
      const read = parseVersions(call.body, call.status);
      // HTTP error.
      if (read.kind === "failure") {
        // Show it.
        setVersions(null);
        setVersionError(read.failure);
        // Stop.
        return;
      }
      // Store the rows.
      setVersions(read.value);
    } catch (error) {
      // Network error.
      const detail = error instanceof Error ? error.message : "unknown error";
      // Show it.
      setVersionError({ statusCode: null, detail });
    } finally {
      // Re-enable the button.
      setLoadingVersions(false);
    }
  };
  // Build the what-if body from the fields that have text.
  const buildBody = (): Record<string, number> | string => {
    // Fields that were filled.
    const body: Record<string, number> = {};
    // Budget, when the field is not blank.
    if (budgetText.trim() !== "") {
      // Parse.
      const value = Number(budgetText);
      // Non-negative finite rupees.
      if (!Number.isFinite(value) || value < 0) {
        // Form error.
        return "Budget must be a non-negative number.";
      }
      // Send it.
      body.budget_inr = value;
    }
    // Length.
    if (lengthText.trim() !== "") {
      // Parse.
      const value = Number(lengthText);
      // Positive metres.
      if (!Number.isFinite(value) || value <= 0) {
        // Form error.
        return "Length must be a positive number of metres.";
      }
      // Send it.
      body.length_m = value;
    }
    // Width.
    if (widthText.trim() !== "") {
      // Parse.
      const value = Number(widthText);
      // Positive metres.
      if (!Number.isFinite(value) || value <= 0) {
        // Form error.
        return "Width must be a positive number of metres.";
      }
      // Send it.
      body.width_m = value;
    }
    // Occupants.
    if (occupantText.trim() !== "") {
      // Parse.
      const value = Number(occupantText);
      // Integer of at least 1.
      if (!Number.isInteger(value) || value < 1) {
        // Form error.
        return "Occupants must be an integer of at least 1.";
      }
      // Send it.
      body.occupant_count = value;
    }
    // At least one field.
    if (Object.keys(body).length === 0) {
      // Form error.
      return "Change at least one value.";
    }
    // Body.
    return body;
  };
  // Run the what-if against the Pareto design, then refresh its versions.
  const runWhatIf = async (): Promise<void> => {
    // Local checks first.
    const body = buildBody();
    // A string is a form error.
    if (typeof body === "string") {
      // Show it and do not post.
      setFormError(body);
      // Stop.
      return;
    }
    // Clear the form error.
    setFormError(null);
    // Clear the previous HTTP error.
    setCounterError(null);
    // Clear the previous rejection.
    setRejected(null);
    // Show the wait.
    setCountering(true);
    // Request.
    try {
      // POST the delta. Hints come from the stored design on the server.
      const call = await callJson(
        `/api/designs/${encodeURIComponent(anchorDesignId)}/counterfactual`,
        "POST",
        body,
      );
      // Read it.
      const read = parseCounterfactual(call.body, call.status);
      // HTTP error. The plan is left alone.
      if (read.kind === "failure") {
        // Show it.
        setCounterError(read.failure);
        // Stop.
        return;
      }
      // Infeasible. Show the reason and do not replace the plan.
      if (read.value.feasible === false) {
        // Keep the reason.
        setRejected(read.value);
        // Stop.
        return;
      }
      // Remember the diff.
      setAccepted(read.value);
      // Ask the plan to draw this design.
      onCounterfactual(read.value);
      // Refresh the version table so the new row is visible.
      await loadVersions();
    } catch (error) {
      // Network error.
      const detail = error instanceof Error ? error.message : "unknown error";
      // Show it.
      setCounterError({ statusCode: null, detail });
    } finally {
      // Re-enable the button.
      setCountering(false);
    }
  };
  // The three blocks.
  return (
    // Stack.
    <div className="flex flex-col gap-6">
      {/* Explanation. */}
      <section className="flex flex-col gap-3 rounded-2xl border border-stone-200 bg-white p-5 shadow-card animate-rise">
        {/* Heading. */}
        <h3 className="font-display text-lg font-semibold text-stone-900">Explanation</h3>
        {/* Which design will be explained. */}
        <p className="break-all text-sm text-stone-600">Design {viewDesignId}</p>
        {/* Ask for the sentences. */}
        <button
          type="button"
          className="w-fit rounded-md border border-stone-300 bg-white px-3 py-2 text-sm disabled:opacity-60"
          disabled={explaining}
          onClick={() => {
            // Fire the request. Errors are stored in state.
            void explain();
          }}
        >
          Explain this design
        </button>
        {/* Wait. */}
        {explaining ? <p className="text-sm text-stone-600">Writing the explanation.</p> : null}
        {/* HTTP error. */}
        {explainError ? (
          <p className="whitespace-pre-wrap text-sm text-red-800">{explainError.detail}</p>
        ) : null}
        {/* Facts and claims. */}
        {explanation ? (
          <div className="flex flex-col gap-3">
            {/* How the sentences were produced. */}
            <p className="text-sm text-stone-700">
              {explanation.rephrase_note}. Verified {explanation.verified_rate.toFixed(3)}.
            </p>
            {/* Sources. These sentences are the trace, not the model. */}
            <h4 className="text-sm font-semibold text-stone-900">Sources</h4>
            <ul className="flex flex-col gap-2 text-sm text-stone-800">
              {/* One fact. */}
              {explanation.facts.map((fact) => (
                <li key={fact.ref} className="break-words">
                  {/* Pointer. */}
                  <span className="font-mono text-xs text-stone-500">{fact.ref}</span>
                  {/* Sentence. */}
                  <span className="mt-1 block">{fact.text}</span>
                </li>
              ))}
            </ul>
            {/* Claims, each with a verified badge and its source. */}
            <h4 className="text-sm font-semibold text-stone-900">Claims</h4>
            <ul className="flex flex-col gap-2 text-sm text-stone-800">
              {/* One claim. */}
              {explanation.claims.map((claim) => (
                <li key={claim.explanation_id} className="break-words">
                  {/* Badge. */}
                  <span className={claim.verified ? "text-emerald-800" : "text-amber-800"}>
                    {claim.verified ? "Verified" : "Unverified"}
                  </span>
                  {/* Source pointer. */}
                  <span className="ml-2 font-mono text-xs text-stone-500">{claim.supporting_trace_ref}</span>
                  {/* Sentence. */}
                  <span className="mt-1 block">{claim.claim_text}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
      {/* What-if. */}
      <section className="flex flex-col gap-3 rounded-2xl border border-stone-200 bg-white p-5 shadow-card animate-rise">
        {/* Heading. */}
        <h3 className="font-display text-lg font-semibold text-stone-900">What-if</h3>
        {/* What the control does. */}
        <p className="text-sm text-stone-600">
          Re-solves from this Pareto design. The budget field starts at 10% above the solved budget.
          Leave a field blank to keep it.
        </p>
        {/* Fields stack on a narrow screen. */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {/* Budget. */}
          <label className={labelClassName}>
            New budget (INR)
            <input
              className={inputClassName}
              inputMode="decimal"
              value={budgetText}
              onChange={(event) => {
                // Keep the typed text.
                setBudgetText(event.target.value);
              }}
            />
          </label>
          {/* Length. */}
          <label className={labelClassName}>
            New length (m)
            <input
              className={inputClassName}
              inputMode="decimal"
              value={lengthText}
              onChange={(event) => {
                // Keep the typed text.
                setLengthText(event.target.value);
              }}
            />
          </label>
          {/* Width. */}
          <label className={labelClassName}>
            New width (m)
            <input
              className={inputClassName}
              inputMode="decimal"
              value={widthText}
              onChange={(event) => {
                // Keep the typed text.
                setWidthText(event.target.value);
              }}
            />
          </label>
          {/* Occupants. */}
          <label className={labelClassName}>
            New occupants
            <input
              className={inputClassName}
              inputMode="numeric"
              value={occupantText}
              onChange={(event) => {
                // Keep the typed text.
                setOccupantText(event.target.value);
              }}
            />
          </label>
        </div>
        {/* Run. */}
        <button
          type="button"
          className="w-fit rounded-md bg-stone-900 px-3 py-2 text-sm text-white disabled:opacity-60"
          disabled={countering}
          onClick={() => {
            // Fire the request.
            void runWhatIf();
          }}
        >
          Run what-if
        </button>
        {/* Wait. */}
        {countering ? <p className="text-sm text-stone-600">Re-solving with the previous placement as a hint.</p> : null}
        {/* Form error. */}
        {formError ? <p className="text-sm text-red-800">{formError}</p> : null}
        {/* HTTP error. */}
        {counterError ? (
          <p className="whitespace-pre-wrap text-sm text-red-800">{counterError.detail}</p>
        ) : null}
        {/* Infeasible reason. */}
        {rejected ? (
          <p className="whitespace-pre-wrap text-sm text-amber-950">
            No design. {rejected.reason} ({formatMs(rejected.solve_time_ms)})
          </p>
        ) : null}
        {/* Feasible summary and the diff. */}
        {accepted ? (
          <div className="flex flex-col gap-2 text-sm text-stone-800">
            {/* Score, cost, and time. */}
            <p>
              Score change {accepted.score_change.toFixed(6)}, cost change {formatInr(accepted.cost_change)},{" "}
              {accepted.warm_started ? `warm-started with ${accepted.hint_count} hints` : "no hint applied"},{" "}
              {formatMs(accepted.solve_time_ms)}
            </p>
            {/* Sensitivity. */}
            <p>
              {accepted.sensitivity_score_per_inr === null
                ? "The budget did not change, so there is no score-per-rupee figure."
                : `Score change per rupee ${accepted.sensitivity_score_per_inr.toExponential(3)}`}
            </p>
            {/* Object diff. */}
            <p className="break-words">Added: {idList(accepted.diff.items_added)}</p>
            <p className="break-words">Removed: {idList(accepted.diff.items_removed)}</p>
            <p className="break-words">
              Moved:{" "}
              {accepted.diff.items_moved.length === 0
                ? "none"
                : accepted.diff.items_moved
                    .map((item) => `${item.id} (${item.from_position.join(", ")} -> ${item.to_position.join(", ")})`)
                    .join("; ")}
            </p>
          </div>
        ) : null}
      </section>
      {/* Versions of the Pareto design. */}
      <section className="flex flex-col gap-3 rounded-2xl border border-stone-200 bg-white p-5 shadow-card animate-rise">
        {/* Heading. */}
        <h3 className="font-display text-lg font-semibold text-stone-900">Versions</h3>
        {/* Which design the table belongs to. */}
        <p className="break-all text-sm text-stone-600">History for Pareto design {anchorDesignId}</p>
        {/* Load. */}
        <button
          type="button"
          className="w-fit rounded-md border border-stone-300 bg-white px-3 py-2 text-sm disabled:opacity-60"
          disabled={loadingVersions}
          onClick={() => {
            // Fire the request.
            void loadVersions();
          }}
        >
          Compare versions
        </button>
        {/* Wait. */}
        {loadingVersions ? <p className="text-sm text-stone-600">Loading versions.</p> : null}
        {/* HTTP error. */}
        {versionError ? (
          <p className="whitespace-pre-wrap text-sm text-red-800">{versionError.detail}</p>
        ) : null}
        {/* Table. It scrolls sideways on a narrow screen instead of widening the page. */}
        {versions ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[36rem] border-collapse text-left text-sm">
              {/* Column names. */}
              <thead>
                <tr className="border-b border-stone-200 text-stone-600">
                  <th className="py-2 pr-3 font-medium">Version</th>
                  <th className="py-2 pr-3 font-medium">Score</th>
                  <th className="py-2 pr-3 font-medium">Added</th>
                  <th className="py-2 pr-3 font-medium">Removed</th>
                  <th className="py-2 pr-3 font-medium">Moved</th>
                  <th className="py-2 pr-3 font-medium">Cost change</th>
                  <th className="py-2 font-medium">Score change</th>
                </tr>
              </thead>
              <tbody>
                {/* One version. */}
                {versions.versions.map((row) => (
                  <tr key={row.version} className="border-b border-stone-100 align-top">
                    <td className="py-2 pr-3">{row.version}</td>
                    <td className="py-2 pr-3">{row.score.toFixed(3)}</td>
                    <td className="py-2 pr-3 break-words">{idList(row.diff.items_added)}</td>
                    <td className="py-2 pr-3 break-words">{idList(row.diff.items_removed)}</td>
                    <td className="py-2 pr-3">{row.diff.items_moved.length}</td>
                    <td className="py-2 pr-3">{formatInr(row.diff.cost_change)}</td>
                    <td className="py-2">{row.diff.score_change.toFixed(6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}
