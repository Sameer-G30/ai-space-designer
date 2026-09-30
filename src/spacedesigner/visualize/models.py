"""Response models for POST /designs/{id}/visualize. Locked schemas are not edited."""

# Closed strings for image, mesh, and critic status.
from typing import Literal

# Field bounds the optional scores.
from pydantic import Field

# SchemaModel rejects unexpected keys.
from spacedesigner.schemas.base import SchemaModel


# One placed object and whether a cleaned GLB exists for it.
class MeshPlacement(SchemaModel):
    """Solver pose plus the mesh decision. A missing GLB stays a box."""

    # Design object id.
    object_id: str = Field(min_length=1)
    # Taxonomy class.
    category: str = Field(min_length=1)
    # Catalog id when the object id embeds one.
    item_id: str | None = None
    # glb when a cleaned file is on disk, otherwise box.
    kind: Literal["glb", "box"]
    # Objaverse uid when kind is glb.
    objaverse_uid: str | None = None
    # Floor centre [x, y] in metres.
    position: list[float] = Field(min_length=2, max_length=2)
    # Rotation in degrees.
    rotation: float
    # Local [length, width, height] in metres.
    dimensions: list[float] = Field(min_length=3, max_length=3)


# POST /designs/{id}/visualize. The design itself is not rewritten.
class VisualizeResponse(SchemaModel):
    """Maps, an optional diffusion image, and the advisory critic note."""

    # Design that was drawn.
    design_id: str = Field(min_length=1)
    # Always true. The critic and the consistency loop do not save a new design.
    design_unchanged: bool
    # One entry per design object.
    placements: list[MeshPlacement]
    # generated when Stable Diffusion returned an image, otherwise not_run.
    image_status: Literal["generated", "not_run"]
    # Why the image was or was not generated.
    image_note: str
    # Composited diffusion PNG, or null when image_status is not_run.
    image_png_base64: str | None = None
    # Depth rendered from the scene graph. Nearer pixels are brighter.
    depth_png_base64: str
    # Segmentation rendered from the scene graph.
    segmentation_png_base64: str
    # SSIM of pixels outside the inpaint mask. Null when no diffusion image exists.
    unchanged_ssim: float | None = None
    # matched, mismatched, or not_run when the detector did not run.
    consistency_status: Literal["matched", "mismatched", "not_run"]
    # What the loop did.
    consistency_note: str
    # How many diffusion attempts ran. Zero when diffusion did not run.
    consistency_attempts: int = Field(ge=0)
    # advisory when the VLM answered, otherwise not_run.
    critic_status: Literal["advisory", "not_run"]
    # Why the critic did or did not run. A note is never a rejection.
    critic_note: str
    # Aesthetic opinion, or null when the critic did not run.
    critic_plausible: bool | None = None
    # Aesthetic notes from the VLM. Empty when it did not run.
    critic_issues: list[str]
    # Findings from the existing Shapely checker. They are not new rules.
    deterministic_violations: list[str]
    # Hard kinds where the VLM and the Shapely checker disagree.
    disagreements: list[str]
    # Peak allocated MiB reported by a GPU worker, or null when none ran.
    peak_vram_mib: float | None = None
