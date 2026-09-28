"""Requirement models named in blueprint sections 15, 21, 23, and 38."""

# Field and field_validator express bounds and list rules.
from pydantic import Field, field_validator

# SchemaModel rejects keys that are not part of this contract.
from spacedesigner.schemas.base import SchemaModel


# The six weights in the layout scoring formula.
class ObjectiveWeights(SchemaModel):
    # Weight for layout and space-utilization efficiency.
    layout: float = Field(ge=0, le=1)
    # Weight for circulation-area adequacy.
    circulation: float = Field(ge=0, le=1)
    # Weight for ergonomic-guideline satisfaction.
    ergonomics: float = Field(ge=0, le=1)
    # Weight for budget compliance.
    budget: float = Field(ge=0, le=1)
    # Weight for style and aesthetic compatibility.
    aesthetics: float = Field(ge=0, le=1)
    # Weight for the sustainability score.
    sustainability: float = Field(ge=0, le=1)


# Structured requirement paired with the original user text.
class Requirement(SchemaModel):
    # Identifier for this requirement row.
    requirement_id: str = Field(min_length=1)
    # Scene this requirement applies to.
    scene_id: str = Field(min_length=1)
    # Original natural-language text, which may be empty before parsing.
    raw_text: str
    # Hard budget ceiling in Indian rupees.
    budget_inr: float = Field(ge=0)
    # Item categories the design must include.
    must_have: list[str]
    # Scene-object ids the design must retain.
    must_keep_object_ids: list[str]
    # Number of people the room must accommodate.
    occupant_count: int = Field(ge=1)
    # Requested style description used for similarity scoring.
    style: str = Field(min_length=1)
    # Whether accessibility clearances are mandatory.
    accessibility_required: bool
    # User-adjustable weights for the six objective terms.
    objective_weights: ObjectiveWeights

    # Reject blank strings inside the item and object-id lists.
    @field_validator("must_have", "must_keep_object_ids")
    @classmethod
    def entries_must_be_non_empty(cls, value: list[str]) -> list[str]:
        # Inspect each requested category or object id.
        for entry in value:
            # A blank entry cannot identify an item.
            if not entry.strip():
                # Fail validation with a stable message.
                raise ValueError("list entries must be non-empty strings")
        # Return the list unchanged when every entry has text.
        return value
