"""Round-trip tests for the Phase 0 Pydantic contracts."""

# pytest marks each function below as a test.
import pytest

# Models covered by the round trip.
from spacedesigner.schemas import (
    CatalogItem,
    Design,
    DesignVersion,
    OptimizerTrace,
    Requirement,
    SceneGraph,
)

# Shared documents, including the blueprint scene example.
from tests.schemas.samples import (
    SCENE_GRAPH_JSON,
    sample_catalog_item,
    sample_design,
    sample_requirement,
    sample_trace,
    sample_version,
)

# Union of the contract models this helper accepts.
ContractModel = SceneGraph | Requirement | Design | CatalogItem | OptimizerTrace | DesignVersion


# Dump a model to Python and JSON, then parse both back.
def assert_round_trip(model: ContractModel) -> None:
    """Check that a model survives both dump modes."""
    # Parse the Python dump back into the same model type.
    from_python = type(model).model_validate(model.model_dump())
    # The parsed model must equal the original.
    assert from_python == model
    # Parse the JSON dump back into the same model type.
    from_json = type(model).model_validate_json(model.model_dump_json())
    # The JSON round trip must also equal the original.
    assert from_json == model


# The blueprint example is the scene-graph fixture.
def test_scene_graph_example_round_trip() -> None:
    """Load the section 11 example and round-trip it."""
    # Parse the JSON copied from the blueprint.
    scene = SceneGraph.model_validate_json(SCENE_GRAPH_JSON)
    # Confirm the identifier from that example survived parsing.
    assert scene.scene_id == "room_0091"
    # Confirm the nested confidence labels survived parsing.
    assert scene.dimensions.confidence == "medium"
    assert scene.objects[0].confidence == "high"
    # Run both dump modes.
    assert_round_trip(scene)


# Each remaining contract gets the same two dump modes.
@pytest.mark.parametrize(
    "builder",
    [sample_requirement, sample_design, sample_catalog_item, sample_trace, sample_version],
)
def test_contract_round_trip(builder) -> None:
    """Round-trip one sample from each remaining contract."""
    # Build the sample inside the test so failures name this case.
    assert_round_trip(builder())
