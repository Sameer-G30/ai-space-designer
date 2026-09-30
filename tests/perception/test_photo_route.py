"""POST /scenes/photo tests with a fake runner. No weights load and no GPU is used."""

# In-memory bytes.
import io

# Route test client.
from fastapi.testclient import TestClient

# Pillow builds the upload.
from PIL import Image

# Application and dependency keys.
from spacedesigner.api.main import app
from spacedesigner.api.store import get_design_store
from spacedesigner.perception.runner import PerceptionFailure, get_perception_runner

# Shared in-memory store and worker-style result.
from tests.api.test_phase3_routes import MemoryStore
from tests.perception.test_assemble import result


# PNG bytes for the upload.
def png() -> bytes:
    """Return a small valid PNG."""
    # Encode a plain image.
    buffer = io.BytesIO()
    # Save it.
    Image.new("RGB", (32, 24), (10, 120, 200)).save(buffer, format="PNG")
    # Return the bytes.
    return buffer.getvalue()


# Client with a fake store and a fake runner that records what it received.
def make_client(runner) -> tuple[TestClient, MemoryStore]:
    """Return a client and its store, with dependency overrides installed."""
    # Fresh store.
    store = MemoryStore()
    # Database override.
    app.dependency_overrides[get_design_store] = lambda: store
    # Runner override.
    app.dependency_overrides[get_perception_runner] = lambda: runner
    # Client bound to the app.
    return TestClient(app), store


# A good upload returns a scene, saves it, and reports metric-depth confidence.
def test_photo_upload_without_length_is_low_and_saved() -> None:
    """Metric depth only: low confidence, version 1, stored."""
    # Runner that records the bytes it got.
    seen = {}

    # Fake pipeline.
    def runner(data: bytes, focal: float | None) -> dict:
        """Capture the input and return a fixed result."""
        # Remember what the pipeline received.
        seen["bytes"], seen["focal"] = data, focal
        # Fixed worker-style result with the extra fields the route reads.
        return {
            **result(),
            "room_type_scores": [["bedroom", 0.7], ["living_room", 0.2], ["home_office", 0.1]],
            "detections": [["bed", 0.9]],
            "faces_blurred": 2,
            "warnings": ["note"],
        }

    # Install the fakes.
    client, store = make_client(runner)
    # Always remove overrides.
    try:
        # Post the raw image bytes.
        response = client.post("/scenes/photo?scene_id=p1", content=png())
    finally:
        # Clean up.
        app.dependency_overrides.clear()
    # Accepted.
    assert response.status_code == 200
    # Body.
    body = response.json()
    # Low confidence, metric depth.
    assert body["scale_source"] == "metric_depth"
    # Scene confidence is low.
    assert body["scene"]["dimensions"]["confidence"] == "low"
    # Every dimension has a label.
    assert body["dimension_confidence"] == {"length": "low", "width": "low", "height": "low"}
    # First version.
    assert body["scene"]["version"] == 1
    # Stored for the optimizer.
    assert store.scenes["p1"].room_type == "bedroom"
    # The pipeline got a metadata-free PNG.
    assert Image.open(io.BytesIO(seen["bytes"])).format == "PNG"
    # Privacy counter passes through.
    assert body["faces_blurred"] == 2


# A typed length gives high confidence, and a second upload bumps the version.
def test_photo_upload_with_length_is_high_and_versions_increase() -> None:
    """Known length: scale applied, confidence high, next upload is version 2."""

    # Fake pipeline.
    def runner(data: bytes, focal: float | None) -> dict:
        """Return a fixed result."""
        # Fixed result.
        return {
            **result(),
            "room_type_scores": [["bedroom", 1.0]],
            "detections": [],
            "faces_blurred": 0,
            "warnings": [],
        }

    # Install the fakes.
    client, store = make_client(runner)
    # Always remove overrides.
    try:
        # First upload, typed length 8 m on a 4 m estimate.
        first = client.post("/scenes/photo?scene_id=p2&known_length_m=8", content=png())
        # Second upload of the same scene.
        second = client.post("/scenes/photo?scene_id=p2", content=png())
    finally:
        # Clean up.
        app.dependency_overrides.clear()
    # Accepted.
    assert first.status_code == 200
    # Source.
    assert first.json()["scale_source"] == "user_length"
    # Scale of two.
    assert first.json()["scale_factor"] == 2.0
    # Room length is the typed length.
    assert first.json()["scene"]["dimensions"]["length"] == 8.0
    # High confidence.
    assert first.json()["scene"]["dimensions"]["confidence"] == "high"
    # Second upload continues the versions.
    assert second.json()["scene"]["version"] == 2
    # The store holds the latest.
    assert store.scenes["p2"].version == 2


# Bad input is a 422, not a crash.
def test_photo_route_rejects_bad_input() -> None:
    """Non-image, empty, bad length, and pipeline failures are all 422."""

    # Runner that fails like a missing-weights worker.
    def failing(data: bytes, focal: float | None) -> dict:
        """Raise the pipeline error."""
        # Safe message.
        raise PerceptionFailure("no floor was found in the photo; enter the room by hand")

    # Install the fakes.
    client, _ = make_client(failing)
    # Always remove overrides.
    try:
        # Not an image.
        assert client.post("/scenes/photo?scene_id=x", content=b"hello").status_code == 422
        # Empty body.
        assert client.post("/scenes/photo?scene_id=x", content=b"").status_code == 422
        # Pipeline failure carries its reason.
        bad = client.post("/scenes/photo?scene_id=x", content=png())
        # Status.
        assert bad.status_code == 422
        # Reason text.
        assert "no floor" in bad.json()["detail"]
    finally:
        # Clean up.
        app.dependency_overrides.clear()


# A typed length that disagrees wildly with the photo is refused before anything is saved.
def test_photo_route_rejects_absurd_length_and_saves_nothing() -> None:
    """A 400 m length on a 4 m estimate is a 422 and nothing is stored."""

    # Fake pipeline.
    def runner(data: bytes, focal: float | None) -> dict:
        """Return a fixed result."""
        # Fixed result.
        return {
            **result(),
            "room_type_scores": [["bedroom", 1.0]],
            "detections": [],
            "faces_blurred": 0,
            "warnings": [],
        }

    # Install the fakes.
    client, store = make_client(runner)
    # Always remove overrides.
    try:
        # Absurd length.
        response = client.post("/scenes/photo?scene_id=p3&known_length_m=400", content=png())
    finally:
        # Clean up.
        app.dependency_overrides.clear()
    # Refused.
    assert response.status_code == 422
    # Nothing saved.
    assert "p3" not in store.scenes
