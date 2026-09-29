"""Phase 3 Stage 1 layout optimization."""

# Public result models support explicit feasible and infeasible handling.
from spacedesigner.optimizer.models import (
    BomLine,
    FeasibleOptimization,
    InfeasibleOptimization,
    OptimizationResult,
)

# optimize is the single Stage 1 entry point.
from spacedesigner.optimizer.stage1_cpsat import optimize

# Limit wildcard imports to the supported Phase 3 surface.
__all__ = [
    "BomLine",
    "FeasibleOptimization",
    "InfeasibleOptimization",
    "OptimizationResult",
    "optimize",
]
