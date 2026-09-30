// Same-origin proxy for POST /scenes/photo. The browser sends the image bytes and two numbers.

// JSON response helper.
import { NextResponse } from "next/server";

// Upstream call and the error envelope.
import { callApi, failureResponse } from "@/lib/upstream";

// The vision pipeline can take a minute on first load, so wait up to five minutes.
const PHOTO_TIMEOUT_MS = 300_000;

// POST /api/scenes/photo?scene_id=..&known_length_m=..&known_axis=..
export async function POST(request: Request): Promise<NextResponse> {
  // Query values typed in the form.
  const incoming = new URL(request.url).searchParams;
  // Forward only the three known keys.
  const outgoing = new URLSearchParams();
  // Scene id is required by the API.
  for (const key of ["scene_id", "known_length_m", "known_axis"]) {
    // Copy a value only when the form sent one.
    const value = incoming.get(key);
    // Skip empty values so the API uses its defaults.
    if (value !== null && value !== "") {
      // Copy it.
      outgoing.set(key, value);
    }
  }
  // Raw image bytes.
  const bytes = await request.arrayBuffer();
  // Forward them unchanged so the API does the privacy pass and the validation.
  const upstream = await callApi(`/scenes/photo?${outgoing.toString()}`, {
    method: "POST",
    raw: { bytes, contentType: request.headers.get("content-type") ?? "application/octet-stream" },
    timeoutMs: PHOTO_TIMEOUT_MS,
  });
  // 422 and other upstream errors keep their status.
  if (!upstream.ok) {
    // The page shows the detail.
    return failureResponse(upstream.statusCode, upstream.detail);
  }
  // Wrap the estimate. The page reads it defensively.
  return NextResponse.json({ ok: true, photo: upstream.body });
}
