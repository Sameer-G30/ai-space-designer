"""Phase 8 routes with an in-memory store and a scripted chat client."""

# json builds the scripted model reply.
import json

# TestClient calls the routes without a live server.
from fastapi.testclient import TestClient

# Application and dependency keys.
from spacedesigner.api.main import app
from spacedesigner.api.store import get_design_store

# Claim type stored by the fake.
from spacedesigner.explain.models import ExplanationClaim

# Scorer override. The real cache is not required.
from spacedesigner.optimizer.catalog import load_catalog
from spacedesigner.recommend.scoring import load_style_scorer
from spacedesigner.recommend.service import get_style_scorer

# Chat override so the route does not call Ollama.
from spacedesigner.requirements.ollama_client import get_chat_client

# Locked records the fake store keeps.
from spacedesigner.schemas import Design, DesignVersion, Requirement

# The Phase 3 memory store, extended with the Phase 8 methods.
from tests.api.test_phase3_routes import MemoryStore

# Fixtures.
from tests.phase3_samples import sample_requirement, sample_scene
from tests.recommend.fakes import FakeEmbedder


# In-memory store that can explain a design saved by POST /designs/optimize.
class ExplainMemory(MemoryStore):
    """Add design, explanation, and version maps on top of the Phase 3 fake."""

    # Empty maps.
    def __init__(self) -> None:
        """Create the Phase 3 maps plus the Phase 8 maps."""
        # Scenes and the saved-pair list.
        super().__init__()
        # Designs by id.
        self.designs: dict[str, Design] = {}
        # Requirements by id.
        self.requirements: dict[str, Requirement] = {}
        # Claims by design id.
        self.explanations: dict[str, list[ExplanationClaim]] = {}
        # Versions by design id.
        self.versions: dict[str, list[DesignVersion]] = {}

    # Index the pair the optimize route writes.
    def save_design(self, requirement: Requirement, design: Design) -> None:
        """Store the pair and index both records."""
        # Keep the Phase 3 list assertion working.
        super().save_design(requirement, design)
        # Index the requirement.
        self.requirements[requirement.requirement_id] = requirement
        # Index the design.
        self.designs[design.design_id] = design

    # Read one design.
    def get_design(self, design_id: str) -> Design | None:
        """Return a stored design."""
        # Missing ids return None.
        return self.designs.get(design_id)

    # Read one requirement.
    def get_requirement(self, requirement_id: str) -> Requirement | None:
        """Return a stored requirement."""
        # Missing ids return None.
        return self.requirements.get(requirement_id)

    # Replace claims.
    def save_explanations(self, design_id: str, claims: list[ExplanationClaim]) -> None:
        """Store the claim list for one design."""
        # Replace.
        self.explanations[design_id] = list(claims)

    # Read claims.
    def list_explanations(self, design_id: str) -> list[ExplanationClaim]:
        """Return the stored claims."""
        # A missing design has an empty list, matching a SQL query.
        return list(self.explanations.get(design_id, []))

    # Append a version unless that number already exists.
    def append_version(self, version: DesignVersion) -> None:
        """Insert one version and keep the list ordered."""
        # Rows for this design.
        rows = self.versions.setdefault(version.design_id, [])
        # Do not overwrite.
        if any(row.version == version.version for row in rows):
            # Leave the stored row.
            return
        # Append.
        rows.append(version)
        # Keep version order.
        rows.sort(key=lambda row: row.version)

    # Read versions.
    def list_versions(self, design_id: str) -> list[DesignVersion]:
        """Return a copy of the version list."""
        # Missing designs have no rows.
        return list(self.versions.get(design_id, []))


# A chat client that echoes the fact lines back as sentences.
class EchoChat:
    """Rephrase by repeating the facts, which the checker accepts."""

    # Two-argument complete, so the route's optional token cap falls back to this.
    def complete(self, messages: list[dict[str, str]], schema: dict) -> str:
        """Return the fact lines as a sentences array."""
        # The user message is the fact list.
        text = messages[-1]["content"]
        # Bullets only.
        sentences = [line[2:].strip() for line in text.splitlines() if line.startswith("- ")]
        # JSON object.
        return json.dumps({"sentences": sentences})


# A chat client that invents a price.
class InventChat:
    """Return one sentence with a number that is not in the trace."""

    # Two-argument complete.
    def complete(self, messages: list[dict[str, str]], schema: dict) -> str:
        """Return an invented cost."""
        # One sentence. The schema is ignored on purpose.
        return json.dumps({"sentences": ["The catalog cost is INR 999999.99."]})


# Optimize the sample room and return the client, the store, and the first design id.
def _solve(store: ExplainMemory, chat: object, tmp_path) -> TestClient:
    """Install overrides and return a client. The caller clears the overrides."""
    # Deterministic scorer.
    scorer = load_style_scorer(load_catalog(), FakeEmbedder(), tmp_path / "c.npz", ("modern",))
    # Store, scorer, and chat.
    app.dependency_overrides[get_design_store] = lambda: store
    app.dependency_overrides[get_style_scorer] = lambda: scorer
    app.dependency_overrides[get_chat_client] = lambda: chat
    # The caller owns the client context.
    return TestClient(app)


# Post the sample scene and solve it. Return the first design id.
def _optimize(client: TestClient) -> str:
    """Store the sample scene and return one feasible design id."""
    # Scene.
    scene_response = client.post("/scenes", json=sample_scene().model_dump(mode="json"))
    # Stored.
    assert scene_response.status_code == 200
    # Solve.
    optimize_response = client.post(
        "/designs/optimize",
        json={
            "scene_id": "scene-phase3",
            "requirement": sample_requirement().model_dump(mode="json"),
        },
    )
    # Feasible set.
    assert optimize_response.status_code == 200
    # Body.
    payload = optimize_response.json()
    # The sample room is feasible.
    assert payload["feasible"] is True
    # First design id.
    return payload["points"][0]["design"]["design_id"]


