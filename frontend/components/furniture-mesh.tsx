"use client"; // GLB loading uses the browser.

// Report which kind is showing, and drop the load when the object changes.
import { useEffect, useState } from "react";

// Group returned by the fitter.
import type { Group } from "three";

// Box geometry shared with the room shell.
import { furnitureBox } from "@/lib/geometry";

// Fit a clone onto the solver footprint.
import { fitFurniture } from "@/lib/mesh-fit";

// Catalog id and the cached loader.
import { catalogItemId, loadFurnitureGltf } from "@/lib/meshes";

// One placed object.
import type { SceneObject } from "@/lib/types";

// What the caption should say.
export type MeshKind = "box" | "glb";

// Props.
type FurnitureMeshProps = {
  // Placed object.
  obj: SceneObject;
  // Plan colour, used when the object stays a box.
  color: string;
  // Tell the caption whether this object is a mesh or a box.
  onKind: (objectId: string, kind: MeshKind) => void;
};

// One piece of furniture. A box is shown until a GLB is actually in the scene.
export function FurnitureMesh({ obj, color, onKind }: FurnitureMeshProps) {
  // Solver box, used for the fallback and for the kept-object wire frame.
  const box = furnitureBox(obj);
  // Fitted clone. Null until a GLB has loaded, so the box stays up until then.
  const [fitted, setFitted] = useState<Group | null>(null);
  // Catalog id, or null for a kept object.
  const itemId = catalogItemId(obj.id);
  // A mesh replaces the box only after the clone exists.
  const kind: MeshKind = itemId !== null && fitted !== null ? "glb" : "box";
  // Load when the catalog id or the pose changes.
  useEffect(() => {
    // A kept object has no cleaned mesh. kind stays "box" because fitted stays null.
    if (itemId === null) {
      // No request.
      return;
    }
    // Ignore a response that arrives after this object was replaced.
    let cancel = false;
    // Cached load. State updates run in the callback, not in the effect body.
    void loadFurnitureGltf(itemId).then((gltf) => {
      // This effect was cleaned up.
      if (cancel) {
        // Do not set state.
        return;
      }
      // 404 stays a box.
      if (gltf === null) {
        // Caption.
        onKind(obj.id, "box");
        // Stop.
        return;
      }
      // Clone and scale onto this object's footprint.
      const placed = fitFurniture(gltf.scene, obj);
      // Degenerate bounds stay a box.
      if (placed === null) {
        // Caption.
        onKind(obj.id, "box");
        // Stop.
        return;
      }
      // Show the mesh. The box underneath is removed in the render below.
      setFitted(placed);
      // Caption.
      onKind(obj.id, "glb");
    });
    // Cancel the state update when the object changes.
    return () => {
      // Ignore the in-flight result.
      cancel = true;
    };
  }, [itemId, obj, onKind]);
  // Skip a non-positive box.
  if (box.size[0] <= 0 || box.size[1] <= 0 || box.size[2] <= 0) {
    // Nothing to draw.
    return null;
  }
  // Mesh in place of the box, plus a wire frame when the object is kept.
  return (
    // One object.
    <group>
      {/* GLB at the solver position. The box is not drawn once this exists. */}
      {kind === "glb" && fitted !== null ? <primitive object={fitted} /> : null}
      {/* Box until the mesh is shown, and for every item with no cleaned file. */}
      {kind === "box" ? (
        <mesh position={box.position}>
          {/* Solver size. */}
          <boxGeometry args={box.size} />
          {/* Same colour as the plan. */}
          <meshStandardMaterial color={color} />
        </mesh>
      ) : null}
      {/* Kept objects stay outlined so they remain visible on a mesh or a box. */}
      {obj.must_keep ? (
        <mesh position={box.position}>
          {/* Same size as the solver box. */}
          <boxGeometry args={box.size} />
          {/* Wire paint. */}
          <meshBasicMaterial color="#111111" wireframe />
        </mesh>
      ) : null}
    </group>
  );
}
