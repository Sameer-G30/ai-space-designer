"""POST /requirements with a scripted model and a fake index."""

# JSON replies.
import json

# FastAPI TestClient.
from fastapi.testclient import TestClient

# Application and dependency keys.
from spacedesigner.api.main import app

# The door constant this phase must not rewrite.
from spacedesigner.optimizer.constants import MIN_DOOR_CLEAR_WIDTH_M

# Retriever dependency and the hit type.
from spacedesigner.rag.hybrid import ChunkHit, get_hybrid_retriever

# Chat dependency.
from spacedesigner.requirements.ollama_client import get_chat_client

# Weight names for a complete extract.
from spacedesigner.requirements.vocab import WEIGHT_NAMES


# Scripted assistant strings.
class ScriptedChat:
    """Return replies without calling Ollama."""

    # Store the script.
    def __init__(self, replies: list[str]) -> None:
        """Keep the replies."""
        # Remaining strings.
        self._replies = list(replies)

    # One reply.
    def complete(self, messages: list[dict[str, str]], schema: dict) -> str:
        """Pop the next reply."""
        # The route passed a schema.
        assert schema["type"] == "object"
        # The sentence is in the last user turn.
        assert messages[-1]["role"] == "user"
        # Next string.
        return self._replies.pop(0)


# Index that never opens Postgres or loads bge.
class FakeIndex:
    """Return one chunk whose text is original to this test."""

    # The route calls search.
    def search(self, query: str, limit: int = 5) -> list[ChunkHit]:
        """Return a door measurement that differs from the solver constant."""
        # The query includes the sentence.
        assert "desk" in query
        # The limit is the route's top-5.
        assert limit == 5
        # One hit. 900 mm is not the named 0.815 m constant.
        return [
            ChunkHit(
                chunk_id="chunk-test",
                source="ada_2010",
                page=4,
                topic="door",
                text="A door opening is 900 mm minimum.",
                score=2.0,
            )
        ]


# A valid extract that tries to set the wrong scene id.
def _reply() -> str:
    """JSON the assembler accepts."""
    # Fields the model is allowed to set, plus a scene id it must not keep.
    return json.dumps(
        {
            "budget_inr": 80000,
            "must_have": ["desk", "chair"],
            "must_keep_object_ids": ["kept-1"],
            "occupant_count": 1,
            "style": "modern",
            "accessibility_required": False,
            "objective_weights": {name: 1.0 for name in WEIGHT_NAMES},
            "scene_id": "wrong-scene",
        }
    )


# The route returns a Requirement and numbers, and leaves the door constant alone.
def test_requirements_route_returns_parse_and_numbers() -> None:
    """A valid model reply fills the requirement and a retrieved number."""
    # Overrides.
    app.dependency_overrides[get_chat_client] = lambda: ScriptedChat([_reply()])
    # Fake index.
    app.dependency_overrides[get_hybrid_retriever] = lambda: FakeIndex()
    # Always clear overrides.
    try:
        # Client.
        with TestClient(app) as client:
            # Post the sentence and one existing object.
            response = client.post(
                "/requirements",
                json={
                    "scene_id": "room-1",
                    "raw_text": "I need a desk.",
                    "requirement_id": "requirement-room-1",
                    "objects": [{"id": "kept-1", "type": "desk"}],
                },
            )
            # Success.
            assert response.status_code == 200
            # Body.
            body = response.json()
            # Identity comes from the request.
            assert body["requirement"]["scene_id"] == "room-1"
            assert body["requirement"]["raw_text"] == "I need a desk."
            assert body["requirement"]["requirement_id"] == "requirement-room-1"
            # Sorted classes.
            assert body["requirement"]["must_have"] == ["chair", "desk"]
            # The keep id was in the object list.
            assert body["requirement"]["must_keep_object_ids"] == ["kept-1"]
            # All six weights are present.
            assert set(body["requirement"]["objective_weights"]) == set(WEIGHT_NAMES)
            # One number, and no passage.
            assert body["retrieved"][0]["value_m"] == 0.9
            assert body["retrieved"][0]["source"] == "ada_2010"
            assert body["retrieved"][0]["page"] == 4
            assert body["retrieved"][0]["topic"] == "door"
            assert "text" not in body["retrieved"][0]
            # The named constant is still 0.815 m.
            constants = {item["name"]: item["value_m"] for item in body["solver_constants_m"]}
            assert constants["door_clear_width"] == MIN_DOOR_CLEAR_WIDTH_M
            # The note says retrieval ran.
            assert body["retrieval_note"] == "ok"
            # One attempt.
            assert body["attempts"] == 1
    # Restore the app.
    finally:
        # Drop overrides.
        app.dependency_overrides.clear()


# Two invalid replies become a 422 with the parser message.
def test_requirements_route_invalid_json_is_422() -> None:
    """The form can show the parser error. No requirement is returned."""
    # Both replies are invalid.
    app.dependency_overrides[get_chat_client] = lambda: ScriptedChat(["{", "{"])
    # The index would not be called after a parse failure, but override it anyway.
    app.dependency_overrides[get_hybrid_retriever] = lambda: FakeIndex()
    # Always clear overrides.
    try:
        # Client.
        with TestClient(app) as client:
            # Post a sentence.
            response = client.post(
                "/requirements",
                json={"scene_id": "room-1", "raw_text": "I need a desk."},
            )
            # Readable failure.
            assert response.status_code == 422
            # The detail names the budget.
            assert "2 attempts" in response.json()["detail"]
            # No requirement was invented.
            assert "requirement" not in response.json()
    # Restore the app.
    finally:
        # Drop overrides.
        app.dependency_overrides.clear()


# Unknown keys are rejected by the request model.
def test_requirements_route_rejects_extra_keys() -> None:
    """rating is not a requirement field."""
    # No model is needed. Validation fails first.
    with TestClient(app) as client:
        # Extra key.
        response = client.post(
            "/requirements",
            json={"scene_id": "room-1", "raw_text": "I need a desk.", "rating": 5},
        )
        # Schema rejection.
        assert response.status_code == 422
