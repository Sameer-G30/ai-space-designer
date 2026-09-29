"""Internal Phase 3 result and bill-of-material models."""

# Field applies non-negative constraints to monetary values and quantities.
from pydantic import Field

# Locked public schemas remain nested rather than being modified.
from spacedesigner.schemas import Design, OptimizerTrace

# SchemaModel rejects unexpected API and solver fields.
from spacedesigner.schemas.base import SchemaModel


# One deterministic bill-of-material line.
class BomLine(SchemaModel):
    """Aggregate one catalog item used by a design."""

    # Catalog identifier for the purchased item.
    item_id: str = Field(min_length=1)
    # Taxonomy category shown to the caller.
    category: str = Field(min_length=1)
    # Number of identical units in the design.
    qty: int = Field(ge=1)
    # Price of one unit in INR.
    unit_price: float = Field(ge=0)
    # Quantity multiplied by the unit price.
    line_total: float = Field(ge=0)


# Successful optimizer output kept separate from the locked Design schema.
class FeasibleOptimization(SchemaModel):
    """Return one audited design and its supporting records."""

    # Feasibility discriminator for API serialization.
    feasible: bool = True
    # Schema-valid candidate produced by CP-SAT.
    design: Design
    # Facts explaining the solver decision.
    trace: OptimizerTrace
    # Deterministically aggregated purchased catalog items.
    bom: list[BomLine]
    # Wall-clock solve duration in milliseconds.
    solve_time_ms: float = Field(ge=0)


# Failed optimizer output never carries a design.
class InfeasibleOptimization(SchemaModel):
    """Return a readable explanation when no hard-feasible design exists."""

    # Feasibility discriminator for API serialization.
    feasible: bool = False
    # Human-readable hard-constraint failure.
    reason: str = Field(min_length=1)
    # Wall-clock solve duration in milliseconds.
    solve_time_ms: float = Field(ge=0)


# One labelled non-dominated design in a Stage 2 Pareto set.
class ParetoPoint(SchemaModel):
    """Wrap a Stage 1-style result with the labels that name it."""

    # Names such as cheapest, balanced, premium, most_sustainable (a point may have several).
    labels: list[str] = Field(min_length=1)
    # Schema-valid design placed by CP-SAT.
    design: Design
    # Trace beside the design, never inside it.
    trace: OptimizerTrace
    # Deterministic bill of materials whose total equals Design.cost.
    bom: list[BomLine]
    # Solver wall-clock time for this point in milliseconds.
    solve_time_ms: float = Field(ge=0)


# Successful Stage 2 output: one Pareto set per solve.
class ParetoOptimization(SchemaModel):
    """Return the labelled non-dominated designs for one scene and requirement."""

    # Feasibility discriminator for API serialization.
    feasible: bool = True
    # Between one and eight labelled, non-dominated, audited designs.
    points: list[ParetoPoint] = Field(min_length=1, max_length=8)
    # Distinct item selections that were placed and audited.
    candidates_evaluated: int = Field(ge=1)
    # Placed candidates removed because another candidate dominated them.
    dominated_removed: int = Field(ge=0)
    # Style scoring backend: the CLIP checkpoint name or the tag-overlap fallback.
    style_backend: str = Field(min_length=1)
    # Total wall-clock time for the whole sweep in milliseconds.
    solve_time_ms: float = Field(ge=0)


# Public union used by scripts, tests, and the API.
OptimizationResult = FeasibleOptimization | InfeasibleOptimization

# Stage 2 response union used by POST /designs/optimize.
ParetoResult = ParetoOptimization | InfeasibleOptimization
