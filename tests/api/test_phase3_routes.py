"""Phase 3 route tests with an in-memory persistence boundary."""

# FastAPI TestClient exercises request and response validation.
from fastapi.testclient import TestClient

# Dependency key and application are overridden without a live database.
from spacedesigner.api.main import app

# Store dependency function is the override key.
from spacedesigner.api.store import get_design_store

# Locked records type fake-store state.
from spacedesigner.schemas import Design, Requirement, SceneGraph

# Shared fixtures provide valid API bodies.
from tests.phase3_samples import sample_requirement, sample_scene


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
def test_scene_and_optimize_routes() -> None:
    """Persist a scene and return an audited design response."""
    # Create one store for both HTTP calls.
    store = MemoryStore()
    # Override production PostgreSQL access.
    app.dependency_overrides[get_design_store] = lambda: store
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
            # The spacious fixture should produce one feasible design.
            assert payload["feasible"] is True
            # Trace must remain beside rather than inside Design.
            assert "trace" in payload and "trace" not in payload["design"]
            # BOM accounting must equal Design.cost.
            assert sum(line["line_total"] for line in payload["bom"]) == payload["design"]["cost"]
            # The feasible design must be persisted once.
            assert len(store.saved) == 1
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
