// Same-origin proxy for POST /designs/optimize.

// JSON response helper.
import { NextResponse } from "next/server";

// Upstream call and the error envelope.
import { callApi, failureResponse } from "@/lib/upstream";

// POST /api/designs/optimize runs the Pareto solve.
export async function POST(request: Request): Promise<NextResponse> {
  // Parsed JSON, or a failure when the body is not JSON.
  let payload: unknown;
  // Parse the browser body.
  try {
    // The form sends scene_id and requirement.
    payload = await request.json();
  } catch {
    // Tell the page the body was not JSON.
    return failureResponse(400, "request body must be JSON");
  }
  // Forward the body unchanged.
  const upstream = await callApi("/designs/optimize", { method: "POST", json: payload });
  // 404, 422, and other upstream errors keep their status.
  if (!upstream.ok) {
    // The page shows statusCode and detail and draws no design.
    return failureResponse(upstream.statusCode, upstream.detail);
  }
  // A 200 body may still be feasible:false. The page branches on that flag.
  return NextResponse.json({ ok: true, result: upstream.body });
}
