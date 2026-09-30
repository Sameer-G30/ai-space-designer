// Server-side calls to FastAPI. The browser never sees API_URL.

// NextResponse builds the JSON the browser reads.
import { NextResponse } from "next/server";

// Safe error text.
import { formatApiDetail } from "@/lib/api-error";

// One completed upstream call.
export type Upstream =
  // HTTP success and a parsed JSON body, or null when the body was empty.
  | { ok: true; statusCode: number; body: unknown }
  // HTTP or network failure with a safe detail string.
  | { ok: false; statusCode: number | null; detail: string };

// Origin of the FastAPI process.
export function apiOrigin(): string {
  // Use the server env value, or the port this project already documents.
  return process.env.API_URL ?? "http://127.0.0.1:8001";
}

// Call one FastAPI path. json is sent only when the caller provides it.
export async function callApi(
  path: string,
  init: {
    method: string;
    json?: unknown;
    // Raw bytes and their content type, used by the photo route.
    raw?: { bytes: ArrayBuffer; contentType: string };
    timeoutMs?: number;
  },
): Promise<Upstream> {
  // Build the upstream URL on the server.
  const url = `${apiOrigin()}${path}`;
  // Headers for every call.
  const headers: Record<string, string> = {
    // Ask for JSON.
    Accept: "application/json",
  };
  // Add a content type only when there is a body.
  if (init.json !== undefined) {
    // The body is JSON.
    headers["Content-Type"] = "application/json";
  }
  // A raw body carries its own content type.
  if (init.raw !== undefined) {
    // Image bytes.
    headers["Content-Type"] = init.raw.contentType;
  }
  // Network failures have no status code.
  try {
    // Send the request and do not cache it.
    const response = await fetch(url, {
      // GET or POST.
      method: init.method,
      // Headers built above.
      headers,
      // Omit the body for GET.
      body: init.raw !== undefined
        ? init.raw.bytes
        : init.json === undefined
          ? undefined
          : JSON.stringify(init.json),
      // Always ask the upstream again.
      cache: "no-store",
      // Optional deadline. Other routes keep the previous unlimited wait.
      signal: init.timeoutMs === undefined ? undefined : AbortSignal.timeout(init.timeoutMs),
    });
    // Read text first so a non-JSON error still has a status.
    const text = await response.text();
    // Parsed JSON, or null when the body is empty or not JSON.
    let parsed: unknown = null;
    // Parse only when there is text.
    if (text !== "") {
      // A non-JSON body stays null and is not shown.
      try {
        // Parse the upstream JSON.
        parsed = JSON.parse(text) as unknown;
      } catch {
        // Leave parsed null.
        parsed = null;
      }
    }
    // Success returns the parsed body to the route.
    if (response.ok) {
      // Include the status so the health view can print it.
      return { ok: true, statusCode: response.status, body: parsed };
    }
    // Failure keeps a formatted detail and the status.
    return {
      // Not a success.
      ok: false,
      // Upstream status.
      statusCode: response.status,
      // Safe sentence.
      detail: formatApiDetail(parsed, response.status),
    };
  } catch (error) {
    // The message is a network error, not a database URL.
    const message = error instanceof Error ? error.message : "unknown error";
    // Report that the API process could not be reached.
    return { ok: false, statusCode: null, detail: `API unreachable: ${message}` };
  }
}

// JSON error for the browser. 404 and 422 keep their status codes.
export function failureResponse(statusCode: number | null, detail: string): NextResponse {
  // Use the upstream status when it is an error code. Otherwise use 503.
  const status = statusCode !== null && statusCode >= 400 && statusCode <= 599 ? statusCode : 503;
  // The page reads ok, statusCode, and detail.
  return NextResponse.json({ ok: false, statusCode, detail }, { status });
}
