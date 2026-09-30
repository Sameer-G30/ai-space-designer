// Same-origin proxy for POST /designs/{id}/visualize.

// JSON response helper.
import { NextResponse } from "next/server";

// Upstream call and the error envelope.
import { callApi, failureResponse } from "@/lib/upstream";

// Diffusion, when weights exist, can take longer than a parse. The not-run path is fast.
const VISUALIZE_TIMEOUT_MS = 300000;

// Route params in Next.js 16.
type Context = {
  // The design id.
  params: Promise<{ id: string }>;
};

// POST /api/designs/[id]/visualize renders maps and, when weights are local, an image.
export async function POST(_request: Request, context: Context): Promise<NextResponse> {
  // Design id from the path.
  const { id } = await context.params;
  // Forward the POST. There is no JSON body.
  const upstream = await callApi(`/designs/${encodeURIComponent(id)}/visualize`, {
    // Create the visualization for the stored design.
    method: "POST",
    // Long enough for one local diffusion pass. A missing weight file returns quickly.
    timeoutMs: VISUALIZE_TIMEOUT_MS,
  });
  // 404 keeps its status.
  if (!upstream.ok) {
    // The panel shows statusCode and detail.
    return failureResponse(upstream.statusCode, upstream.detail);
  }
  // Wrap the visualize body.
  return NextResponse.json({ ok: true, result: upstream.body });
}
