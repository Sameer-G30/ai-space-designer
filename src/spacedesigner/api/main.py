"""FastAPI application for health, manual scenes, and Phase 4 Pareto optimization."""

# Annotated attaches a dependency to a precise store type.
from typing import Annotated

# FastAPI builds the ASGI application and validates route dependencies.
from fastapi import Depends, FastAPI, HTTPException

# BaseModel types the unchanged health response.
from pydantic import BaseModel

# Store dependency supports PostgreSQL in production and an in-memory test fake.
from spacedesigner.api.store import DesignStore, get_design_store

# The independent critic prevents a broken design from crossing the API boundary.
from spacedesigner.critic import audit_design

# Result models keep successful and failed HTTP payloads explicit.
from spacedesigner.optimizer import InfeasibleOptimization
from spacedesigner.optimizer.models import ParetoResult

# Stage 2 sweeps weights and returns one Pareto set per solve.
from spacedesigner.optimizer.stage2_pareto import optimize_pareto

# Cached-vector style scorer; CLIP itself is never loaded inside a request.
from spacedesigner.recommend.scoring import StyleScorer
from spacedesigner.recommend.service import get_style_scorer

# Locked public inputs remain unchanged.
from spacedesigner.schemas import Requirement, SceneGraph

# SchemaModel rejects extra request wrapper keys.
from spacedesigner.schemas.base import SchemaModel


# JSON body returned by GET /health.
class HealthResponse(BaseModel):
    """Status payload for the health route."""

    # "ok" when the process is serving requests.
    status: str


# Request wrapper pairs explicit lookup id with the gold requirement.
class OptimizeRequest(SchemaModel):
    """Input accepted by POST /designs/optimize."""

    # Persisted scene to optimize.
    scene_id: str
    # Already-structured gold requirement; natural language parsing is Phase 6.
    requirement: Requirement


# Reusable injected store annotation.
StoreDependency = Annotated[DesignStore, Depends(get_design_store)]

# Reusable injected scorer annotation (tests override it with a fake embedder).
ScorerDependency = Annotated[StyleScorer, Depends(get_style_scorer)]


# Application object uvicorn loads as spacedesigner.api.main:app.
app = FastAPI(title="PhotoSpace", version="0.1.0")


# Liveness route used by the Phase 0 checks and the Next.js page.
@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report that the API process is up."""
    # Return the only status this skeleton defines.
    return HealthResponse(status="ok")


# Manual-measurement input route for a complete validated scene graph.
@app.post("/scenes", response_model=SceneGraph)
def create_scene(scene: SceneGraph, store: StoreDependency) -> SceneGraph:
    """Validate and persist one manual scene graph."""
    # Store only after FastAPI and Pydantic accepted the complete contract.
    store.save_scene(scene)
    # Echo the canonical validated representation.
    return scene


# Stage 2 optimization route: a Pareto set from a persisted scene and gold requirement.
@app.post("/designs/optimize", response_model=ParetoResult)
def optimize_design(
    request: OptimizeRequest, store: StoreDependency, scorer: ScorerDependency
) -> ParetoResult:
    """Solve a weight sweep, audit every point independently, and persist the set."""
    # Require both copies of the scene identifier to agree.
    if request.requirement.scene_id != request.scene_id:
        # Report a client error before storage lookup.
        raise HTTPException(
            status_code=422,
            detail="request scene_id must match requirement scene_id",
        )
    # Load the validated scene from the configured store.
    scene = store.get_scene(request.scene_id)
    # Unknown scenes cannot be optimized.
    if scene is None:
        # Return the conventional resource status.
        raise HTTPException(status_code=404, detail="scene not found")
    # Run the Stage 2 sweep; Stage 2 already audits each point with the independent checker.
    result = optimize_pareto(scene, request.requirement, scorer=scorer)
    # Return readable infeasibility without writing a design.
    if not result.feasible:
        # Preserve the solver reason and measured duration.
        return result
    # Re-audit at the API boundary so a broken design can never cross it.
    for point in result.points:
        # Independent Shapely findings for this point.
        violations = audit_design(scene, request.requirement, point.design, point.bom)
        # Convert any finding into a no-design response.
        if violations:
            # Nothing is persisted when a point fails.
            return InfeasibleOptimization(
                reason=f"independent checker rejected solution: {'; '.join(violations)}",
                solve_time_ms=result.solve_time_ms,
            )
    # Persist the requirement and every audited design in the set.
    for point in result.points:
        # Each design has a distinct deterministic id.
        store.save_design(request.requirement, point.design)
    # Return the Pareto set with traces and BOMs.
    return result
