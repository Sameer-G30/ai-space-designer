"""Build the visualize response. The stored design is not rewritten."""

# Annotations on Python 3.11.
from __future__ import annotations

# Default disagreement log.
from pathlib import Path

# A small read protocol avoids importing the API package (that import loads the app).
from typing import Protocol

# Mask composite and SSIM use arrays.
import numpy as np

# Resize a diffusion image back to the render size.
from PIL import Image

# The live Shapely checker. It is not weakened here.
from spacedesigner.critic.deterministic import audit_design

# Log disagreements. This does not change the checker.
from spacedesigner.critic.disagreement import append_disagreement, disagreement_lines

# Repository root for the gitignored log.
from spacedesigner.data.common import repo_root

# BOM lines the checker recomputes from.
from spacedesigner.optimizer.bom import build_bom

# Tracked catalog. Embeddings are not written.
from spacedesigner.optimizer.catalog import load_catalog

# BomLine type comes from the optimizer models via build_bom.
from spacedesigner.optimizer.models import BomLine

# Locked records.
from spacedesigner.schemas import Design, Requirement, SceneGraph

# Catalog id and GLB lookup.
from spacedesigner.visualize.assets import catalog_item_id, glb_for_item

# Real workers, replaced in tests.
from spacedesigner.visualize.backends import CriticOutput, InpaintOutput, VisualizeBackends

# Expected boxes for the matcher.
from spacedesigner.visualize.consistency import ExpectedBox, match_detections

# Missing rows.
from spacedesigner.visualize.errors import VisualizeError

# PNG fields.
from spacedesigner.visualize.images import png_base64

# Response models.
from spacedesigner.visualize.models import MeshPlacement, VisualizeResponse

# Scene-graph maps and the pixel lock.
from spacedesigner.visualize.raster import lock_unchanged, render_scene

# Unchanged-region SSIM.
from spacedesigner.visualize.ssim import ssim_unchanged

# First diffusion seed. Later attempts add 1.
SEED = 20260930

# How many times the consistency loop may generate.
MAX_ATTEMPTS = 3

# Render size passed to SD 1.5. It is a multiple of 8.
IMAGE_SIZE = 512


# The three reads this route needs. Defined here so importing the service does not load FastAPI.
class DesignReader(Protocol):
    """Read a stored design, its scene, and its requirement."""

    # Scene.
    def get_scene(self, scene_id: str) -> SceneGraph | None:
        """Return a scene."""

    # Design.
    def get_design(self, design_id: str) -> Design | None:
        """Return a design."""

    # Requirement.
    def get_requirement(self, requirement_id: str) -> Requirement | None:
        """Return a requirement."""


# Default gitignored log. Tests pass their own path.
def default_log_path() -> Path:
    """Return datasets/processed/phase9/disagreements.jsonl."""
    # processed/ is gitignored.
    return repo_root() / "datasets" / "processed" / "phase9" / "disagreements.jsonl"


# Rebuild the bill from catalog ids embedded in the object ids.
def bom_from_design(design: Design) -> list[BomLine]:
    """Return BOM lines for catalog objects. Kept objects are not purchased rows."""
    # Catalog by id. This reads the tracked JSONL and does not write embeddings.
    by_id = {item.item_id: item for item in load_catalog()}
    # Selected rows, one per placed catalog object.
    selected = []
    # Every placed object.
    for obj in design.objects:
        # Parse catalog::{item}::{index}.
        item_id = catalog_item_id(obj.id)
        # A kept object has no catalog id.
        if item_id is None:
            # Not a purchased line.
            continue
        # Row.
        item = by_id.get(item_id)
        # An unknown id cannot be priced. The checker will see the cost gap.
        if item is None:
            # Skip it.
            continue
        # One purchased unit.
        selected.append(item)
    # Same aggregator the optimizer uses.
    return build_bom(selected)


# Placements for the response and for a client that wants the mesh decision.
def placements_for(design: Design) -> list[MeshPlacement]:
    """Mark each object glb or box. A missing cleaned file stays a box."""
    # Rows in design order.
    rows: list[MeshPlacement] = []
    # One object.
    for obj in design.objects:
        # Catalog id, or None.
        item_id = catalog_item_id(obj.id)
        # GLB only when the cleaned file exists.
        found = glb_for_item(item_id) if item_id else None
        # Uid when found.
        uid = found[0] if found else None
        # Box unless the file is on disk.
        kind = "glb" if found else "box"
        # One placement. Coordinates stay in the solver frame.
        rows.append(
            MeshPlacement(
                object_id=obj.id,
                category=obj.type,
                item_id=item_id,
                kind=kind,
                objaverse_uid=uid,
                position=list(obj.position),
                rotation=obj.rotation,
                dimensions=list(obj.dimensions),
            )
        )
    # All objects.
    return rows


