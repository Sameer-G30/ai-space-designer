"""FastAPI application for health, scenes, Pareto optimization, requirements, and explanations."""

# Annotated attaches a dependency to a precise store type.
from typing import Annotated

# FastAPI builds the ASGI application and validates route dependencies.
from fastapi import Depends, FastAPI, HTTPException, Request

# BaseModel types the unchanged health response.
from pydantic import BaseModel

# Store dependency supports PostgreSQL in production and an in-memory test fake.
from spacedesigner.api.store import DesignStore, get_design_store

# The independent critic prevents a broken design from crossing the API boundary.
from spacedesigner.critic import audit_design

# Phase 8 failures become HTTP status codes. The solver itself is unchanged.
from spacedesigner.explain.errors import ExplainError

# Counterfactual, explanation, and version payloads.
from spacedesigner.explain.models import (
    CounterfactualRequest,
    CounterfactualResult,
    ExplanationResponse,
    VersionsResponse,
)

# Explanation, what-if, and version orchestration.
from spacedesigner.explain.service import (
    build_explanation,
    list_design_versions,
    run_counterfactual,
)

# Result models keep successful and failed HTTP payloads explicit.
from spacedesigner.optimizer import InfeasibleOptimization
from spacedesigner.optimizer.models import ParetoResult

# Stage 2 sweeps weights and returns one Pareto set per solve.
from spacedesigner.optimizer.stage2_pareto import optimize_pareto

# Photo pipeline pieces. The GPU worker runs in a child process behind an injectable runner.
from spacedesigner.perception.assemble import InvalidMeasurement, build_scene
from spacedesigner.perception.models import DimensionConfidence, PhotoSceneResponse, RoomGuess
from spacedesigner.perception.privacy import UnreadableImage, strip_metadata, to_png_bytes
from spacedesigner.perception.runner import PerceptionFailure, get_perception_runner

# Hybrid index dependency. Tests override it so weights are not loaded.
from spacedesigner.rag.hybrid import HybridRetriever, get_hybrid_retriever

# Cached-vector style scorer; CLIP itself is never loaded inside a request.
from spacedesigner.recommend.scoring import StyleScorer
from spacedesigner.recommend.service import get_style_scorer

# Parser failures become HTTP 422. The model is not loaded in this process.
from spacedesigner.requirements.errors import ParserFailure

# Parse route models.
from spacedesigner.requirements.models import ParseRequest, ParseResponse

# Ollama HTTP client dependency.
from spacedesigner.requirements.ollama_client import get_chat_client

# Chat contract used by the route annotation.
from spacedesigner.requirements.parser import ChatClient

# Parse plus retrieval. Constants are copied, not edited.
from spacedesigner.requirements.service import parse_and_retrieve

# Locked public inputs remain unchanged.
from spacedesigner.schemas import Requirement, SceneGraph

# SchemaModel rejects extra request wrapper keys.
from spacedesigner.schemas.base import SchemaModel

# Phase 9 workers. Tests override the dependency so no weights load.
from spacedesigner.visualize.backends import VisualizeBackends, get_visualize_backends

# Missing design, scene, or requirement.
from spacedesigner.visualize.errors import VisualizeError

# Visualize response. The locked design schema is not edited.
from spacedesigner.visualize.models import VisualizeResponse

# Maps, optional diffusion, consistency, and the advisory critic.
from spacedesigner.visualize.service import visualize_design


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
    # Structured requirement. POST /requirements fills this from a sentence.
    requirement: Requirement


# Reusable injected store annotation.
StoreDependency = Annotated[DesignStore, Depends(get_design_store)]

# Reusable injected scorer annotation (tests override it with a fake embedder).
ScorerDependency = Annotated[StyleScorer, Depends(get_style_scorer)]

# Reusable injected chat client. The default talks to Ollama over HTTP.
ChatDependency = Annotated[ChatClient, Depends(get_chat_client)]

# Reusable injected retriever. The default embeds and reranks on CPU.
RetrieverDependency = Annotated[HybridRetriever, Depends(get_hybrid_retriever)]


# Reusable injected photo runner (tests replace it so no GPU or weights are used).
RunnerDependency = Annotated[object, Depends(get_perception_runner)]

# Reusable injected visualize backends. The default does not download weights.
BackendDependency = Annotated[VisualizeBackends, Depends(get_visualize_backends)]

# Largest photo upload in bytes.
MAX_PHOTO_BYTES = 15 * 1024 * 1024


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


