"""Shared sample documents for schema round-trip tests."""

# datetime builds the timezone-aware version timestamp.
from datetime import datetime, timezone

# Contract models under test.
from spacedesigner.schemas.catalog import CatalogItem
from spacedesigner.schemas.design import Design
from spacedesigner.schemas.requirement import ObjectiveWeights, Requirement
from spacedesigner.schemas.scene import SceneGraph
from spacedesigner.schemas.trace import OptimizerTrace
from spacedesigner.schemas.version import DesignVersion

# Scene graph copied from the example in blueprint section 11.
SCENE_GRAPH_JSON = """
{
  "scene_id": "room_0091",
  "version": 3,
  "room_type": "gaming_room",
  "dimensions": {"length": 4.5, "width": 3.8, "height": 2.8, "confidence": "medium"},
  "openings": [{"type": "window", "wall": "north", "position": 2.1, "width": 1.2}],
  "objects": [
    {"id": "obj_01", "type": "desk", "position": [2.1, 1.2], "rotation": 0,
     "dimensions": [1.4, 0.7, 0.75], "movable": true, "must_keep": false, "confidence": "high"}
  ]
}
"""


# Build the six objective weights used by more than one sample.
def sample_weights() -> ObjectiveWeights:
    """Return one valid weight vector."""
    # Every term is inside the unit interval.
    return ObjectiveWeights(
        layout=0.2,
        circulation=0.2,
        ergonomics=0.15,
        budget=0.2,
        aesthetics=0.15,
        sustainability=0.1,
    )


# Build a requirement that points at the blueprint scene example.
def sample_requirement() -> Requirement:
    """Return one valid requirement."""
    # Fill every field the requirement contract requires.
    return Requirement(
        requirement_id="req_01",
        scene_id="room_0091",
        raw_text="A desk for two, modern, under 50000 rupees.",
        budget_inr=50000,
        must_have=["desk", "chair"],
        must_keep_object_ids=["obj_01"],
        occupant_count=2,
        style="modern",
        accessibility_required=False,
        objective_weights=sample_weights(),
    )


# Build a design that reuses the scene example's desk.
def sample_design() -> Design:
    """Return one valid design."""
    # Parse the scene so the placed object matches that contract.
    scene = SceneGraph.model_validate_json(SCENE_GRAPH_JSON)
    # Fill every field the design contract requires.
    return Design(
        design_id="design_01",
        scene_id=scene.scene_id,
        requirement_id="req_01",
        weights=sample_weights(),
        score=0.72,
        cost=18000,
        objects=scene.objects,
        parent_design_id=None,
    )


# Build a catalog item with no embedding yet.
def sample_catalog_item() -> CatalogItem:
    """Return one valid catalog item."""
    # Fill every field the catalog contract requires.
    return CatalogItem(
        item_id="item_01",
        category="desk",
        dims={"length": 1.4, "width": 0.7, "height": 0.75},
        price=18000,
        style_tags=["modern"],
        material="wood",
        embedding=None,
    )


# Build a trace with one binding constraint and one rejection.
def sample_trace() -> OptimizerTrace:
    """Return one valid optimizer trace."""
    # Fill every field the trace contract requires.
    return OptimizerTrace(
        design_id="design_01",
        binding_constraints=[{"name": "budget", "detail": "total cost equals 18000 INR"}],
        rejected_items=[{"item_id": "item_99", "reason": "12cm over the remaining wall"}],
        objective_terms={
            "layout": 0.8,
            "circulation": 0.7,
            "ergonomics": 0.6,
            "budget": 1.0,
            "aesthetics": 0.5,
            "sustainability": 0.4,
        },
    )


# Build the first version of the sample design.
def sample_version() -> DesignVersion:
    """Return one valid design version."""
    # Use a fixed offset so the round trip does not depend on the local zone.
    recorded_at = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
    # Fill every field the version contract requires.
    return DesignVersion(
        design_id="design_01",
        scene_id="room_0091",
        version=1,
        parent_version=None,
        diff={},
        score=0.72,
        timestamp=recorded_at,
    )
