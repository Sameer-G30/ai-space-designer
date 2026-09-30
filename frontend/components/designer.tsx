"use client"; // Health rechecks and solves stay on this origin.

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
  HealthView,
  InfeasibleBody,
  ParetoBody,
  SceneGraph,
} from "@/lib/types";

// A finished solve kept beside the form.
type Outcome =
  // Feasible set.
  | { kind: "pareto"; scene: SceneGraph; result: ParetoBody; selected: number }
  // Infeasible reason.
  | { kind: "infeasible"; result: InfeasibleBody };

// Props from the server page.
type DesignerProps = {
  // Health read while the page was rendered.
  initialHealth: HealthView;
};

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

// The page: health, the sentence, the forms, and the selected design.
export function Designer({ initialHealth }: DesignerProps) {
  // Health, starting from the server render.
  const [health, setHealth] = useState(initialHealth);
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
  // Status line in the Phase 0 shape.
  const statusLine =
    health.statusCode === null ? health.status : `${health.status} (HTTP ${health.statusCode})`;
  // Scroll to the result when one arrives.
  useEffect(() => {
    // Only after a solve has produced something to read.
    if (failure !== null || badDetail !== null || outcome !== null) {
      // Bring the panel into view on a small screen.
      resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [failure, badDetail, outcome]);
  // Ask the health route again without losing the form.
  const recheck = async (): Promise<void> => {
    // The route answers even when the API is down.
    try {
      // Same-origin health check.
      const response = await fetch("/api/health", { cache: "no-store" });
      // Parsed payload.
      const body = (await response.json()) as HealthView;
      // Replace the status line.
      setHealth(body);
    } catch (error) {
      // The route itself could not be reached.
      const detail = error instanceof Error ? error.message : "unknown error";
      // Show unreachable.
      setHealth({ statusCode: null, status: "unreachable", detail });
    }
  };
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
    <main className="mx-auto flex min-h-full w-full max-w-6xl flex-col gap-8 px-4 py-8 sm:px-6">
      {/* Title and the Phase 0 health line. */}
      <header className="flex flex-col gap-3">
        {/* Project name. */}
        <h1 className="text-3xl font-semibold tracking-tight">PhotoSpace</h1>
        {/* What this page does. */}
        <p className="text-zinc-600">Manual room, a sentence or a structured requirement, and Pareto designs.</p>
        {/* Phase 0 check label, kept so the health line is still obvious. */}
        <p className="text-sm text-zinc-500">Phase 0 API health check</p>
        {/* Status returned by GET /health. */}
        <p className="rounded-lg border border-zinc-200 bg-white px-4 py-3 text-lg">API status: {statusLine}</p>
        {/* Failure detail from the health check. */}
        {health.detail ? <p className="text-sm text-red-700">{health.detail}</p> : null}
        {/* Recheck without posting a room. */}
        <button
          type="button"
          className="w-fit rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm"
          onClick={() => {
            // Fire the recheck. Errors are stored in state.
            void recheck();
          }}
        >
          Recheck API
        </button>
      </header>
      {/* Forms. */}
      <RequestForm pending={pending} onSolve={(value) => void solve(value)} />
      {/* Results. */}
      <div ref={resultsRef} className="flex flex-col gap-4">
        {/* Solving notice. */}
        {pending ? <p className="text-sm text-zinc-600">Solving the room.</p> : null}
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
    </main>
  );
}
