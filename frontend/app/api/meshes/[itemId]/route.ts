// Stream one cleaned Objaverse GLB. A catalog item with no mesh is 404, and the view draws a box.

// Read the sidecar and the GLB. Both live in the repo, not in this Next.js folder.
import { readFile } from "node:fs/promises";

// Join paths without accepting a caller-supplied directory.
import path from "node:path";

// 200 bytes or 404 JSON.
import { NextResponse } from "next/server";

// Provenance record. Only the uid is used.
type ProvenanceRecord = {
  // Present on mesh-backed items.
  objaverse_uid?: string;
};

// Cached sidecar so every chair does not re-read the JSON.
let provenance: Record<string, ProvenanceRecord> | null = null;

// Repo root. `next dev` is started in frontend/, so the datasets live one level up.
function repoRoot(): string {
  // Current working directory.
  const cwd = process.cwd();
  // The documented dev command runs inside frontend/.
  if (path.basename(cwd) === "frontend") {
    // Parent is the repo.
    return path.resolve(cwd, "..");
  }
  // Already at the repo, for a process started there.
  return cwd;
}

// Load the tracked provenance sidecar once.
async function loadProvenance(): Promise<Record<string, ProvenanceRecord>> {
  // Use the cache.
  if (provenance !== null) {
    // Already read.
    return provenance;
  }
  // Tracked JSON from Phase 2b.
  const file = path.join(repoRoot(), "datasets", "metadata", "cleaning", "furniture_catalog_provenance.json");
  // Read text.
  const text = await readFile(file, "utf8");
  // Parse.
  provenance = JSON.parse(text) as Record<string, ProvenanceRecord>;
  // Cache it.
  return provenance;
}

// Route params.
type Context = {
  // The catalog item id.
  params: Promise<{ itemId: string }>;
};

// GET /api/meshes/[itemId] returns model/gltf-binary or 404.
export async function GET(_request: Request, context: Context): Promise<NextResponse> {
  // Catalog id from the path.
  const { itemId } = await context.params;
  // Reject anything that is not a catalog token, so the id cannot be a path.
  if (!/^[A-Za-z0-9_]+$/.test(itemId)) {
    // No file.
    return NextResponse.json({ ok: false, detail: "no mesh" }, { status: 404 });
  }
  // Sidecar. A missing file is a 404, not a 500 the canvas cannot explain.
  let records: Record<string, ProvenanceRecord>;
  // Read it.
  try {
    // Cached after the first call.
    records = await loadProvenance();
  } catch {
    // The view will draw a box.
    return NextResponse.json({ ok: false, detail: "no mesh" }, { status: 404 });
  }
  // This item's source record.
  const record = records[itemId];
  // SUN-tier items have no uid.
  const uid = record?.objaverse_uid;
  // Missing or not a hex uid.
  if (uid === undefined || !/^[a-f0-9]+$/i.test(uid)) {
    // Box.
    return NextResponse.json({ ok: false, detail: "no mesh" }, { status: 404 });
  }
  // Cleaned export. The uid was checked, so this cannot leave the folder.
  const file = path.join(repoRoot(), "datasets", "processed", "objaverse", `${uid}.glb`);
  // Bytes.
  let bytes: Buffer;
  // A deleted GLB stays a box.
  try {
    // Read the file.
    bytes = await readFile(file);
  } catch {
    // Box.
    return NextResponse.json({ ok: false, detail: "no mesh" }, { status: 404 });
  }
  // Binary GLB. Copy into a Uint8Array so the body type is a web buffer.
  const body = new Uint8Array(bytes);
  // The loader reads this as a GLB.
  return new NextResponse(body, {
    // Found.
    status: 200,
    // Headers.
    headers: {
      // GLB content type.
      "Content-Type": "model/gltf-binary",
      // Meshes do not change during a session.
      "Cache-Control": "public, max-age=86400",
    },
  });
}