# Echoed facts verify. A what-if appends a version diff. Versions are readable.
def test_explanation_counterfactual_and_versions(tmp_path) -> None:
    """Solve, explain, run one budget what-if, and read both version lists."""
    # Store.
    store = ExplainMemory()
    # Overrides.
    client = _solve(store, EchoChat(), tmp_path)
    # Always clear overrides.
    try:
        # Enter the client.
        with client:
            # Design id.
            design_id = _optimize(client)
            # Explain.
            explanation = client.get(f"/designs/{design_id}/explanation")
            # Stored.
            assert explanation.status_code == 200
            # Body.
            body = explanation.json()
            # Facts are the sources.
            assert body["facts"]
            # Every echoed claim verified.
            assert body["verified_rate"] == 1.0
            assert all(claim["verified"] is True for claim in body["claims"])
            # A fact mentions the catalog cost.
            assert any(fact["ref"] == "design.cost" for fact in body["facts"])
            # What-if: raise the budget.
            counter = client.post(
                f"/designs/{design_id}/counterfactual",
                json={"budget_inr": 11000},
            )
            # Accepted.
            assert counter.status_code == 200
            # Body.
            created = counter.json()
            # Feasible.
            assert created["feasible"] is True
            # Warm start passed the desk hint.
            assert created["warm_started"] is True
            assert created["hint_count"] >= 1
            # Sensitivity is present because the budget changed.
            assert created["sensitivity_score_per_inr"] is not None
            # Diff keys the UI reads.
            diff_keys = (
                "items_added",
                "items_removed",
                "items_moved",
                "cost_change",
                "score_change",
            )
            # Each required key.
            for key in diff_keys:
                # The diff the page renders must include it.
                assert key in created["diff"]
            # Child id.
            child_id = created["design"]["design_id"]
            # Parent versions: snapshot plus the what-if.
            parent_versions = client.get(f"/designs/{design_id}/versions")
            # Readable.
            assert parent_versions.status_code == 200
            # Two rows.
            parent_rows = parent_versions.json()["versions"]
            assert [row["version"] for row in parent_rows] == [1, 2]
            # Version 2 points at the child and carries the same cost delta.
            assert parent_rows[1]["diff"]["result_design_id"] == child_id
            assert parent_rows[1]["diff"]["cost_change"] == created["cost_change"]
            # Child versions: one row, the change diff.
            child_versions = client.get(f"/designs/{child_id}/versions")
            # Readable.
            assert child_versions.status_code == 200
            # One row.
            child_rows = child_versions.json()["versions"]
            assert len(child_rows) == 1
            assert child_rows[0]["version"] == 1
            assert child_rows[0]["parent_version"] is None
            # The child diff names the parent.
            assert child_rows[0]["diff"]["parent_design_id"] == design_id
            # The child design can be explained from its own stored requirement.
            child_explanation = client.get(f"/designs/{child_id}/explanation")
            # Stored.
            assert child_explanation.status_code == 200
            # The echoed facts verify, including a sensitivity sentence when the budget changed.
            assert child_explanation.json()["verified_rate"] == 1.0
    # Clear even on failure.
    finally:
        # Drop overrides.
        app.dependency_overrides.clear()


# An invented price is stored with verified false.
def test_invented_claim_is_not_verified(tmp_path) -> None:
    """The checker rejects a model sentence whose price is not in the trace."""
    # Store.
    store = ExplainMemory()
    # Overrides with the inventing client.
    client = _solve(store, InventChat(), tmp_path)
    # Clear later.
    try:
        # Client.
        with client:
            # Solve.
            design_id = _optimize(client)
            # Explain.
            explanation = client.get(f"/designs/{design_id}/explanation")
            # The route still returns 200. The claim is flagged.
            assert explanation.status_code == 200
            # Body.
            body = explanation.json()
            # The model did answer.
            assert body["rephrased"] is True
            # The invented price fails.
            assert body["claims"][0]["verified"] is False
            assert body["verified_rate"] == 0.0
    # Clear.
    finally:
        # Drop overrides.
        app.dependency_overrides.clear()


# Unknown ids are 404. An empty what-if is 422.
def test_missing_design_and_empty_counterfactual(tmp_path) -> None:
    """404 for an unknown design, and 422 when the what-if body has no change."""
    # Empty store.
    store = ExplainMemory()
    # Overrides. The chat is unused.
    client = _solve(store, EchoChat(), tmp_path)
    # Clear later.
    try:
        # Client.
        with client:
            # Unknown explanation.
            missing = client.get("/designs/missing-design/explanation")
            # Not found.
            assert missing.status_code == 404
            # Unknown versions.
            missing_versions = client.get("/designs/missing-design/versions")
            # Not found.
            assert missing_versions.status_code == 404
            # Unknown what-if.
            missing_counter = client.post(
                "/designs/missing-design/counterfactual",
                json={"budget_inr": 1000},
            )
            # Not found.
            assert missing_counter.status_code == 404
            # Solve so a real design exists for the empty-body check.
            design_id = _optimize(client)
            # No parameter.
            empty = client.post(f"/designs/{design_id}/counterfactual", json={})
            # Validation error.
            assert empty.status_code == 422
    # Clear.
    finally:
        # Drop overrides.
        app.dependency_overrides.clear()
