"use client"; // WebGL runs in the browser. This file is loaded with server rendering off.

// Canvas and the camera hook.
import { Canvas, useThree } from "@react-three/fiber";

// Mount the orbit controls after the canvas exists.
import { useEffect } from "react";

// Camera class used to update the projection.
import { PerspectiveCamera } from "three";

// Orbit controls ship with three. This is not a separate package.
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

// Frame note and the shared palette.
import { BOX_NOTE, planColor } from "@/lib/constants";

// Boxes in the solver frame.
import { furnitureBox, roomShell } from "@/lib/geometry";

// Scene and object shapes.
import type { SceneGraph, SceneObject } from "@/lib/types";

// Props. The room comes from the stored scene. The boxes come from the selected design.
type BoxViewProps = {
  // Room size and openings.
  scene: SceneGraph;
  // Placed objects for the selected design.
  objects: SceneObject[];
};

// Average footprint centre, or the middle of the room when nothing is placed.
function focusPoint(length: number, width: number, objects: SceneObject[]): { x: number; z: number } {
  // Empty designs look at the room centre.
  if (objects.length === 0) {
    // Room centre.
    return { x: length / 2, z: width / 2 };
  }
  // Mean centre x.
  const x = objects.reduce((sum, obj) => sum + obj.position[0], 0) / objects.length;
  // Mean centre y, which is world z.
  const z = objects.reduce((sum, obj) => sum + obj.position[1], 0) / objects.length;
  // The cluster the camera frames.
  return { x, z };
}

// Point the camera down at the placed furniture and let the user orbit it.
function CameraRig({
  length,
  width,
  objects,
}: {
  // Room length.
  length: number;
  // Room width.
  width: number;
  // Selected design objects. The camera recentres when they change.
  objects: SceneObject[];
}) {
  // Active camera.
  const camera = useThree((state) => state.camera);
  // Renderer, needed for the pointer controls.
  const gl = useThree((state) => state.gl);
  // Where the furniture sits.
  const focus = focusPoint(length, width, objects);
  // Reset the camera when the furniture or the room changes.
  useEffect(() => {
    // The canvas element. Offscreen canvases are not used here.
    const element = gl.domElement;
    // OrbitControls needs an HTML element.
    if (!(element instanceof HTMLElement)) {
      // Leave the default camera.
      return;
    }
    // Stand above and a little north-east of the furniture so the south wall is not in the way.
    camera.position.set(focus.x + Math.max(length * 0.12, 0.6), Math.max(length, width) * 0.55, focus.z + Math.max(width * 0.12, 0.6));
    // Look down at the furniture.
    camera.lookAt(focus.x, 0.3, focus.z);
    // Refresh the projection after moving a perspective camera.
    if (camera instanceof PerspectiveCamera) {
      // Apply the new position.
      camera.updateProjectionMatrix();
    }
    // Dragging orbits the camera. It does not move furniture.
    const controls = new OrbitControls(camera, element);
    // Orbit around the furniture.
    controls.target.set(focus.x, 0.3, focus.z);
    // Apply the target.
    controls.update();
    // Drop the controls when this view is replaced.
    return () => {
      // Release the pointer listeners.
      controls.dispose();
    };
  }, [camera, gl, length, width, focus.x, focus.z]);
  // The rig adds no mesh of its own.
  return null;
}

// Box view at the solver coordinates.
export default function BoxView({ scene, objects }: BoxViewProps) {
  // Room length.
  const length = scene.dimensions.length;
  // Room width.
  const width = scene.dimensions.width;
  // Room height.
  const height = scene.dimensions.height;
  // Walls and opening marks.
  const shell = roomShell(length, width, height, scene.openings);
  // The canvas fills the sized parent.
  return (
    // Section wrapper.
    <section className="flex flex-col gap-3">
      {/* Heading. */}
      <h3 className="text-base font-semibold text-zinc-900">Box view</h3>
      {/* Frame reminder. */}
      <p className="text-sm text-zinc-600">{BOX_NOTE}</p>
      {/* Sized parent. The canvas needs a height. */}
      <div className="h-80 w-full overflow-hidden rounded-lg border border-zinc-300 bg-zinc-200 sm:h-96">
        {/* WebGL scene. */}
        <Canvas
          camera={{
            // Field of view.
            fov: 45,
            // Near plane.
            near: 0.05,
            // Far plane.
            far: 200,
            // Initial position, before the rig looks at the furniture.
            position: [length * 0.5, Math.max(length, width) * 0.55, width * 0.5],
          }}
        >
          {/* Camera rig. */}
          <CameraRig length={length} width={width} objects={objects} />
          {/* Soft fill. */}
          <ambientLight intensity={0.75} />
          {/* A light from above the north-east. */}
          <directionalLight position={[length, height * 3, width]} intensity={0.9} />
          {/* Floor. A hair below y = 0 so it does not flicker against the boxes. */}
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[length / 2, -0.01, width / 2]}>
            {/* Floor size is the room size. */}
            <planeGeometry args={[length, width]} />
            {/* Neutral floor. */}
            <meshStandardMaterial color="#f5f5f4" />
          </mesh>
          {/* Solid wall pieces. Openings are gaps. */}
          {shell.walls.map((box, index) => (
            <mesh key={`wall-${index}`} position={box.position}>
              {/* Wall size. */}
              <boxGeometry args={box.size} />
              {/* Wall paint. */}
              <meshStandardMaterial color="#d6d3d1" />
            </mesh>
          ))}
          {/* Door and window marks sitting in those gaps. */}
          {shell.marks.map((box, index) => (
            <mesh key={`mark-${index}`} position={box.position}>
              {/* Mark size. */}
              <boxGeometry args={box.size} />
              {/* Red door, blue window. */}
              <meshStandardMaterial color={box.kind === "window" ? "#4cc9f0" : "#9b2226"} />
            </mesh>
          ))}
          {/* Furniture boxes. */}
          {objects.map((obj, index) => {
            // Solver box.
            const box = furnitureBox(obj);
            // Skip a non-positive size rather than handing it to three.
            if (box.size[0] <= 0 || box.size[1] <= 0 || box.size[2] <= 0) {
              // No mesh.
              return null;
            }
            // Colour shared with the plan.
            const color = planColor(index);
            // Solid box, plus a wire frame when the object is kept.
            return (
              <group key={`${obj.id}-${index}`}>
                {/* Solid box. */}
                <mesh position={box.position}>
                  {/* Size. */}
                  <boxGeometry args={box.size} />
                  {/* Paint. */}
                  <meshStandardMaterial color={color} />
                </mesh>
                {/* Kept objects get a dark wire frame so they stay visible. */}
                {obj.must_keep ? (
                  <mesh position={box.position}>
                    {/* Same size. */}
                    <boxGeometry args={box.size} />
                    {/* Wire paint. */}
                    <meshBasicMaterial color="#111111" wireframe />
                  </mesh>
                ) : null}
              </group>
            );
          })}
        </Canvas>
      </div>
      {/* Drag hint. */}
      <p className="text-sm text-zinc-600">Drag to orbit the camera. Furniture stays where the solver put it.</p>
    </section>
  );
}
