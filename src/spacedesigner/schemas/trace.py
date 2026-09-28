"""Optimizer decision trace from blueprint section 22 and Phase 3."""

# Field expresses required text and the unit interval used for scores.
from pydantic import Field

# SchemaModel rejects keys that are not part of this contract.
from spacedesigner.schemas.base import SchemaModel


# One hard constraint that held with equality at the chosen solution.
class BindingConstraint(SchemaModel):
    # Short name of the constraint, such as "budget".
    name: str = Field(min_length=1)
    # Human-readable fact recorded for that constraint.
    detail: str = Field(min_length=1)


# One catalog item the solver considered and did not place.
class RejectedItem(SchemaModel):
    # Catalog item that was rejected.
    item_id: str = Field(min_length=1)
    # Reason recorded by the solver.
    reason: str = Field(min_length=1)


# The six objective terms, each normalized to the unit interval.
class ObjectiveTerms(SchemaModel):
    # Layout and space-utilization term.
    layout: float = Field(ge=0, le=1)
    # Circulation-area term.
    circulation: float = Field(ge=0, le=1)
    # Ergonomic-guideline term.
    ergonomics: float = Field(ge=0, le=1)
    # Budget-compliance term.
    budget: float = Field(ge=0, le=1)
    # Style and aesthetic term.
    aesthetics: float = Field(ge=0, le=1)
    # Sustainability term.
    sustainability: float = Field(ge=0, le=1)


# Facts the explanation layer is allowed to rephrase.
class OptimizerTrace(SchemaModel):
    # Design this trace explains.
    design_id: str = Field(min_length=1)
    # Constraints that were binding in the chosen solution.
    binding_constraints: list[BindingConstraint]
    # Items the solver rejected, with the recorded reason.
    rejected_items: list[RejectedItem]
    # Normalized contribution of each objective term.
    objective_terms: ObjectiveTerms
