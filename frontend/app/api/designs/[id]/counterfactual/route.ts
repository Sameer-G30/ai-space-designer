// Same-origin proxy for POST /designs/{id}/counterfactual.

// JSON response helper.
import { NextResponse } from "next/server";

// Upstream call and the error envelope.
import { callApi, failureResponse } from "@/lib/upstream";

// A warm-started solve is short. Keep a bound so a hung API does not spin forever.
const COUNTERFACTUAL_TIMEOUT_MS = 60000;

// Route params in Next.js 16.
type Context = {
  // The design id.
  params: Promise<{ id: string }>;
};

// POST /api/designs/[id]/counterfactual runs one what-if.
export async function POST(request: Request, context: Context): Promise<NextResponse> {
  // Design id from the path.
  const { id } = await context.params;
  // Parsed JSON, or a failure when the body is not JSON.
  let payload: unknown;
  // Parse the browser body.
  try {
    // Budget, room edges, or occupants.
    payload = await request.json();
  } catch {
    // Tell the page the body was not JSON.
    return failureResponse(400, "request body must be JSON");
  }
  // Forward the body.
  const upstream = await callApi(`/designs/${encodeURIComponent(id)}/counterfactual`, {
    // Create.
    method: "POST",
    // The what-if fields.
    json: payload,
    // Bound the wait.
    timeoutMs: COUNTERFACTUAL_TIMEOUT_MS,
  });
  // 404 and 422 keep their status. A feasible:false body is HTTP 200.
  if (!upstream.ok) {
    // The panel shows statusCode and detail and does not replace the plan.
    return failureResponse(upstream.statusCode, upstream.detail);
  }
  // Wrap the what-if. The page branches on feasible.
  return NextResponse.json({ ok: true, result: upstream.body });
}
