"""Validation tests for values the Phase 0 contracts must reject."""

# pytest.raises catches the expected validation error.
import pytest

# ValidationError is what Pydantic raises for a bad document.
from pydantic import ValidationError

# Models whose bounds are checked below.
from spacedesigner.schemas import CatalogItem, DesignVersion, Requirement, SceneGraph

# Valid documents that each test mutates in one place.
from tests.schemas.samples import (
    SCENE_GRAPH_JSON,
    sample_catalog_item,
    sample_requirement,
    sample_version,
)


# A non-positive room length is not a usable room.
def test_room_length_must_be_positive() -> None:
    """Reject a room whose length is zero."""
    # Start from the blueprint example.
    payload = SceneGraph.model_validate_json(SCENE_GRAPH_JSON).model_dump()
    # Break only the length.
    payload["dimensions"]["length"] = 0
    # Expect Pydantic to reject the document.
    with pytest.raises(ValidationError):
        # Parse the broken document.
        SceneGraph.model_validate(payload)


# Confidence outside the three labels is not part of the contract.
def test_confidence_must_be_a_known_label() -> None:
    """Reject an unknown confidence label."""
    # Start from the blueprint example.
    payload = SceneGraph.model_validate_json(SCENE_GRAPH_JSON).model_dump()
    # Break only the object confidence.
    payload["objects"][0]["confidence"] = "certain"
    # Expect Pydantic to reject the document.
    with pytest.raises(ValidationError):
        # Parse the broken document.
        SceneGraph.model_validate(payload)


# A position needs exactly two floor coordinates.
def test_object_position_needs_two_coordinates() -> None:
    """Reject a position that has three numbers."""
    # Start from the blueprint example.
    payload = SceneGraph.model_validate_json(SCENE_GRAPH_JSON).model_dump()
    # Break only the position.
    payload["objects"][0]["position"] = [1.0, 2.0, 3.0]
    # Expect Pydantic to reject the document.
    with pytest.raises(ValidationError):
        # Parse the broken document.
        SceneGraph.model_validate(payload)


# An object size must be positive on every axis.
def test_object_dimensions_must_be_positive() -> None:
    """Reject an object with a zero height."""
    # Start from the blueprint example.
    payload = SceneGraph.model_validate_json(SCENE_GRAPH_JSON).model_dump()
    # Break only the height.
    payload["objects"][0]["dimensions"] = [1.4, 0.7, 0]
    # Expect Pydantic to reject the document.
    with pytest.raises(ValidationError):
        # Parse the broken document.
        SceneGraph.model_validate(payload)


# Duplicate ids would make must-keep ambiguous.
def test_object_ids_must_be_unique() -> None:
    """Reject two objects that share an id."""
    # Start from the blueprint example.
    payload = SceneGraph.model_validate_json(SCENE_GRAPH_JSON).model_dump()
    # Copy the only object and keep its id.
    payload["objects"].append(dict(payload["objects"][0]))
    # Expect Pydantic to reject the document.
    with pytest.raises(ValidationError):
        # Parse the broken document.
        SceneGraph.model_validate(payload)


# Unknown keys are outside the integration contract.
def test_unknown_scene_field_is_rejected() -> None:
    """Reject a scene graph that carries an undeclared field."""
    # Start from the blueprint example.
    payload = SceneGraph.model_validate_json(SCENE_GRAPH_JSON).model_dump()
    # Add a key the contract does not define.
    payload["notes"] = "extra"
    # Expect Pydantic to reject the document.
    with pytest.raises(ValidationError):
        # Parse the broken document.
        SceneGraph.model_validate(payload)


# A budget cannot be negative.
def test_budget_cannot_be_negative() -> None:
    """Reject a requirement with a negative budget."""
    # Start from a valid requirement.
    payload = sample_requirement().model_dump()
    # Break only the budget.
    payload["budget_inr"] = -1
    # Expect Pydantic to reject the document.
    with pytest.raises(ValidationError):
        # Parse the broken document.
        Requirement.model_validate(payload)


# Each weight lives on the unit interval.
def test_weight_cannot_exceed_one() -> None:
    """Reject an objective weight above 1."""
    # Start from a valid requirement.
    payload = sample_requirement().model_dump()
    # Break only one weight.
    payload["objective_weights"]["layout"] = 1.1
    # Expect Pydantic to reject the document.
    with pytest.raises(ValidationError):
        # Parse the broken document.
        Requirement.model_validate(payload)


# A catalog price cannot be negative.
def test_catalog_price_cannot_be_negative() -> None:
    """Reject a catalog item with a negative price."""
    # Start from a valid catalog item.
    payload = sample_catalog_item().model_dump()
    # Break only the price.
    payload["price"] = -10
    # Expect Pydantic to reject the document.
    with pytest.raises(ValidationError):
        # Parse the broken document.
        CatalogItem.model_validate(payload)


# An embedding, once present, needs components.
def test_empty_embedding_is_rejected() -> None:
    """Reject a catalog embedding that is an empty list."""
    # Start from a valid catalog item.
    payload = sample_catalog_item().model_dump()
    # Replace the missing embedding with an empty vector.
    payload["embedding"] = []
    # Expect Pydantic to reject the document.
    with pytest.raises(ValidationError):
        # Parse the broken document.
        CatalogItem.model_validate(payload)


# Version timestamps need a timezone.
def test_naive_timestamp_is_rejected() -> None:
    """Reject a design version timestamp that has no offset."""
    # Start from a valid version and drop the offset in the JSON form.
    payload = sample_version().model_dump(mode="json")
    # A trailing Z is the offset; remove it so the timestamp is naive.
    payload["timestamp"] = "2026-09-28T12:00:00"
    # Expect Pydantic to reject the document.
    with pytest.raises(ValidationError):
        # Parse the broken document.
        DesignVersion.model_validate(payload)
