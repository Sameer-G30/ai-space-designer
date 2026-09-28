// Result of reading GET /health, including a failed request.
type HealthView = {
  // HTTP status code, or null when the request did not complete.
  statusCode: number | null;
  // Status string from the API, or "unreachable" when the call failed.
  status: string;
  // Error text when the request failed before a JSON body arrived.
  detail: string;
};

// Read GET /health from the FastAPI process.
async function loadHealth(origin: string): Promise<HealthView> {
  // Catch network failures so the page can show them.
  try {
    // Ask for a fresh response on every page load.
    const response = await fetch(`${origin}/health`, { cache: "no-store" });
    // Parse the JSON body.
    const body: { status?: unknown } = await response.json();
    // Keep the status only when it is the string the API promises.
    const status = typeof body.status === "string" ? body.status : "unknown";
    // Return the HTTP code and the status string.
    return { statusCode: response.status, status, detail: "" };
  } catch (error) {
    // Use the error message when one is available.
    const detail = error instanceof Error ? error.message : "unknown error";
    // Report that the API could not be reached.
    return { statusCode: null, status: "unreachable", detail };
  }
}

// Render the Phase 0 page that displays the API health check.
export default async function HomePage() {
  // Read the API origin configured for this frontend.
  const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8001";
  // Load the health payload before rendering.
  const health = await loadHealth(apiUrl);
  // Choose the status line the page shows.
  const statusLine =
    health.statusCode === null
      ? health.status
      : `${health.status} (HTTP ${health.statusCode})`;
  // Render the status card.
  return (
    // Center the card on the page.
    <main className="mx-auto flex min-h-full max-w-xl flex-col justify-center gap-4 px-6 py-16">
      {/* Project name. */}
      <h1 className="text-3xl font-semibold tracking-tight">PhotoSpace</h1>
      {/* What this page is checking. */}
      <p className="text-zinc-600">Phase 0 API health check</p>
      {/* Status returned by GET /health. */}
      <p className="rounded-lg border border-zinc-200 px-4 py-3 text-lg">
        API status: {statusLine}
      </p>
      {/* Show the failure detail only when the request did not succeed. */}
      {health.detail ? <p className="text-sm text-red-700">{health.detail}</p> : null}
    </main>
  );
}
