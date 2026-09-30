// Same-origin proxy for POST /requirements. The browser does not call FastAPI.

// JSON response helper.
import { NextResponse } from "next/server";

// Upstream call and the error envelope.
import { callApi, failureResponse } from "@/lib/upstream";

// A 7B JSON answer can take longer than a solve.
const PARSER_TIMEOUT_MS = 180000;

// POST /api/requirements parses one sentence.
export async function POST(request: Request): Promise<NextResponse> {
  // Parsed JSON, or a failure when the body is not JSON.
  let payload: unknown;
  // Parse the browser body.
  try {
    // The form sends scene_id, raw_text, requirement_id, and objects.
    payload = await request.json();
  } catch {
    // Tell the page the body was not JSON.
    return failureResponse(400, "request body must be JSON");
  }
  // Forward the body. The API validates it. Give the model time to answer.
  const upstream = await callApi("/requirements", {
    method: "POST",
    json: payload,
    timeoutMs: PARSER_TIMEOUT_MS,
  });
  // 422 and other upstream errors keep their status so the form can show the parser error.
  if (!upstream.ok) {
    // The form shows statusCode and detail and does not fill fields.
    return failureResponse(upstream.statusCode, upstream.detail);
  }
  // Wrap the parse. The form reads result.requirement and result.retrieved.
  return NextResponse.json({ ok: true, result: upstream.body });
}
