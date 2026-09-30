// Same-origin proxy for GET /designs/{id}/versions.

// JSON response helper.
import { NextResponse } from "next/server";

// Upstream call and the error envelope.
import { callApi, failureResponse } from "@/lib/upstream";

// Route params in Next.js 16.
type Context = {
  // The design id.
  params: Promise<{ id: string }>;
};

// GET /api/designs/[id]/versions reads the append-only version rows.
export async function GET(_request: Request, context: Context): Promise<NextResponse> {
  // Design id from the path.
  const { id } = await context.params;
  // Forward the GET. The first read also stores version 1.
  const upstream = await callApi(`/designs/${encodeURIComponent(id)}/versions`, {
    // Read.
    method: "GET",
  });
  // 404 keeps its status.
  if (!upstream.ok) {
    // The panel shows statusCode and detail.
    return failureResponse(upstream.statusCode, upstream.detail);
  }
  // Wrap the version list.
  return NextResponse.json({ ok: true, result: upstream.body });
}
