"use client"; // Solves stay on this origin.

// State and the results anchor.
import { useEffect, useRef, useState } from "react";

// Results for a finished solve.
import { OutcomePanel } from "@/components/outcome-panel";

// The room and requirement form.
import { RequestForm } from "@/components/request-form";

// Response readers.
import { parseOptimizePayload, parseScenePayload } from "@/lib/parse-result";

// Shapes.
import type {
  BuiltRequest,
  FailureView,
  InfeasibleBody,
  ParetoBody,
  SceneGraph,
} from "@/lib/types";

// A finished solve kept beside the form.
type Outcome =
  // Feasible set.
  | {
      kind: "pareto";
      scene: SceneGraph;
      result: ParetoBody;
      selected: number;
      requirement: BuiltRequest["requirement"];
    }
  // Infeasible reason.
  | { kind: "infeasible"; result: InfeasibleBody };

// POST JSON to a same-origin route and return the status plus the parsed body.
async function postJson(path: string, json: unknown): Promise<{ status: number; body: unknown }> {
  // Same-origin request. API_URL is not used here.
  const response = await fetch(path, {
    // Create or solve.
    method: "POST",
    // JSON both ways.
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    // The scene or the optimize wrapper.
    body: JSON.stringify(json),
    // Do not reuse an older solve.
    cache: "no-store",
  });
  // Body, or null when the response is not JSON.
  let body: unknown = null;
  // Parse when possible.
  try {
    // Read the route JSON.
    body = await response.json();
  } catch {
    // Leave body null. The reader turns that into an HTTP line.
    body = null;
  }
  // Status plus body.
  return { status: response.status, body };
}

