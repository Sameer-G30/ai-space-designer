"use client"; // The render button calls this origin.

// Pending flag and the last result.
import { useState } from "react";

// Reader.
import { parseVisualize } from "@/lib/parse-phase9";

// Shapes.
import type { FailureView, VisualizeBody } from "@/lib/types";

// Props.
type VisualizePanelProps = {
  // Design currently drawn. A what-if uses the new id.
  designId: string;
};

// One labelled PNG.
function PngFigure({ title, alt, data }: { title: string; alt: string; data: string }) {
  // A scene-graph map or the diffusion image.
  return (
    // Figure.
    <figure className="flex min-w-0 flex-col gap-2">
      {/* Caption. */}
      <figcaption className="text-sm font-semibold text-zinc-900">{title}</figcaption>
      {/* The image scales down on a narrow viewport. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={`data:image/png;base64,${data}`}
        alt={alt}
        className="h-auto w-full rounded-md border border-zinc-300 bg-white"
      />
    </figure>
  );
}

// Render maps, the generated image or the reason it was not generated, and the critic note.
export function VisualizePanel({ designId }: VisualizePanelProps) {
  // True while the route is in flight.
  const [pending, setPending] = useState(false);
  // HTTP failure.
  const [failure, setFailure] = useState<FailureView | null>(null);
  // A successful body.
  const [body, setBody] = useState<VisualizeBody | null>(null);
  // Ask for maps and, when weights are local, an image.
  const renderImage = async (): Promise<void> => {
    // Clear the previous result.
    setPending(true);
    // Clear the error.
    setFailure(null);
    // Clear the body so an old image cannot linger.
    setBody(null);
    // Call this origin.
    try {
      // POST. The design id is in the path.
      const response = await fetch(`/api/designs/${encodeURIComponent(designId)}/visualize`, {
        // Create.
        method: "POST",
        // JSON back.
        headers: { Accept: "application/json" },
        // Do not reuse an older image.
        cache: "no-store",
      });
      // Body, or null when it is not JSON.
      let payload: unknown = null;
      // Parse when possible.
      try {
        // Route JSON.
        payload = await response.json();
      } catch {
        // Leave it null.
        payload = null;
      }
      // Read it.
      const read = parseVisualize(payload, response.status);
      // 404 and other failures.
      if (read.kind === "failure") {
        // Show the status.
        setFailure(read.failure);
        // Stop.
        return;
      }
      // Draw the maps and the note.
      setBody(read.value);
    } catch (error) {
      // The browser could not reach this Next.js route.
      const detail = error instanceof Error ? error.message : "unknown error";
      // Show it.
      setFailure({ statusCode: null, detail });
    } finally {
      // Re-enable the button.
      setPending(false);
    }
  };
  // The panel.
  return (
    // Section.
    <section className="flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-4">
      {/* Heading. */}
      <h3 className="text-base font-semibold text-zinc-900">Generated image</h3>
      {/* What this button does. */}
      <p className="text-sm text-zinc-600">
        Depth and segmentation are rendered from the scene graph. A diffusion image is added only when Stable
        Diffusion 1.5 and ControlNet-depth weights are already on this machine. The critic note is advisory and
        does not change the design.
      </p>
      {/* Trigger. */}
      <button
        type="button"
        className="w-fit rounded-md bg-zinc-900 px-3 py-2 text-sm text-white disabled:opacity-50"
        disabled={pending}
        onClick={() => {
          // One request.
          void renderImage();
        }}
      >
        {pending ? "Rendering…" : "Render this design"}
      </button>
      {/* HTTP error. */}
      {failure ? (
        <p className="text-sm text-red-800" role="alert">
          {failure.statusCode === null ? failure.detail : `HTTP ${failure.statusCode}: ${failure.detail}`}
        </p>
      ) : null}
      {/* Result. */}
      {body ? (
        <div className="flex flex-col gap-4">
          {/* Diffusion image, or the reason it was not made. */}
          {body.image_status === "generated" && body.image_png_base64 ? (
            <PngFigure title="Generated image" alt="Inpainted room" data={body.image_png_base64} />
          ) : (
            <p className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
              {body.image_note}
            </p>
          )}
          {/* Scene-graph maps. These are not diffusion output. */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {/* Depth. */}
            <PngFigure
              title="Depth from the scene graph"
              alt="Depth map rendered from the scene graph"
              data={body.depth_png_base64}
            />
            {/* Segmentation. */}
            <PngFigure
              title="Segmentation from the scene graph"
              alt="Segmentation map rendered from the scene graph"
              data={body.segmentation_png_base64}
            />
          </div>
          {/* Lock score, only when an image exists. */}
          {body.unchanged_ssim !== null ? (
            <p className="text-sm text-zinc-700">Unchanged-region SSIM: {body.unchanged_ssim.toFixed(3)}</p>
          ) : null}
          {/* Consistency. */}
          <p className="text-sm text-zinc-700">
            Consistency: {body.consistency_status}. {body.consistency_note}
          </p>
          {/* Critic. Advisory even when it disagrees. */}
          <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3">
            <p className="text-sm font-semibold text-zinc-900">Critic note</p>
            <p className="mt-1 text-sm text-zinc-700">
              {body.critic_status}. {body.critic_note}
            </p>
            {/* Aesthetic lines. */}
            {body.critic_issues.length > 0 ? (
              <ul className="mt-2 list-disc pl-5 text-sm text-zinc-700">
                {body.critic_issues.map((issue) => (
                  <li key={issue}>{issue}</li>
                ))}
              </ul>
            ) : null}
            {/* Disagreements with the geometric checker. */}
            {body.disagreements.length > 0 ? (
              <ul className="mt-2 list-disc pl-5 text-sm text-zinc-700">
                {body.disagreements.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
