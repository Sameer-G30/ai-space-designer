"""Phase 8 request and response models. The locked schemas are nested, not edited."""

# Literal distinguishes the two counterfactual outcomes.
from typing import Any, Literal

# Field bounds the optional what-if numbers.
from pydantic import Field, model_validator

# BomLine is the same bill the optimize route already returns.
from spacedesigner.optimizer.models import BomLine

# Locked records travel inside the new responses.
from spacedesigner.schemas import Design, DesignVersion, OptimizerTrace, SceneGraph

# SchemaModel rejects unexpected keys.
from spacedesigner.schemas.base import SchemaModel


# One templated sentence and the trace field it came from.
class TemplatedFact(SchemaModel):
    """A fact the model is allowed to rephrase."""

    # Dotted pointer such as trace.binding_constraints.budget.
    ref: str = Field(min_length=1)
    # The sentence, including every number written out.
    text: str = Field(min_length=1)


# One stored explanation row.
class ExplanationClaim(SchemaModel):
    """A claim written to the explanations table."""

    # Surrogate key.
    explanation_id: str = Field(min_length=1)
    # Sentence, either a rephrase or the template itself.
    claim_text: str = Field(min_length=1)
    # Trace field that supports the claim, or a failure tag.
    supporting_trace_ref: str = Field(min_length=1)
    # True when every number and domain word in the claim is in the facts.
    verified: bool


# GET /designs/{id}/explanation.
class ExplanationResponse(SchemaModel):
    """Templated facts plus the claims stored for one design."""

    # Design that was explained.
    design_id: str = Field(min_length=1)
    # Facts computed from the trace. These are the sources.
    facts: list[TemplatedFact]
    # Claims stored in explanations. Empty only before the first write fails.
    claims: list[ExplanationClaim]
    # verified claims divided by the number of claims.
    verified_rate: float = Field(ge=0, le=1)
    # True when the stored claims came from the language model.
    rephrased: bool
    # Why the model did or did not rephrase.
    rephrase_note: str


# Body of POST /designs/{id}/counterfactual. At least one field is required.
class CounterfactualRequest(SchemaModel):
    """Parameter changes. Omitted fields stay at the solved design's values."""

    # Replacement budget in INR. Absent means the budget is unchanged.
    budget_inr: float | None = Field(default=None, ge=0)
    # Replacement room length in metres.
    length_m: float | None = Field(default=None, gt=0)
    # Replacement room width in metres.
    width_m: float | None = Field(default=None, gt=0)
    # Replacement room height in metres. Stage 1 does not place against height.
    height_m: float | None = Field(default=None, gt=0)
    # Replacement occupant count. Stage 1 does not constrain it.
    occupant_count: int | None = Field(default=None, ge=1)

    # Reject an empty what-if before the solver starts.
    @model_validator(mode="after")
    def at_least_one_change(self) -> "CounterfactualRequest":
        """Require one parameter so a click cannot re-solve with no delta."""
        # Every optional field.
        values = (
            self.budget_inr,
            self.length_m,
            self.width_m,
            self.height_m,
            self.occupant_count,
        )
        # An empty body is a client error.
        if all(value is None for value in values):
            # FastAPI turns this into HTTP 422.
            raise ValueError(
                "provide at least one of budget_inr, length_m, width_m, height_m, occupant_count"
            )
        # Keep the request.
        return self


# A warm-started design that passed the hard constraints.
class CounterfactualDesign(SchemaModel):
    """The re-optimized design and the sensitivity of that re-solve."""

    # Discriminator.
    feasible: Literal[True] = True
    # New design. parent_design_id points at the design in the URL.
    design: Design
    # Trace of the warm-started solve.
    trace: OptimizerTrace
    # Bill whose total equals design.cost.
    bom: list[BomLine]
    # Scene the new design was solved against. A room-size change uses a new scene id.
    scene: SceneGraph
    # Design the what-if started from.
    parent_design_id: str = Field(min_length=1)
    # CP-SAT wall time for the warm-started solve, in milliseconds.
    solve_time_ms: float = Field(ge=0)
    # New score minus the parent score.
    score_change: float
    # New cost minus the parent cost.
    cost_change: float
    # New budget minus the parent budget. Zero when the budget was not edited.
    budget_change_inr: float
    # score_change / budget_change_inr, or null when the budget did not change.
    sensitivity_score_per_inr: float | None
    # How many previous item poses were passed to CP-SAT as hints.
    hint_count: int = Field(ge=0)
    # True when at least one hint was passed.
    warm_started: bool
    # The same diff stored on the version row.
    diff: dict[str, Any]


# A what-if that has no hard-feasible design.
class CounterfactualRejected(SchemaModel):
    """A readable reason and no design."""

    # Discriminator.
    feasible: Literal[False] = False
    # Solver or selection reason.
    reason: str = Field(min_length=1)
    # Design the what-if started from.
    parent_design_id: str = Field(min_length=1)
    # Time spent before giving up, in milliseconds.
    solve_time_ms: float = Field(ge=0)
    # True when hints were passed into the attempt.
    warm_started: bool
    # Hints passed, even if the model was infeasible.
    hint_count: int = Field(ge=0)


# Public union for the counterfactual route.
CounterfactualResult = CounterfactualDesign | CounterfactualRejected


# GET /designs/{id}/versions.
class VersionsResponse(SchemaModel):
    """Append-only versions stored for one design id."""

    # Design the rows belong to.
    design_id: str = Field(min_length=1)
    # Version 1 is the snapshot. Later rows are what-if diffs.
    versions: list[DesignVersion]
