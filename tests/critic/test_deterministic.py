"""Independent critic rejection tests."""

# Public schemas build intentionally invalid candidate designs.
# Critic must find violations without consulting CP-SAT.
from spacedesigner.critic import audit_design
from spacedesigner.schemas import Design, SceneObject

# Shared validated records reduce unrelated fixture noise.
from tests.phase3_samples import sample_requirement, sample_scene


# Build an output object at a selected centre.
def _chair(object_id: str, x: float, y: float) -> SceneObject:
    """Return one square chair footprint."""
    # Validate the complete scene-object contract.
    return SceneObject(
        id=object_id,
        type="chair",
        position=[x, y],
        rotation=0,
        dimensions=[1.0, 1.0, 1.0],
        movable=True,
        must_keep=False,
        confidence="high",
    )


# Confirm overlap is detected geometrically.
def test_checker_rejects_overlap() -> None:
    """Report intersecting furniture independently."""
    # Build the common room.
    scene = sample_scene()
    # Require a chair category.
    requirement = sample_requirement(category="chair")
    # Deliberately place two chairs at the same centre.
    design = Design(
        design_id="overlap-design",
        scene_id=scene.scene_id,
        requirement_id=requirement.requirement_id,
        weights=requirement.objective_weights,
        score=0.0,
        cost=0.0,
        objects=[_chair("chair-a", 2.0, 2.0), _chair("chair-b", 2.0, 2.0)],
    )
    # Run the independent audit.
    violations = audit_design(scene, requirement, design, [])
    # Require an explicit overlap finding.
    assert any("overlap" in violation for violation in violations)


# Confirm budget and BOM accounting are checked independently.
def test_checker_rejects_budget_breach() -> None:
    """Report a candidate whose cost exceeds its requirement."""
    # Build the room.
    scene = sample_scene()
    # Set a strict budget.
    requirement = sample_requirement(category="chair", budget=10.0)
    # Build an otherwise valid single-chair design.
    design = Design(
        design_id="budget-design",
        scene_id=scene.scene_id,
        requirement_id=requirement.requirement_id,
        weights=requirement.objective_weights,
        score=0.0,
        cost=20.0,
        objects=[_chair("chair-a", 2.0, 2.0)],
    )
    # Run the independent audit.
    violations = audit_design(scene, requirement, design, [])
    # Require the hard-budget finding.
    assert any("exceeds budget" in violation for violation in violations)
