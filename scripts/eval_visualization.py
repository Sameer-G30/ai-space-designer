"""Phase 9 checks: unchanged-region SSIM, and live diffusion, consistency, critic, and VRAM.

The mask-lock SSIM does not download weights and does not call a GPU.
Live Stable Diffusion, the detector consistency rate, the VLM, and peak VRAM run only when
the weights or the model are already installed. This script does not download or pull.

    uv run python scripts/eval_visualization.py
"""

# Annotations on Python 3.11.
from __future__ import annotations

# Mean.
import statistics

# Arrays for the painted edit.
import numpy as np

# Whether the vision model is already pulled. This does not pull it.
from spacedesigner.critic.vlm import vl_model_present

# Locked records.
from spacedesigner.schemas import Design, Requirement, SceneGraph

# Saved detector path. Importing it does not load the weights.
from spacedesigner.training.detector import BEST_WEIGHTS

# Real backend status. A missing package does not start a download.
from spacedesigner.visualize.backends import VisualizeBackends, diffusion_status

# Pixel lock.
from spacedesigner.visualize.raster import lock_unchanged, render_scene

# Orchestrator used only when the weights are already local.
from spacedesigner.visualize.service import visualize_design

# SSIM of the locked pixels.
from spacedesigner.visualize.ssim import ssim_unchanged

# How many scene-graph renders to lock and score.
ROOM_COUNT = 4

# Render size for the CPU lock check. Live diffusion, when installed, uses 512.
LOCK_SIZE = 128


# One room with a kept chair and a new desk, shifted per index.
def room(index: int) -> tuple[SceneGraph, Design]:
    """Return a high-confidence office. The desk is the changed region."""
    # Scene id.
    scene_id = f"viz-eval-{index}"
    # Keep the chair inside the room for every index.
    chair_x = 1.0 + 0.15 * index
    # Desk moves north as the index grows.
    desk_y = 2.6 + 0.2 * index
    # Validate the scene.
    scene = SceneGraph.model_validate(
        {
            "scene_id": scene_id,
            "version": 1,
            "room_type": "home_office",
            "dimensions": {
                "length": 5.5 + 0.3 * index,
                "width": 4.5 + 0.2 * index,
                "height": 2.8,
                "confidence": "high",
            },
            "openings": [{"type": "door", "wall": "south", "position": 0.5, "width": 0.9}],
            "objects": [
                {
                    "id": "kept-chair",
                    "type": "chair",
                    "position": [chair_x, 1.1],
                    "rotation": 0,
                    "dimensions": [0.5, 0.5, 0.9],
                    "movable": False,
                    "must_keep": True,
                    "confidence": "high",
                }
            ],
        }
    )
    # Weights the design schema requires. They are not optimized here.
    weights = {
        "layout": 1,
        "circulation": 1,
        "ergonomics": 1,
        "budget": 1,
        "aesthetics": 1,
        "sustainability": 1,
    }
    # The chair is copied. The desk is new, so it is the inpaint region.
    design = Design.model_validate(
        {
            "design_id": f"viz-eval-design-{index}",
            "scene_id": scene_id,
            "requirement_id": f"viz-eval-req-{index}",
            "weights": weights,
            "score": 0.5,
            "cost": 0,
            "objects": [
                scene.objects[0].model_dump(mode="json"),
                {
                    "id": "catalog::cat_desk_001::0",
                    "type": "desk",
                    "position": [2.4, desk_y],
                    "rotation": 0,
                    "dimensions": [1.2, 0.6, 0.75],
                    "movable": True,
                    "must_keep": False,
                    "confidence": "high",
                },
            ],
        }
    )
    # Scene and design.
    return scene, design


# Paint the editable pixels and lock the rest. Return SSIM and how many pixels changed.
def lock_score(index: int) -> tuple[float, int]:
    """Return (ssim, changed pixel count) for one render."""
    # Room.
    scene, design = room(index)
    # Maps.
    rendered = render_scene(scene, design, LOCK_SIZE)
    # A stand-in edit. Live diffusion is a separate check.
    edited = np.zeros_like(rendered.rgb)
    # Red.
    edited[:, :] = (255, 0, 0)
    # Lock.
    locked = lock_unchanged(rendered.rgb, edited, rendered.mask)
    # Unchanged mask.
    keep = rendered.mask == 0
    # Score. Identical locked pixels are 1.
    score = ssim_unchanged(rendered.rgb, locked, keep)
    # A missing score is a failed room, reported as a non-1 so the mean shows it.
    value = -1.0 if score is None else score
    # Pixels the edit was allowed to change.
    changed = int(np.count_nonzero(rendered.mask == 255))
    # Both numbers.
    return value, changed


