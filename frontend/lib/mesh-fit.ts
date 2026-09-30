// Place a cleaned GLB on the solver footprint.
// Floor x is world X, floor y is world Z, height is world Y.
// The mesh is scaled to the object's local length, width, and height, then yawed.

// Three types used to measure and wrap the mesh.
import { Box3, Group, Vector3, type Object3D } from "three";

// The placed object.
import type { SceneObject } from "@/lib/types";

// Build a group whose origin is the footprint centre on the floor, in world space.
export function fitFurniture(source: Object3D, obj: SceneObject): Group | null {
  // A private copy. The cached GLB is shared by every item of this catalog id.
  const clone = source.clone(true);
  // World matrices for the bounding box.
  clone.updateWorldMatrix(true, true);
  // Bounds of the clone as loaded.
  const bounds = new Box3().setFromObject(clone);
  // Size.
  const size = new Vector3();
  // Fill size.
  bounds.getSize(size);
  // A flat or empty mesh cannot be scaled onto the solver box.
  if (size.x < 1e-6 || size.y < 1e-6 || size.z < 1e-6) {
    // The caller draws a box instead.
    return null;
  }
  // Centre of the loaded bounds.
  const center = new Vector3();
  // Fill centre.
  bounds.getCenter(center);
  // Move the footprint centre to the origin and the bottom to y = 0.
  const holder = new Group();
  // The clone keeps its internal transforms.
  holder.add(clone);
  // Centering translation, in mesh space, before the scale.
  holder.position.set(-center.x, -bounds.min.y, -center.z);
  // Scale group. Scale is applied before its yaw, which is the mesh-axis scale.
  const scaled = new Group();
  // The cleaned export's longer floor edge is not always on X.
  const longOnZ = size.z > size.x;
  // Local length is dimensions[0]. Local width is dimensions[1]. Height is dimensions[2].
  if (longOnZ) {
    // Scale mesh X to the width and mesh Z to the length, then turn Z onto local X.
    scaled.scale.set(obj.dimensions[1] / size.x, obj.dimensions[2] / size.y, obj.dimensions[0] / size.z);
    // +90 degrees yaw maps mesh +Z to local +X.
    scaled.rotation.y = Math.PI / 2;
  } else {
    // The long edge is already on X.
    scaled.scale.set(obj.dimensions[0] / size.x, obj.dimensions[2] / size.y, obj.dimensions[1] / size.z);
  }
  // Holder is scaled in mesh axes.
  scaled.add(holder);
  // Solver yaw and position. Position is the footprint centre on the floor.
  const placed = new Group();
  // Floor x, floor height 0, floor y as z.
  placed.position.set(obj.position[0], 0, obj.position[1]);
  // Solver rotation about Y. 90 degrees swaps the footprint the way the plan does.
  placed.rotation.y = (obj.rotation * Math.PI) / 180;
  // Scaled mesh under the solver yaw.
  placed.add(scaled);
  // Ready for the canvas.
  return placed;
}
