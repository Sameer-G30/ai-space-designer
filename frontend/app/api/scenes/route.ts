// Same-origin proxy for POST /scenes.

// JSON response helper.
import { NextResponse } from "next/server";

// Upstream call and the error envelope.
import { callApi, failureResponse } from "@/lib/upstream";

// POST /api/scenes stores one scene graph.
export async function POST(request: Request): Promise<NextResponse> {
  // Parsed JSON, or a failure when the body is not JSON.
  let payload: unknown;
  // Parse the browser body.
  try {
    // The form sends a SceneGraph.
    payload = await request.json();
  } catch {
    // Tell the page the body was not JSON.
    return failureResponse(400, "request body must be JSON");
  }
  // Forward the body unchanged so the API remains the validator.
  const upstream = await callApi("/scenes", { method: "POST", json: payload });
  // 422 and other upstream errors keep their status.
  if (!upstream.ok) {
    // The page shows statusCode and detail.
    return failureResponse(upstream.statusCode, upstream.detail);
  }
  // Wrap the stored scene. The page draws from this echo.
  return NextResponse.json({ ok: true, scene: upstream.body });
}