# Reads visualize_design needs. This script does not write a design.
class _Store:
    """Hold the records for one live render."""

    # Save the triple.
    def __init__(self, scene: SceneGraph, requirement: Requirement, design: Design) -> None:
        """Index them."""
        # Scene.
        self.scene = scene
        # Requirement.
        self.requirement = requirement
        # Design.
        self.design = design

    # Scene.
    def get_scene(self, scene_id: str) -> SceneGraph | None:
        """Return the scene when the id matches."""
        # One room.
        return self.scene if scene_id == self.scene.scene_id else None

    # Requirement.
    def get_requirement(self, requirement_id: str) -> Requirement | None:
        """Return the requirement when the id matches."""
        # One requirement.
        return self.requirement if requirement_id == self.requirement.requirement_id else None

    # Design.
    def get_design(self, design_id: str) -> Design | None:
        """Return the design when the id matches."""
        # One design.
        return self.design if design_id == self.design.design_id else None


# Requirement wrapper so the geometric checker can run during a live pass.
def requirement_for(scene: SceneGraph, design: Design) -> Requirement:
    """Return a requirement that names the kept chair and the desk."""
    # Validate.
    return Requirement.model_validate(
        {
            "requirement_id": design.requirement_id,
            "scene_id": scene.scene_id,
            "raw_text": "",
            "budget_inr": 80000,
            "must_have": ["desk"],
            "must_keep_object_ids": ["kept-chair"],
            "occupant_count": 1,
            "style": "modern",
            "accessibility_required": False,
            "objective_weights": design.weights.model_dump(),
        }
    )


# Print the CPU lock check and the live checks that were not started.
def main() -> None:
    """Print one line per check. Live lines say not_run when weights are absent."""
    # Per-room scores.
    scores = []
    # Per-room changed-pixel counts.
    changed = []
    # Four rooms.
    for index in range(ROOM_COUNT):
        # One render.
        score, pixels = lock_score(index)
        # Keep them.
        scores.append(score)
        # Keep the count.
        changed.append(pixels)
    # Mean SSIM.
    mean = statistics.fmean(scores)
    # The lock check. This is not a diffusion SSIM.
    print(
        f"mask_lock_ssim n={ROOM_COUNT} size={LOCK_SIZE} "
        f"mean={mean:.6f} min={min(scores):.6f} changed_pixels_min={min(changed)}"
    )
    # Local weights and the diffusers import. No download.
    ready, reason = diffusion_status()
    # Live pass only when the weights are already installed.
    if not ready:
        # The reason names the missing package or weight folder.
        print(f"ssim_live not_run {reason}")
        # No generated image, so there is no consistency rate.
        print(f"consistency_live not_run {reason}")
        # No GPU allocation.
        print(f"vram not_run {reason}")
    else:
        # One room. The worker unloads the chat model before loading diffusion.
        scene, design = room(0)
        # Store.
        store = _Store(scene, requirement_for(scene, design), design)
        # Real backends. local_files_only, so this still does not download.
        result = visualize_design(
            store,
            design.design_id,
            backends=VisualizeBackends(),
            max_attempts=2,
        )
        # Diffusion SSIM, or not_run if the worker declined.
        if result.unchanged_ssim is None:
            # The worker note.
            print(f"ssim_live not_run {result.image_note}")
        else:
            # One image.
            print(f"ssim_live n=1 value={result.unchanged_ssim:.6f}")
        # Consistency.
        print(f"consistency_live {result.consistency_status} {result.consistency_note}")
        # Peak, if the worker reported one.
        if result.peak_vram_mib is None:
            # Not measured.
            print("vram not_run worker did not report a peak")
        else:
            # MiB.
            print(f"vram_peak_mib {result.peak_vram_mib:.1f}")
        # Critic lines from the same call.
        print(f"critic_live {result.critic_status} {result.critic_note}")
        # Disagreement count for this one image.
        print(f"critic_disagreement_lines {len(result.disagreements)}")
    # Critic presence when diffusion did not run. The live branch prints its own critic line.
    if not ready:
        # Presence only. This does not pull.
        if vl_model_present():
            # Pulled, but there is no generated image to send.
            print("critic_live not_run no generated image")
        else:
            # Not pulled.
            print("critic_live not_run qwen2.5vl:7b is not pulled")
        # No rows.
        print("critic_disagreement_rows 0")
    # Detector file, for the record. It was not loaded.
    if BEST_WEIGHTS.is_file():
        # Present.
        print(f"detector_weights present {BEST_WEIGHTS}")
    else:
        # Absent.
        print("detector_weights missing")


# Run.
if __name__ == "__main__":
    # Print the lines.
    main()
