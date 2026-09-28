"""Design record from blueprint section 38."""

# Field expresses id and cost bounds.
from pydantic import Field

# SchemaModel rejects keys that are not part of this contract.
from spacedesigner.schemas.base import SchemaModel

# Objective weights are shared with the requirement contract.
from spacedesigner.schemas.requirement import ObjectiveWeights

# Placed objects use the same object shape as the scene graph.
from spacedesigner.schemas.scene import SceneObject


# One candidate design produced for a scene and a requirement.
class Design(SchemaModel):
    # Identifier for this design.
    design_id: str = Field(min_length=1)
    # Scene the design was solved against.
    scene_id: str = Field(min_length=1)
    # Requirement the design was solved against.
    requirement_id: str = Field(min_length=1)
    # Objective weights used for this candidate.
    weights: ObjectiveWeights
    # Combined objective score for this candidate.
    score: float
    # Total cost of the selected items, in Indian rupees.
    cost: float = Field(ge=0)
    # Objects placed in this design.
    objects: list[SceneObject]
    # Earlier design this candidate was derived from, if any.
    parent_design_id: str | None = None
