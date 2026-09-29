"""Small deterministic Phase 3 test records."""

# Locked schemas validate fixtures before tests use them.
from spacedesigner.schemas import CatalogItem, Requirement, SceneGraph


# Build a square manual scene with optional fixed furniture.
def sample_scene(with_fixed: bool = False) -> SceneGraph:
    """Return a spacious high-confidence room."""
    # Add one 180-degree retained chair when requested.
    objects = (
        [
            {
                "id": "fixed-chair",
                "type": "chair",
                "position": [4.5, 4.5],
                "rotation": 180,
                "dimensions": [0.5, 0.5, 0.9],
                "movable": False,
                "must_keep": True,
                "confidence": "high",
            }
        ]
        if with_fixed
        else []
    )
    # Validate the complete fixture.
    return SceneGraph.model_validate(
        {
            "scene_id": "scene-phase3",
            "version": 1,
            "room_type": "home_office",
            "dimensions": {
                "length": 6.0,
                "width": 6.0,
                "height": 2.8,
                "confidence": "high",
            },
            "openings": [],
            "objects": objects,
        }
    )


# Build one gold requirement for a selected category.
def sample_requirement(
    category: str = "desk",
    budget: float = 10000.0,
    keep_fixed: bool = False,
) -> Requirement:
    """Return a validated structured requirement."""
    # Validate every locked field.
    return Requirement.model_validate(
        {
            "requirement_id": "requirement-phase3",
            "scene_id": "scene-phase3",
            "raw_text": "",
            "budget_inr": budget,
            "must_have": [category],
            "must_keep_object_ids": ["fixed-chair"] if keep_fixed else [],
            "occupant_count": 1,
            "style": "modern",
            "accessibility_required": False,
            "objective_weights": {
                "layout": 1.0,
                "circulation": 1.0,
                "ergonomics": 1.0,
                "budget": 1.0,
                "aesthetics": 1.0,
                "sustainability": 1.0,
            },
        }
    )


# Build one compact catalog row for isolated solver tests.
def sample_catalog(category: str = "desk", price: float = 1000.0) -> tuple[CatalogItem, ...]:
    """Return one validated deterministic catalog item."""
    # Wrap the row in the immutable catalog shape.
    return (
        CatalogItem.model_validate(
            {
                "item_id": f"test-{category}",
                "category": category,
                "dims": {"length": 0.8, "width": 0.5, "height": 0.75},
                "price": price,
                "style_tags": ["modern"],
                "material": "solid_wood",
                "embedding": None,
            }
        ),
    )