# Photo route under the same /scenes prefix. The body is the raw image, so no parser is added.
@app.post("/scenes/photo", response_model=PhotoSceneResponse)
async def create_scene_from_photo(
    request: Request,
    store: StoreDependency,
    runner: RunnerDependency,
    scene_id: str,
    known_length_m: float | None = None,
    known_axis: str = "length",
) -> PhotoSceneResponse:
    """Strip metadata, run the vision pipeline, scale to metres, and save a new scene version."""
    # Read the raw image bytes.
    data = await request.body()
    # Empty and oversized uploads are client errors.
    if not data or len(data) > MAX_PHOTO_BYTES:
        # Tell the client what is allowed.
        raise HTTPException(status_code=422, detail="upload one image of at most 15 MB")
    # Privacy pass step one: pixels only, no EXIF or GPS.
    try:
        # Decode and re-encode.
        clean = strip_metadata(data)
    # Not an image.
    except UnreadableImage as exc:
        # Client error.
        raise HTTPException(status_code=422, detail=str(exc)) from None
    # Run the pipeline (face blur is its first step, before any model).
    try:
        # The runner sees only the metadata-free PNG.
        result = runner(to_png_bytes(clean.image), clean.focal_35mm)
    # Missing weights, no floor, timeouts.
    except PerceptionFailure as exc:
        # The form stays usable by hand.
        raise HTTPException(status_code=422, detail=str(exc)) from None
    # Next version number continues an existing scene, else starts at 1.
    existing = store.get_scene(scene_id)
    # Version follows the Phase 0 scene versioning.
    version = existing.version + 1 if existing is not None else 1
    # Scale and assemble with a confidence on every dimension.
    try:
        # Build the locked scene graph.
        scene, confidence, factor = build_scene(
            result, scene_id, version, known_length_m, known_axis
        )
    # A typed length that cannot be used.
    except InvalidMeasurement as exc:
        # Client error.
        raise HTTPException(status_code=422, detail=str(exc)) from None
    # Persist before replying so the optimizer can run on it.
    store.save_scene(scene)
    # Return the scene and how it was estimated.
    return PhotoSceneResponse(
        scene=scene,
        dimension_confidence=DimensionConfidence(**confidence),
        scale_source="metric_depth" if known_length_m is None else "user_length",
        scale_factor=factor,
        room_guesses=[
            RoomGuess(room_type=name, probability=prob) for name, prob in result["room_type_scores"]
        ],
        detections=[f"{name} {score:.2f}" for name, score in result["detections"]],
        faces_blurred=result["faces_blurred"],
        warnings=result["warnings"],
    )


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


# Natural-language requirement route. The sentence is parsed, then clearances are retrieved.
@app.post("/requirements", response_model=ParseResponse)
def create_requirement(
    body: ParseRequest,
    chat: ChatDependency,
    retriever: RetrieverDependency,
) -> ParseResponse:
    """Validate one sentence into a Requirement and attach retrieved numbers."""
    # Model and index failures that are not a bad requirement become 422.
    try:
        # Parse, then retrieve. Solver constants are copied unchanged.
        return parse_and_retrieve(body, chat, retriever)
    # Unreadable model output, or Ollama did not answer.
    except ParserFailure as exc:
        # The form shows this string and does not fill the structured fields.
        raise HTTPException(status_code=422, detail=str(exc)) from None


# Explanation route. The optimizer routes above are unchanged.
@app.get("/designs/{design_id}/explanation", response_model=ExplanationResponse)
def read_explanation(
    design_id: str,
    store: StoreDependency,
    scorer: ScorerDependency,
    chat: ChatDependency,
) -> ExplanationResponse:
    """Rephrase the templated trace, or return the claims already stored for this design."""
    # Missing rows and a replay failure become 404 or 422.
    try:
        # Phrase on the first call. Later calls read the stored claims.
        return build_explanation(store, design_id, scorer, chat)
    # Not found, or the stored design cannot be replayed.
    except ExplainError as exc:
        # Keep the status the service chose.
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


# What-if route. Warm-starts CP-SAT from the stored design and appends a version diff.
@app.post("/designs/{design_id}/counterfactual", response_model=CounterfactualResult)
def create_counterfactual(
    design_id: str,
    body: CounterfactualRequest,
    store: StoreDependency,
    scorer: ScorerDependency,
) -> CounterfactualResult:
    """Re-solve one parameter change. An infeasible change is returned without a new design."""
    # Missing rows become 404. A bad catalog id becomes 422.
    try:
        # Persist only when the warm-started solve is feasible.
        return run_counterfactual(store, design_id, body, scorer)
    # Not found, or the stored design cannot be replayed.
    except ExplainError as exc:
        # Keep the status the service chose.
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


# Image route. It does not change the optimize, scene, requirement, or explanation routes.
@app.post("/designs/{design_id}/visualize", response_model=VisualizeResponse)
def visualize_existing(
    design_id: str,
    store: StoreDependency,
    backends: BackendDependency,
) -> VisualizeResponse:
    """Render maps and, when weights are local, an inpainted image plus an advisory note."""
    # A missing row becomes 404. The design is not rewritten on success.
    try:
        # Depth, segmentation, optional diffusion, consistency, and the critic.
        return visualize_design(store, design_id, backends=backends)
    # Not found.
    except VisualizeError as exc:
        # Keep the status the service chose.
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


# Version route. The first read stores version 1, an append-only snapshot.
@app.get("/designs/{design_id}/versions", response_model=VersionsResponse)
def read_versions(design_id: str, store: StoreDependency) -> VersionsResponse:
    """Return the append-only version rows for one design."""
    # An unknown design is 404. The snapshot insert does not need the solver.
    try:
        # Create version 1 when this design has no rows yet.
        return list_design_versions(store, design_id)
    # Not found.
    except ExplainError as exc:
        # Keep the status the service chose.
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
