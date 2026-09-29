"""Route tests (Phase 3 routes, Phase 4 Pareto response) with an in-memory store."""

# FastAPI TestClient exercises request and response validation.
from fastapi.testclient import TestClient

# Dependency key and application are overridden without a live database.
from spacedesigner.api.main import app

# Store dependency function is the override key.
from spacedesigner.api.store import get_design_store

# Scorer dependency is overridden with a fake embedder so no weights load.
from spacedesigner.optimizer.catalog import load_catalog
from spacedesigner.recommend.scoring import load_style_scorer
from spacedesigner.recommend.service import get_style_scorer

# Locked records type fake-store state.
from spacedesigner.schemas import Design, Requirement, SceneGraph

# Shared fixtures provide valid API bodies.
from tests.phase3_samples import sample_requirement, sample_scene
from tests.recommend.fakes import FakeEmbedder


# Minimal in-memory implementation of the Phase 3 store protocol.
class MemoryStore:
    """Capture route writes for isolated API tests."""

    # Initialize empty record maps.
    def __init__(self) -> None:
        """Create empty in-memory storage."""
        # Scenes are indexed by scene identifier.
        self.scenes: dict[str, SceneGraph] = {}
        # Successful pairs are retained for assertions.
        self.saved: list[tuple[Requirement, Design]] = []

    # Save one scene by identifier.
    def save_scene(self, scene: SceneGraph) -> None:
        """Store one scene."""
        # Replace the prior version for the same id.
        self.scenes[scene.scene_id] = scene

    # Load one scene by identifier.
    def get_scene(self, scene_id: str) -> SceneGraph | None:
        """Return one stored scene."""
        # Use dictionary lookup for missing-scene behavior.
        return self.scenes.get(scene_id)

    # Capture one successful requirement/design pair.
    def save_design(self, requirement: Requirement, design: Design) -> None:
        """Store one feasible result."""
        # Append in route-call order.
        self.saved.append((requirement, design))


# Exercise both required routes with real optimization.
def test_scene_and_optimize_routes(tmp_path) -> None:
    """Persist a scene and return an audited design response."""
    # Create one store for both HTTP calls.
    store = MemoryStore()
    # Override production PostgreSQL access.
    app.dependency_overrides[get_design_store] = lambda: store
    # Deterministic style scoring without CLIP weights or the local cache.
    scorer = load_style_scorer(load_catalog(), FakeEmbedder(), tmp_path / "c.npz", ("modern",))
    # Override the scorer dependency.
    app.dependency_overrides[get_style_scorer] = lambda: scorer
    # Ensure overrides are removed even when an assertion fails.
    try:
        # Create a synchronous test client.
        with TestClient(app) as client:
            # Post the complete manual-measurement graph.
            scene_response = client.post("/scenes", json=sample_scene().model_dump(mode="json"))
            # Require successful validation and storage.
            assert scene_response.status_code == 200
            # Post the gold requirement wrapper.
            optimize_response = client.post(
                "/designs/optimize",
                json={
                    "scene_id": "scene-phase3",
                    "requirement": sample_requirement().model_dump(mode="json"),
                },
            )
            # Require a schema-valid optimization response.
            assert optimize_response.status_code == 200
            # Decode the returned union.
            payload = optimize_response.json()
            # The spacious fixture should produce one feasible Pareto set.
            assert payload["feasible"] is True
            # One set with 1 to 8 labelled points.
            assert 1 <= len(payload["points"]) <= 8
            # Every point carries design, trace, BOM and labels; trace never sits inside Design.
            for point in payload["points"]:
                # Required keys.
                assert {"labels", "design", "trace", "bom"} <= set(point)
                # Trace stays beside the design.
                assert "trace" not in point["design"]
                # BOM accounting must equal Design.cost.
                assert sum(x["line_total"] for x in point["bom"]) == point["design"]["cost"]
                # Budget is never exceeded.
                assert point["design"]["cost"] <= 10000.0
            # Every point in the set is persisted.
            assert len(store.saved) == len(payload["points"])
    # Always restore application dependency state.
    finally:
        # Remove all local overrides.
        app.dependency_overrides.clear()


# Confirm missing scene lookup returns the intended status.
def test_optimize_unknown_scene_returns_404() -> None:
    """Reject optimization before invoking CP-SAT for an unknown scene."""
    # Configure an empty store.
    store = MemoryStore()
    # Override production persistence.
    app.dependency_overrides[get_design_store] = lambda: store
    # Ensure cleanup after the request.
    try:
        # Create the route client.
        with TestClient(app) as client:
            # Submit a valid wrapper whose scene is absent.
            response = client.post(
                "/designs/optimize",
                json={
                    "scene_id": "scene-phase3",
                    "requirement": sample_requirement().model_dump(mode="json"),
                },
            )
            # Require conventional not-found behavior.
            assert response.status_code == 404
    # Restore shared app state.
    finally:
        # Clear the override mapping.
        app.dependency_overrides.clear()
