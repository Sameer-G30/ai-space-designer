"""Phase 9 maps, pixel lock, mesh lookup, and visualize route. No weights and no GPU."""

# Base64 images in the response.
import base64

# In-memory PNG decode.
import io

# Arrays for the painted edit.
import numpy as np

# Route client.
from fastapi.testclient import TestClient

# Decode a response PNG.
from PIL import Image

# Application and the store override.
from spacedesigner.api.main import app
from spacedesigner.api.store import get_design_store

# Real Stage 1 so the route test stores a feasible design.
from spacedesigner.optimizer import optimize

# Scorer override. CLIP is not loaded.
from spacedesigner.optimizer.catalog import load_catalog
from spacedesigner.recommend.scoring import load_style_scorer
from spacedesigner.recommend.service import get_style_scorer

# Locked records.
from spacedesigner.schemas import Design, Requirement, SceneGraph

# Catalog id parser and GLB lookup.
from spacedesigner.visualize.assets import catalog_item_id, glb_for_item

# Backend records the fakes return.
from spacedesigner.visualize.backends import (
    CriticOutput,
    DetectOutput,
    InpaintOutput,
    get_visualize_backends,
)

# Matcher.
from spacedesigner.visualize.consistency import Detection, ExpectedBox, match_detections

# Pixel lock and the scene-graph renderer.
from spacedesigner.visualize.raster import lock_unchanged, render_scene

# Orchestrator.
from spacedesigner.visualize.service import visualize_design

# SSIM.
from spacedesigner.visualize.ssim import ssim_unchanged

# Memory store that can explain, which is also enough to visualize.
from tests.explain.test_routes import ExplainMemory

# Fixtures.
from tests.phase3_samples import sample_catalog, sample_requirement, sample_scene
from tests.recommend.fakes import FakeEmbedder


