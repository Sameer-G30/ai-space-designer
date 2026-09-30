// Catalog ids and GLB loading for the 3D view. A missing file stays a box.

// Parsed GLB type.
import type { GLTF } from "three/examples/jsm/loaders/GLTFLoader.js";

// Loader that ships with three. This is not a new package.
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

// One cached load per catalog item.
const cache = new Map<string, Promise<GLTF | null>>();

// catalog::{item_id}::{index} is the solver's object id. Anything else is a kept object.
export function catalogItemId(objectId: string): string | null {
  // Three fields.
  const parts = objectId.split("::");
  // Kept objects do not use this shape.
  if (parts.length !== 3 || parts[0] !== "catalog" || parts[1] === "" || !/^\d+$/.test(parts[2] ?? "")) {
    // No mesh lookup.
    return null;
  }
  // The catalog id.
  return parts[1] ?? null;
}

// Load one GLB. A 404 resolves to null so the caller draws a box.
export function loadFurnitureGltf(itemId: string): Promise<GLTF | null> {
  // Reuse a load that is already in flight or finished.
  const existing = cache.get(itemId);
  // Same item, same promise.
  if (existing !== undefined) {
    // Do not fetch twice.
    return existing;
  }
  // Start a load.
  const pending = new Promise<GLTF | null>((resolve) => {
    // One loader per item. The cache shares the result.
    const loader = new GLTFLoader();
    // Same-origin route. It streams the cleaned GLB or returns 404.
    loader.load(
      // Item id is a catalog token, not a path.
      `/api/meshes/${encodeURIComponent(itemId)}`,
      // Parsed scene.
      (gltf) => {
        // Keep it.
        resolve(gltf);
      },
      // Progress is unused.
      undefined,
      // 404 and network errors become a box.
      () => {
        // No mesh.
        resolve(null);
      },
    );
  });
  // Remember it before it finishes so a second chair does not double-fetch.
  cache.set(itemId, pending);
  // The caller clones the scene per instance.
  return pending;
}
