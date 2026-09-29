// Same-origin health proxy. The browser never calls the FastAPI port.

// JSON response helper.
import { NextResponse } from "next/server";

// Shared reader used by the server page as well.
import { loadHealth } from "@/lib/health";

// GET /api/health returns the Phase 0 status payload.
export async function GET(): Promise<NextResponse> {
  // Read GET /health on the server.
  const health = await loadHealth();
  // Always answer 200 so a down API is data, not a failed page fetch.
  return NextResponse.json(health);
}