# One home office with a kept chair and a new desk.
def _office() -> tuple[SceneGraph, Design, Requirement]:
    """Return a scene, a design, and a requirement the maps can render."""
    # Room.
    scene = SceneGraph.model_validate(
        {
            "scene_id": "viz-room",
            "version": 1,
            "room_type": "home_office",
            "dimensions": {"length": 6.0, "width": 5.0, "height": 2.8, "confidence": "high"},
            "openings": [{"type": "door", "wall": "south", "position": 0.4, "width": 0.9}],
            "objects": [
                {
                    "id": "kept-chair",
                    "type": "chair",
                    "position": [1.0, 1.2],
                    "rotation": 0,
                    "dimensions": [0.5, 0.5, 0.9],
                    "movable": False,
                    "must_keep": True,
                    "confidence": "high",
                }
            ],
        }
    )
    # The desk is new. The chair is copied.
    design = Design.model_validate(
        {
            "design_id": "viz-design",
            "scene_id": "viz-room",
            "requirement_id": "viz-req",
            "weights": {
                "layout": 1,
                "circulation": 1,
                "ergonomics": 1,
                "budget": 1,
                "aesthetics": 1,
                "sustainability": 1,
            },
            "score": 0.5,
            "cost": 0,
            "objects": [
                scene.objects[0].model_dump(mode="json"),
                {
                    "id": "catalog::cat_desk_001::0",
                    "type": "desk",
                    "position": [3.0, 3.2],
                    "rotation": 0,
                    "dimensions": [1.2, 0.6, 0.75],
                    "movable": True,
                    "must_keep": False,
                    "confidence": "high",
                },
            ],
        }
    )
    # Requirement stored beside the design. The checker may report the zero cost.
    requirement = Requirement.model_validate(
        {
            "requirement_id": "viz-req",
            "scene_id": "viz-room",
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
    # The three records.
    return scene, design, requirement


# In-memory store with the three reads visualize_design uses.
class _Store:
    """Hold one scene, one requirement, and one design."""

    # Save the triple.
    def __init__(self, scene: SceneGraph, requirement: Requirement, design: Design) -> None:
        """Index the three records."""
        # Scene.
        self.scene = scene
        # Requirement.
        self.requirement = requirement
        # Design.
        self.design = design

    # Scene read.
    def get_scene(self, scene_id: str) -> SceneGraph | None:
        """Return the scene when the id matches."""
        # One room.
        return self.scene if scene_id == self.scene.scene_id else None

    # Requirement read.
    def get_requirement(self, requirement_id: str) -> Requirement | None:
        """Return the requirement when the id matches."""
        # One requirement.
        return self.requirement if requirement_id == self.requirement.requirement_id else None

    # Design read.
    def get_design(self, design_id: str) -> Design | None:
        """Return the design when the id matches."""
        # One design.
        return self.design if design_id == self.design.design_id else None


# Fake workers. They do not import diffusers or ultralytics.
class _FakeBackends:
    """Paint the mask red, return no boxes, and flag overlap."""

    # Count inpaint calls.
    def __init__(self) -> None:
        """Start at zero calls."""
        # How many times inpaint ran.
        self.calls = 0

    # Paint editable pixels red. The service locks the rest.
    def inpaint(self, base, mask, depth, prompt, seed):
        """Return a generated image without a model."""
        # Count the attempt.
        self.calls += 1
        # Copy the base.
        painted = np.array(base)
        # Editable pixels.
        editable = np.array(mask) > 127
        # Red stands in for a diffusion edit.
        painted[editable] = (255, 0, 0)
        # A tiny fake peak so the field is populated without a GPU.
        return InpaintOutput("generated", "fake inpaint", Image.fromarray(painted), 1.0)

    # No boxes, so the loop reports a mismatch.
    def detect(self, image):
        """Return an empty detection list."""
        # The detector did run, in the sense the hook was called. No GPU.
        return DetectOutput("ok", "fake detector", [], None)

    # Flag a hard issue the fixture's geometry does not have to share.
    def critic(self, image_base64, summary):
        """Return an advisory overlap flag."""
        # Advisory. The service must not rewrite the design because of this.
        return CriticOutput(
            "advisory",
            "advisory only",
            False,
            ["looks cramped"],
            {"overlap": True, "clearance": False, "budget": False, "missing": False},
        )


# The new desk is in the mask and the kept chair is not.
def test_mask_covers_only_changed_furniture() -> None:
    """Depth and segmentation exist, and the kept chair stays out of the mask."""
    # Fixture.
    scene, design, _requirement = _office()
    # Small render. 64 is a multiple of 8.
    rendered = render_scene(scene, design, 64)
    # Something was drawn.
    assert int(rendered.depth_u8.max()) > 0
    # Segmentation is an RGB image of the same size.
    assert rendered.segmentation.shape == (64, 64, 3)
    # Find the two projections.
    by_id = {item.object_id: item for item in rendered.projections}
    # The desk is new.
    assert by_id["catalog::cat_desk_001::0"].changed is True
    # The chair was copied from the scene.
    assert by_id["kept-chair"].changed is False
    # The desk faces the camera and wins some pixels.
    assert by_id["catalog::cat_desk_001::0"].visible_pixels > 0
    # Desk label is the second furniture object, base 10 plus index 1.
    desk_label = 11
    # Those pixels are editable.
    assert np.any((rendered.labels == desk_label) & (rendered.mask == 255))
    # Chair pixels are locked.
    assert not np.any((rendered.labels == 10) & (rendered.mask == 255))


# A piece near the south wall used to fall below a level camera.
def test_furniture_near_the_south_wall_is_visible() -> None:
    """The camera looks at the furniture, so a south-wall desk still has pixels."""
    # Wide room. The desk sits close to the south edge.
    scene = SceneGraph.model_validate(
        {
            "scene_id": "south-desk",
            "version": 1,
            "room_type": "home_office",
            "dimensions": {"length": 6.0, "width": 6.0, "height": 2.8, "confidence": "high"},
            "openings": [],
            "objects": [],
        }
    )
    # One new desk.
    design = Design.model_validate(
        {
            "design_id": "south-desk-design",
            "scene_id": "south-desk",
            "requirement_id": "south-desk-req",
            "weights": {
                "layout": 1,
                "circulation": 1,
                "ergonomics": 1,
                "budget": 1,
                "aesthetics": 1,
                "sustainability": 1,
            },
            "score": 0.5,
            "cost": 0,
            "objects": [
                {
                    "id": "catalog::cat_desk_001::0",
                    "type": "desk",
                    "position": [3.0, 1.0],
                    "rotation": 0,
                    "dimensions": [1.2, 0.6, 0.75],
                    "movable": True,
                    "must_keep": False,
                    "confidence": "high",
                }
            ],
        }
    )
    # Render.
    rendered = render_scene(scene, design, 128)
    # The desk is in the picture.
    desk = next(item for item in rendered.projections if item.object_id.startswith("catalog::"))
    # Enough pixels to be a real view, not a sliver.
    assert desk.visible_pixels > 40
    # Those pixels are the inpaint region.
    assert np.any(rendered.mask == 255)


# A painted edit does not change the locked pixels, so their SSIM stays at 1.
def test_unchanged_region_ssim_is_one_after_lock() -> None:
    """Composite the mask and measure SSIM outside it."""
    # Fixture.
    scene, design, _requirement = _office()
    # Render.
    rendered = render_scene(scene, design, 64)
    # An edit that replaces every pixel.
    edited = np.zeros_like(rendered.rgb)
    # Red.
    edited[:, :] = (255, 0, 0)
    # Lock.
    locked = lock_unchanged(rendered.rgb, edited, rendered.mask)
    # Locked pixels match the base byte for byte.
    keep = rendered.mask == 0
    # The region is not empty: walls and the chair remain.
    assert np.any(keep)
    # Byte match.
    assert np.array_equal(rendered.rgb[keep], locked[keep])
    # SSIM on that region.
    score = ssim_unchanged(rendered.rgb, locked, keep)
    # Identical locked pixels score 1.
    assert score == 1.0
    # Flip one locked pixel. The score must leave 1 so the check is not a constant.
    broken = locked.copy()
    # First locked pixel.
    row, col = np.argwhere(keep)[0]
    # A different colour.
    broken[row, col] = (0, 255, 0)
    # The lock failed on that pixel.
    assert ssim_unchanged(rendered.rgb, broken, keep) < 1.0
    # The editable region actually changed, so the check is not an untouched image.
    assert np.any(rendered.mask == 255)
    # Those pixels are the edit.
    assert np.all(locked[rendered.mask == 255] == (255, 0, 0))


# Class and rough position.
def test_consistency_match_and_mismatch() -> None:
    """A same-class overlap matches. A wrong class does not."""
    # One expected desk.
    expected = [ExpectedBox("desk-1", "desk", (10.0, 10.0, 40.0, 40.0))]
    # A detection that covers it.
    hit = [Detection("desk", 0.9, (12.0, 12.0, 38.0, 36.0))]
    # Match.
    assert match_detections(expected, hit).matched is True
    # Wrong class.
    miss = [Detection("bed", 0.9, (12.0, 12.0, 38.0, 36.0))]
    # Not a match, and the bed is extra.
    result = match_detections(expected, miss)
    # Failed.
    assert result.matched is False
    # The desk was not paired.
    assert result.matched_count == 0
    # The bed remains.
    assert result.extra_count == 1


# A blank picture is not a match when the design placed furniture.
def test_unseen_furniture_is_not_a_match() -> None:
    """Zero projected objects is a failure when the design is not empty."""
    # The camera missed every piece.
    missed = match_detections([], [], placed_count=2)
    # Not a success.
    assert missed.matched is False
    # The note says why.
    assert missed.note == "camera did not see the placed furniture"
    # An empty design still matches an empty detection list.
    assert match_detections([], []).matched is True


# Solver object ids.
def test_catalog_item_id_parser() -> None:
    """catalog::{item}::{index} parses. A kept id does not."""
    # Stage 1 shape.
    assert catalog_item_id("catalog::cat_desk_001::0") == "cat_desk_001"
    # Kept object.
    assert catalog_item_id("kept-chair") is None


# Cleaned mesh lookup. The GLB is gitignored, so skip when it was not generated.
def test_mesh_lookup_uses_cleaned_objaverse_files() -> None:
    """A mesh-backed desk resolves. A SUN-tier desk stays a box."""
    # Mesh item from the tracked provenance.
    found = glb_for_item("cat_desk_001")
    # The cleaned file is part of the Phase 2b export on this machine.
    if found is None:
        # Another checkout may not have the gitignored GLBs.
        assert glb_for_item("cat_desk_015") is None
        # The mesh case is skipped by returning. The SUN case still holds above when both miss.
        return
    # Uid and path.
    uid, path = found
    # The file name is the uid.
    assert path.name == f"{uid}.glb"
    # It is a real file.
    assert path.is_file()
    # SUN-tier desks have no uid.
    assert glb_for_item("cat_desk_015") is None


# The service composites, logs a disagreement, and does not rewrite the design.
def test_visualize_locks_pixels_and_does_not_rewrite(tmp_path) -> None:
    """Fake diffusion and an advisory overlap flag leave the design as it was."""
    # Records.
    scene, design, requirement = _office()
    # Store.
    store = _Store(scene, requirement, design)
    # Fakes.
    backends = _FakeBackends()
    # Snapshot.
    before = design.model_dump(mode="json")
    # One attempt so a mismatch does not loop.
    result = visualize_design(
        store,
        design.design_id,
        backends=backends,
        image_size=64,
        max_attempts=1,
        log_path=tmp_path / "disagreements.jsonl",
    )
    # The fake ran once.
    assert backends.calls == 1
    # An image was produced by the fake, not by a download.
    assert result.image_status == "generated"
    # The design flag stays true.
    assert result.design_unchanged is True
    # The stored record is the same object contents.
    assert design.model_dump(mode="json") == before
    # SSIM of the lock.
    assert result.unchanged_ssim == 1.0
    # The empty detector does not match the projected furniture.
    assert result.consistency_status == "mismatched"
    # The VLM flag is advisory.
    assert result.critic_status == "advisory"
    # It disagreed with the geometric checker on overlap, whatever else the checker said.
    assert any(line.startswith("vlm flagged overlap") for line in result.disagreements)
    # The log was written.
    assert (tmp_path / "disagreements.jsonl").is_file()
    # The mesh decision for the desk is glb when the cleaned file exists.
    kinds = {row.object_id: row.kind for row in result.placements}
    # The kept chair is never a catalog mesh.
    assert kinds["kept-chair"] == "box"


# Weights that are not installed produce a reason and still return the maps.
class _MissingBackends:
    """Stand in for a machine with no diffusers weights and no vision model."""

    # No image.
    def inpaint(self, base, mask, depth, prompt, seed):
        """Report that diffusion was not started."""
        # The note matches the real backend's missing-package sentence.
        return InpaintOutput(
            "not_run",
            "diffusion not run: diffusers is not installed in .venv-train",
            None,
            None,
        )

    # Unused when there is no image. Present so the service can call it.
    def detect(self, image):
        """Report that the detector was not started."""
        # No boxes.
        return DetectOutput(
            "not_run",
            "consistency not run: detector weights are missing",
            [],
            None,
        )

    # Unused when there is no image.
    def critic(self, image_base64, summary):
        """Report that the vision model was not pulled."""
        # No advice.
        return CriticOutput("not_run", "critic not run: qwen2.5vl:7b is not pulled", None, [], {})


# The page can show a reason when diffusion weights are absent.
def test_missing_weights_return_maps_and_a_reason(tmp_path) -> None:
    """No download, no design change, depth still present."""
    # Records.
    scene, design, requirement = _office()
    # Store.
    store = _Store(scene, requirement, design)
    # Run.
    result = visualize_design(
        store,
        design.design_id,
        backends=_MissingBackends(),
        image_size=64,
        max_attempts=1,
        log_path=tmp_path / "none.jsonl",
    )
    # Not generated.
    assert result.image_status == "not_run"
    # The reason names the missing package.
    assert "diffusers" in result.image_note
    # No diffusion PNG.
    assert result.image_png_base64 is None
    # The scene-graph depth is still there.
    assert result.depth_png_base64
    # Consistency did not invent a rate.
    assert result.consistency_status == "not_run"
    # The critic was not called, because there is no generated image.
    assert result.critic_status == "not_run"
    # No disagreement row without a critic answer.
    assert result.disagreements == []
    # The log was not created.
    assert not (tmp_path / "none.jsonl").exists()
    # The design flag.
    assert result.design_unchanged is True


# Unknown design.
def test_visualize_route_unknown_design_is_404() -> None:
    """A missing design is 404 and does not start a worker."""
    # Empty store.
    store = ExplainMemory()
    # Override.
    app.dependency_overrides[get_design_store] = lambda: store
    # Always clear.
    try:
        # Client.
        with TestClient(app) as client:
            # No such design.
            response = client.post("/designs/missing/visualize")
    # Clear even on failure.
    finally:
        # Drop overrides.
        app.dependency_overrides.clear()
    # Not found.
    assert response.status_code == 404


# A stored design can be visualized with fakes. The optimize route is unchanged.
def test_visualize_route_returns_maps(tmp_path) -> None:
    """Solve one sample room, then visualize it without weights."""
    # Store that records designs.
    store = ExplainMemory()
    # Database override.
    app.dependency_overrides[get_design_store] = lambda: store
    # Deterministic style scores.
    scorer = load_style_scorer(load_catalog(), FakeEmbedder(), tmp_path / "c.npz", ("modern",))
    # Scorer override.
    app.dependency_overrides[get_style_scorer] = lambda: scorer
    # Fakes.
    backends = _FakeBackends()
    # Backend override.
    app.dependency_overrides[get_visualize_backends] = lambda: backends
    # Clear afterwards.
    try:
        # Client.
        with TestClient(app) as client:
            # Store the scene.
            scene_response = client.post("/scenes", json=sample_scene().model_dump(mode="json"))
            # Accepted.
            assert scene_response.status_code == 200
            # Solve. This is the existing route.
            optimize_response = client.post(
                "/designs/optimize",
                json={
                    "scene_id": "scene-phase3",
                    "requirement": sample_requirement().model_dump(mode="json"),
                },
            )
            # The sample room is feasible.
            assert optimize_response.status_code == 200
            # Body.
            body = optimize_response.json()
            # Need a design id.
            assert body["feasible"] is True
            # First point.
            design_id = body["points"][0]["design"]["design_id"]
            # How many designs were stored.
            stored = len(store.designs)
            # Visualize.
            visual = client.post(f"/designs/{design_id}/visualize")
    # Clear overrides.
    finally:
        # Drop them.
        app.dependency_overrides.clear()
    # Accepted.
    assert visual.status_code == 200
    # Payload.
    payload = visual.json()
    # Maps are always present.
    assert payload["depth_png_base64"]
    # Segmentation too.
    assert payload["segmentation_png_base64"]
    # The fake generated an image. The note says so.
    assert payload["image_status"] == "generated"
    # The design was not replaced by another id.
    assert payload["design_id"] == design_id
    # No extra design row.
    assert len(store.designs) == stored
    # The PNG decodes.
    raw = base64.b64decode(payload["depth_png_base64"])
    # A real image.
    assert Image.open(io.BytesIO(raw)).size[0] > 0
    # Each placement agrees with the cleaned-file lookup.
    for row in payload["placements"]:
        # Only the two kinds.
        assert row["kind"] in {"glb", "box"}
        # Catalog objects follow the on-disk mesh.
        item_id = catalog_item_id(row["object_id"])
        # A kept object has no catalog id and stays a box.
        if item_id is None:
            # Box.
            assert row["kind"] == "box"
            # Next object.
            continue
        # File present or not.
        if glb_for_item(item_id) is None:
            # No cleaned mesh.
            assert row["kind"] == "box"
        # A cleaned file is a glb placement.
        else:
            # The uid is set.
            assert row["kind"] == "glb"
            # Non-empty uid.
            assert row["objaverse_uid"]


# optimize() is imported so a future edit does not drop the solver from this module's checks.
def test_sample_solver_still_feasible() -> None:
    """The Phase 3 sample still solves. Phase 9 does not change that function."""
    # Solve the sample.
    result = optimize(sample_scene(), sample_requirement(), sample_catalog())
    # Feasible.
    assert result.feasible
