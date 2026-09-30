// Same-origin proxy for GET /designs/{id}/explanation.

// JSON response helper.
import { NextResponse } from "next/server";

// Upstream call and the error envelope.
import { callApi, failureResponse } from "@/lib/upstream";

// A 7B rephrase can take as long as a requirement parse.
const EXPLAIN_TIMEOUT_MS = 180000;

// Route params in Next.js 16.
type Context = {
  // The design id.
  params: Promise<{ id: string }>;
};

// GET /api/designs/[id]/explanation reads or writes the explanation.
export async function GET(_request: Request, context: Context): Promise<NextResponse> {
  // Design id from the path.
  const { id } = await context.params;
  // Forward the GET. The model may need the full timeout.
  const upstream = await callApi(`/designs/${encodeURIComponent(id)}/explanation`, {
    // Read.
    method: "GET",
    // Same budget as the sentence parser.
    timeoutMs: EXPLAIN_TIMEOUT_MS,
  });
  // 404 and 422 keep their status.
  if (!upstream.ok) {
    // The panel shows statusCode and detail.
    return failureResponse(upstream.statusCode, upstream.detail);
  }
  // Wrap the explanation.
  return NextResponse.json({ ok: true, result: upstream.body });
}