# Prompt from the room type and the categories the optimizer changed.
def _prompt(scene: SceneGraph, changed_categories: list[str]) -> str:
    """Return a short photorealistic prompt. It does not name a new model."""
    # Unique changed classes, stable order.
    kinds = ", ".join(sorted(set(changed_categories))) or "furniture"
    # Room phrase.
    room = scene.room_type.replace("_", " ")
    # One sentence.
    return f"photorealistic {room}, {kinds}, natural indoor light, no text"


# Summary the critic may read. It includes the geometric findings so a disagreement is informed.
def _summary(scene: SceneGraph, design: Design, violations: list[str]) -> str:
    """Return a short text summary. It is not a new design."""
    # Categories in order.
    categories = ", ".join(obj.type for obj in design.objects) or "none"
    # Checker text.
    findings = "; ".join(violations) if violations else "none"
    # One paragraph.
    return f"room {scene.room_type}, objects {categories}, geometric checker: {findings}"


# Visible projected objects become the expected boxes.
def _expected(rendered, image_size: int) -> list[ExpectedBox]:
    """Drop objects that won too few pixels to be a fair detector target."""
    # Scale the minimum with the image so a 64 px test and a 512 px render both work.
    minimum = max(1, (image_size * image_size) // 40000)
    # Expected boxes.
    boxes: list[ExpectedBox] = []
    # One projection.
    for item in rendered.projections:
        # Hidden objects are not required to be detected.
        if item.visible_pixels < minimum:
            # Skip.
            continue
        # Matcher record.
        boxes.append(ExpectedBox(item.object_id, item.category, item.xyxy))
    # What the detector should find.
    return boxes


# Highest peak, ignoring None.
def _max_peak(current: float | None, extra: float | None) -> float | None:
    """Return the larger peak, or whichever one exists."""
    # Nothing new.
    if extra is None:
        # Keep the current value.
        return current
    # First measurement.
    if current is None:
        # Use it.
        return extra
    # Larger of the two stages. They do not run at the same time.
    return max(current, extra)


# Orchestrate maps, optional diffusion, the consistency loop, and the advisory critic.
def visualize_design(
    store: DesignReader,
    design_id: str,
    backends: VisualizeBackends | None = None,
    image_size: int = IMAGE_SIZE,
    max_attempts: int = MAX_ATTEMPTS,
    log_path: Path | None = None,
) -> VisualizeResponse:
    """Return maps and notes. This function does not call save_design."""
    # Real workers unless a test passed doubles.
    backend = backends if backends is not None else VisualizeBackends()
    # Load the design.
    design = store.get_design(design_id)
    # Unknown id.
    if design is None:
        # 404.
        raise VisualizeError(404, "design not found")
    # Load the scene the design names.
    scene = store.get_scene(design.scene_id)
    # The scene row should exist for every stored design.
    if scene is None:
        # 404.
        raise VisualizeError(404, "scene not found")
    # Load the requirement the checker needs.
    requirement = store.get_requirement(design.requirement_id)
    # A design without its requirement cannot be audited.
    if requirement is None:
        # 404.
        raise VisualizeError(404, "requirement not found")
    # Snapshot so a later edit would fail the test below.
    before = design.model_dump(mode="json")
    # Mesh decisions.
    placements = placements_for(design)
    # Depth, segmentation, colour, and mask from the scene graph.
    rendered = render_scene(scene, design, image_size)
    # Independent checker. Its result is logged, not used to drop the design.
    violations = audit_design(scene, requirement, design, bom_from_design(design))
    # Depth PNG.
    depth_b64 = png_base64(rendered.depth_u8)
    # Segmentation PNG.
    seg_b64 = png_base64(rendered.segmentation)
    # PIL views of the maps.
    base = Image.fromarray(rendered.rgb)
    # Single-channel mask.
    mask_image = Image.fromarray(rendered.mask)
    # 3-channel depth for ControlNet.
    depth_image = Image.fromarray(rendered.depth_u8).convert("RGB")
    # Categories the mask is allowed to change.
    changed = [item.category for item in rendered.projections if item.changed]
    # Prompt.
    prompt = _prompt(scene, changed)
    # Image fields start as not run.
    image_status = "not_run"
    # Filled when the first attempt returns.
    image_note = "diffusion did not run"
    # Composited RGB, when an attempt generated one.
    final: np.ndarray | None = None
    # SSIM, only after a composite.
    score: float | None = None
    # Consistency starts as not run.
    consistency_status = "not_run"
    # Note.
    consistency_note = "consistency not run: no generated image"
    # Attempts that produced an image.
    attempts = 0
    # Peak across attempts and the detector. The models are not resident together.
    peak: float | None = None
    # Seeds for the regeneration loop.
    seeds = [SEED + offset for offset in range(max_attempts)]
    # Each attempt is a separate process when the real backend is used.
    for attempt, seed in enumerate(seeds, start=1):
        # One inpaint. A not_run backend returns immediately and does not download.
        output: InpaintOutput = backend.inpaint(base, mask_image, depth_image, prompt, seed)
        # Remember the peak even when generation failed.
        peak = _max_peak(peak, output.peak_vram_mib)
        # No image.
        if output.status != "generated" or output.image is None:
            # Keep a prior image if a later attempt failed.
            if final is None:
                # Nothing to show.
                image_status = "not_run"
                # The backend's reason, including a missing download.
                image_note = output.note
                # No consistency loop without an image.
                consistency_note = "consistency not run: no generated image"
            # Stop. Do not keep spawning.
            break
        # This attempt counts.
        attempts = attempt
        # Match the render size. The lock restores pixels outside the mask.
        resized = output.image.convert("RGB").resize(
            (image_size, image_size),
            Image.Resampling.BILINEAR,
        )
        # Array for the composite.
        edited = resized
        # Pixel-lock walls and unchanged furniture.
        locked = lock_unchanged(rendered.rgb, np.asarray(edited), rendered.mask)
        # Keep it.
        final = locked
        # An image exists even if consistency later fails.
        image_status = "generated"
        # Worker note.
        image_note = output.note
        # SSIM on pixels the mask left alone.
        score = ssim_unchanged(rendered.rgb, locked, rendered.mask == 0)
        # Detector on the composited image. It is a separate process from diffusion.
        detected = backend.detect(Image.fromarray(locked))
        # Detector peak is not simultaneous with diffusion.
        peak = _max_peak(peak, detected.peak_vram_mib)
        # Weights missing or the worker failed.
        if detected.status != "ok":
            # Report that the rate was not measured.
            consistency_status = "not_run"
            # Reason.
            consistency_note = detected.note
            # Do not regenerate without a comparison.
            break
        # Compare class and rough position.
        result = match_detections(
            _expected(rendered, image_size),
            detected.detections,
            placed_count=len(design.objects),
        )
        # Agreement.
        if result.matched:
            # Stop.
            consistency_status = "matched"
            # Counts.
            consistency_note = result.note
            # Done.
            break
        # Mismatch. Another seed is allowed until the cap.
        consistency_status = "mismatched"
        # Counts so far.
        consistency_note = result.note
        # Last allowed attempt.
        if attempt == len(seeds):
            # Say the cap was reached.
            consistency_note = f"{result.note}; regeneration limit reached"
            # Stop.
            break
    # Critic fields.
    critic_status = "not_run"
    # Default reason when there is no image.
    critic_note = "critic not run: no generated image"
    # Opinion.
    plausible: bool | None = None
    # Aesthetic notes.
    issues: list[str] = []
    # Hard disagreements.
    disagreements: list[str] = []
    # The critic sees only a generated image, and only as advice.
    if final is not None and image_status == "generated":
        # Base64 of the composited image.
        image_b64 = png_base64(final)
        # Advisory call. A missing model returns not_run and does not pull.
        critic: CriticOutput = backend.critic(image_b64, _summary(scene, design, violations))
        # Status.
        critic_status = critic.status
        # Note.
        critic_note = critic.note
        # Opinion, possibly None.
        plausible = critic.plausible
        # Notes.
        issues = list(critic.issues)
        # Compare only when the VLM actually answered.
        if critic.status == "advisory":
            # Lines. Empty means the two checkers agree.
            disagreements = disagreement_lines(violations, critic.flags)
            # Append a row. Tests can point this at a tmp directory.
            append_disagreement(
                log_path if log_path is not None else default_log_path(),
                {
                    "design_id": design.design_id,
                    "deterministic_violations": violations,
                    "vlm_flags": critic.flags,
                    "vlm_issues": issues,
                    "disagreements": disagreements,
                },
            )
    # The snapshot must still match. This function has no write path.
    if design.model_dump(mode="json") != before:
        # A bug, not a user-facing rejection of the room.
        raise VisualizeError(500, "visualize changed the stored design")
    # Response. design_unchanged is true on every successful return.
    return VisualizeResponse(
        design_id=design.design_id,
        design_unchanged=True,
        placements=placements,
        image_status=image_status,
        image_note=image_note,
        image_png_base64=None if final is None else png_base64(final),
        depth_png_base64=depth_b64,
        segmentation_png_base64=seg_b64,
        unchanged_ssim=score,
        consistency_status=consistency_status,
        consistency_note=consistency_note,
        consistency_attempts=attempts,
        critic_status=critic_status,
        critic_note=critic_note,
        critic_plausible=plausible,
        critic_issues=issues,
        deterministic_violations=violations,
        disagreements=disagreements,
        peak_vram_mib=peak,
    )
