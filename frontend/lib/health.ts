// Shared GET /health reader for the page and the health route.
// Import this only from server code. It reads API_URL.

// The view the page already showed in Phase 0.
import type { HealthView } from "@/lib/types";

// Upstream helper.
import { callApi } from "@/lib/upstream";

// Read GET /health.
export async function loadHealth(): Promise<HealthView> {
  // Ask the FastAPI process.
  const upstream = await callApi("/health", { method: "GET" });
  // A failed call becomes the unreachable or error line.
  if (!upstream.ok) {
    // Match the Phase 0 wording when nothing answered.
    return {
      // Null when the process could not be reached.
      statusCode: upstream.statusCode,
      // unreachable has no HTTP code. Any other failure names the code in the status line.
      status: upstream.statusCode === null ? "unreachable" : "error",
      // Safe detail.
      detail: upstream.detail,
    };
  }
  // The success body.
  const body = upstream.body;
  // Keep the status only when it is the string the API promises.
  const status =
    typeof body === "object" &&
    body !== null &&
    "status" in body &&
    typeof (body as { status: unknown }).status === "string"
      ? (body as { status: string }).status
      : "unknown";
  // Success has no detail line.
  return { statusCode: upstream.statusCode, status, detail: "" };
}