// The page: the sentence, the forms, and the selected design.
export function Designer() {
  // True while the two posts are in flight.
  const [pending, setPending] = useState(false);
  // HTTP failure, including 404 and 422.
  const [failure, setFailure] = useState<FailureView | null>(null);
  // A 200 body this page cannot draw.
  const [badDetail, setBadDetail] = useState<string | null>(null);
  // The latest solve.
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  // The results block, scrolled into view after a solve.
  const resultsRef = useRef<HTMLDivElement>(null);
  // Scroll to the result when one arrives.
  useEffect(() => {
    // Only after a solve has produced something to read.
    if (failure !== null || badDetail !== null || outcome !== null) {
      // Bring the panel into view on a small screen.
      resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [failure, badDetail, outcome]);
  // Save the scene, then solve.
  const solve = async (value: BuiltRequest): Promise<void> => {
    // Clear the previous design before the new request so an old plan cannot linger.
    setPending(true);
    // Clear the HTTP error.
    setFailure(null);
    // Clear a bad body.
    setBadDetail(null);
    // Clear the previous outcome.
    setOutcome(null);
    // Post both routes.
    try {
      // Store the scene first.
      const sceneCall = await postJson("/api/scenes", value.scene);
      // Read the echo or the error.
      const sceneRead = parseScenePayload(sceneCall.body, sceneCall.status);
      // 422 from the scene stops the solve.
      if (sceneRead.kind === "failure") {
        // Show the status and detail.
        setFailure(sceneRead.failure);
        // Do not optimize.
        return;
      }
      // A scene echo this page cannot read.
      if (sceneRead.kind === "bad") {
        // Show that text and draw nothing.
        setBadDetail(sceneRead.detail);
        // Do not optimize.
        return;
      }
      // Solve against the stored scene id so the two ids match.
      const optimizeCall = await postJson("/api/designs/optimize", {
        // Stored id.
        scene_id: sceneRead.scene.scene_id,
        // Requirement with that same id.
        requirement: { ...value.requirement, scene_id: sceneRead.scene.scene_id },
      });
      // Read the Pareto body, the reason, or the error.
      const optimizeRead = parseOptimizePayload(optimizeCall.body, optimizeCall.status);
      // 404 and 422 land here.
      if (optimizeRead.kind === "failure") {
        // Show the status and detail. Draw nothing.
        setFailure(optimizeRead.failure);
        // Stop.
        return;
      }
      // A body this page cannot draw.
      if (optimizeRead.kind === "bad") {
        // Show that text.
        setBadDetail(optimizeRead.detail);
        // Stop.
        return;
      }
      // Readable infeasible result. No plan.
      if (optimizeRead.kind === "infeasible") {
        // Keep the reason.
        setOutcome({ kind: "infeasible", result: optimizeRead.result });
        // Stop.
        return;
      }
      // Feasible set. The first point is selected.
      setOutcome({
        // Kind.
        kind: "pareto",
        // Scene used for the room outline.
        scene: sceneRead.scene,
        // The set.
        result: optimizeRead.result,
        // First point.
        selected: 0,
        // Requirement the what-if starts from. The form can change later without rewriting this.
        requirement: value.requirement,
      });
    } catch (error) {
      // The browser could not reach this Next.js route.
      const detail = error instanceof Error ? error.message : "unknown error";
      // Show it as a failed request.
      setFailure({ statusCode: null, detail });
    } finally {
      // Re-enable the form.
      setPending(false);
    }
  };
  // Choose a point. The plan, the bill, and the boxes all read this index.
  const selectPoint = (index: number): void => {
    // Update only a feasible set.
    setOutcome((current) => {
      // Ignore clicks after the result was cleared.
      if (current === null || current.kind !== "pareto") {
        // Leave it.
        return current;
      }
      // Ignore an index outside the returned list.
      if (index < 0 || index >= current.result.points.length) {
        // Leave it.
        return current;
      }
      // Replace the selected index.
      return { ...current, selected: index };
    });
  };
  // The page.
  return (
    // Page column.
    <main className="mx-auto flex min-h-full w-full max-w-7xl flex-col gap-8 px-4 py-8 sm:px-6">
      {/* Hero: name and tagline. */}
      <header className="flex flex-col gap-3 rounded-3xl border border-stone-200 bg-white/70 p-6 shadow-card backdrop-blur">
        {/* Project name. */}
        <h1 className="font-display text-4xl font-semibold tracking-tight text-stone-900">PhotoSpace</h1>
        {/* What this page does. */}
        <p className="max-w-3xl text-stone-600">
          Manual room, a sentence or a structured requirement, Pareto designs, a 3D view, a generated image,
          explanations, what-if, and version comparison.
        </p>
      </header>
      {/* Two columns on wide screens: inputs left, results right. */}
      <div className="grid grid-cols-1 items-start gap-8 lg:grid-cols-[minmax(0,460px)_minmax(0,1fr)]">
        {/* Inputs stay in view while results scroll. */}
        <div className="lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto lg:pr-2">
      {/* Forms. */}
      <RequestForm pending={pending} onSolve={(value) => void solve(value)} />
        </div>
      {/* Results. */}
      <div ref={resultsRef} className="flex min-w-0 flex-col gap-4">
        {/* Solving notice. */}
        {pending ? (
          <div className="flex flex-col gap-3 rounded-2xl border border-stone-200 bg-white p-5 shadow-card">
            <p className="text-sm text-stone-600">Solving the room.</p>
            <div className="skeleton h-24 rounded-xl" />
            <div className="skeleton h-40 rounded-xl" />
          </div>
        ) : null}
        {/* Empty state before the first solve. */}
        {!pending && !failure && !badDetail && !outcome ? (
          <div className="rounded-2xl border border-dashed border-stone-300 bg-white/60 p-10 text-center text-stone-500">
            Your designs will appear here after you save a room and solve.
          </div>
        ) : null}
        {/* HTTP error, including 404 and 422. No plan is drawn. */}
        {failure ? (
          <section className="rounded-lg border border-red-200 bg-red-50 p-4" aria-live="polite">
            {/* Heading. */}
            <h2 className="text-lg font-semibold text-red-900">API error</h2>
            {/* Status, when one exists. */}
            {failure.statusCode === null ? (
              <p className="mt-2 text-sm text-red-800">The request did not complete.</p>
            ) : (
              <p className="mt-2 text-sm text-red-800">HTTP {failure.statusCode}</p>
            )}
            {/* Detail from the proxy. */}
            <p className="mt-2 whitespace-pre-wrap text-sm text-red-800">{failure.detail}</p>
          </section>
        ) : null}
        {/* A body the page refused to draw. */}
        {badDetail ? (
          <section className="rounded-lg border border-red-200 bg-red-50 p-4" aria-live="polite">
            {/* Heading. */}
            <h2 className="text-lg font-semibold text-red-900">API error</h2>
            {/* Explanation. */}
            <p className="mt-2 text-sm text-red-800">{badDetail}</p>
          </section>
        ) : null}
        {/* Pareto set or the infeasible reason. */}
        {outcome ? <OutcomePanel outcome={outcome} onSelect={selectPoint} /> : null}
      </div>
      </div>
    </main>
  );
}
