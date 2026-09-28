"""Tests for the Phase 0 health route."""

# TestClient calls the ASGI app without opening a port.
from fastapi.testclient import TestClient

# The application under test.
from spacedesigner.api.main import app


# GET /health is the only route this phase exposes.
def test_health_returns_ok() -> None:
    """Return 200 and the ok status body."""
    # Build a client bound to the in-process app.
    client = TestClient(app)
    # Call the health route.
    response = client.get("/health")
    # The process must answer with HTTP 200.
    assert response.status_code == 200
    # The body must be the status contract.
    assert response.json() == {"status": "ok"}
