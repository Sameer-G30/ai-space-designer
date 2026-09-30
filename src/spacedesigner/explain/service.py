"""Load stored designs, explain them, re-solve what-ifs, and append version diffs."""

# Catalog default is the tracked JSONL. Tests pass a smaller catalog.
# Store contract. The new methods are on the same store the other routes use.
from spacedesigner.api.store import DesignStore

# Feasible what-if payload, including the diff to store.
from spacedesigner.explain.counterfactual import prepare_counterfactual

# HTTP-shaped failures.
from spacedesigner.explain.errors import ExplainError

# Facts are recomputed on every read so the sources stay tied to the trace.
from spacedesigner.explain.facts import build_facts

# Hints module raises ValueError for a missing catalog row.
from spacedesigner.explain.models import (
    CounterfactualDesign,
    CounterfactualRequest,
    CounterfactualResult,
    ExplanationClaim,
    ExplanationResponse,
    VersionsResponse,
)

# Replay builds the trace the template reads.
from spacedesigner.explain.recover import recover_optimization

# Phrase, or keep the template when the model does not answer.
from spacedesigner.explain.rephrase import RephraseClient, phrase_claims

# Version rows.
from spacedesigner.explain.versions import next_version, snapshot_version
from spacedesigner.optimizer.catalog import load_catalog

# Style scores for the aesthetics term. CLIP weights are not loaded here.
from spacedesigner.recommend.scoring import StyleScorer

# Locked design, used when the version snapshot is written.
from spacedesigner.schemas import CatalogItem, Design


# verified claims divided by all claims. An empty list is treated as fully verified.
def _rate(claims: list[ExplanationClaim]) -> float:
    """Return the faithfulness rate for one claim list."""
    # Nothing to check.
    if not claims:
        # Vacuous success.
        return 1.0
    # Count the claims the checker accepted.
    verified = sum(1 for claim in claims if claim.verified)
    # Fraction in the unit interval.
    return verified / len(claims)


# True when the stored sentences are not a verbatim copy of the facts.
def _rephrased(claims: list[ExplanationClaim], facts_text: list[str]) -> bool:
    """Detect a stored model reply. An exact copy of the facts counts as the template."""
    # A different count means the model did not echo the template.
    if len(claims) != len(facts_text):
        # Treat it as a rephrase.
        return True
    # Any edited sentence means the model rephrased.
    return any(claim.claim_text != text for claim, text in zip(claims, facts_text, strict=True))


# Sensitivity stored on this design's own versions, not on a parent's later what-if rows.
def _sensitivity(store: DesignStore, design: Design) -> float | None:
    """Return the newest score-per-rupee value stored for this design, if any."""
    # A design with no parent was not produced by a what-if.
    if design.parent_design_id is None:
        # No sensitivity fact.
        return None
    # Walk newest first.
    for version in reversed(store.list_versions(design.design_id)):
        # The counterfactual diff stores the by-product under this key.
        value = version.diff.get("sensitivity_score_per_inr")
        # Booleans are ints in Python and are not a sensitivity.
        if isinstance(value, bool):
            # Skip.
            continue
        # A real number is the stored sensitivity.
        if isinstance(value, (int, float)):
            # Use it.
            return float(value)
    # This counterfactual did not change the budget.
    return None


# Load the three rows a design points at, or raise a 404.
def _load(store: DesignStore, design_id: str) -> tuple:
    """Return (design, scene, requirement)."""
    # The design row.
    design = store.get_design(design_id)
    # Unknown id.
    if design is None:
        # The route maps this to HTTP 404.
        raise ExplainError(404, "design not found")
    # The scene the design was solved against.
    scene = store.get_scene(design.scene_id)
    # A design whose scene was removed cannot be replayed.
    if scene is None:
        # Not found.
        raise ExplainError(404, "scene not found")
    # The requirement, which holds the budget the design was solved under.
    requirement = store.get_requirement(design.requirement_id)
    # A missing requirement cannot be replayed.
    if requirement is None:
        # Not found.
        raise ExplainError(404, "requirement not found")
    # All three.
    return design, scene, requirement


# Write version 1 when a design has no versions yet.
def _ensure_snapshot(store: DesignStore, design: Design) -> None:
    """Insert the initial snapshot once."""
    # Existing rows mean version 1 is already there.
    if store.list_versions(design.design_id):
        # Nothing to insert.
        return
    # Append-only insert of version 1.
    store.append_version(snapshot_version(design))


# Persist a feasible what-if and append the diff on the parent and the child.
def _persist(store: DesignStore, parent: Design, result: CounterfactualDesign, requirement) -> None:
    """Save the scene, the requirement, the design, and the version rows."""
    # A room-size change uses a new scene id and must be stored before the design.
    if result.scene.scene_id != parent.scene_id:
        # Insert or replace that scene id. It is not the parent's scene.
        store.save_scene(result.scene)
    # Requirement and design share one transaction in the PostgreSQL store.
    store.save_design(requirement, result.design)
    # Parent version 1, so the what-if can be version 2.
    _ensure_snapshot(store, parent)
    # Rows currently stored for the parent.
    parent_rows = store.list_versions(parent.design_id)
    # Skip a second click that produced the same child design.
    already = any(
        row.diff.get("result_design_id") == result.design.design_id for row in parent_rows
    )
    # First time this child is recorded on the parent.
    if not already:
        # The snapshot is the last row when nothing else has been appended.
        last = parent_rows[-1]
        # Version number is one past the last stored version.
        store.append_version(
            next_version(
                design_id=parent.design_id,
                scene_id=parent.scene_id,
                parent_version=last.version,
                version=last.version + 1,
                diff=result.diff,
                score=result.design.score,
            )
        )
    # The child gets version 1 holding the same diff, so its own versions route shows the change.
    if not store.list_versions(result.design.design_id):
        # First version of the new design. Its parent version is empty.
        store.append_version(
            next_version(
                design_id=result.design.design_id,
                scene_id=result.scene.scene_id,
                parent_version=None,
                version=1,
                diff=result.diff,
                score=result.design.score,
            )
        )


# Explain one stored design. The first call phrases and stores. Later calls reuse the claims.
def build_explanation(
    store: DesignStore,
    design_id: str,
    scorer: StyleScorer,
    chat: RephraseClient | None,
    catalog: tuple[CatalogItem, ...] | None = None,
) -> ExplanationResponse:
    """Return templated facts and the stored claims for one design."""
    # Design, scene, and requirement, or a 404.
    design, scene, requirement = _load(store, design_id)
    # The tracked catalog unless a test passed a smaller one.
    active_catalog = load_catalog() if catalog is None else catalog
    # Replay can fail when the catalog row or the placement cannot be reproduced.
    try:
        # Trace from the same placer the design was built with.
        recovered = recover_optimization(scene, requirement, design, active_catalog, scorer)
    # Missing catalog row or an infeasible replay.
    except ValueError as exc:
        # The client can show this. Nothing is stored.
        raise ExplainError(422, str(exc)) from None
    # Object ids must match, otherwise the trace is for a different layout.
    if [obj.id for obj in recovered.design.objects] != [obj.id for obj in design.objects]:
        # Refuse to explain a layout we could not replay.
        raise ExplainError(422, "stored design could not be replayed")
    # Centres must match the stored design, within a tenth of a millimetre.
    for stored, replayed in zip(design.objects, recovered.design.objects, strict=True):
        # X centre.
        moved_x = abs(stored.position[0] - replayed.position[0]) > 1e-4
        # Y centre.
        moved_y = abs(stored.position[1] - replayed.position[1]) > 1e-4
        # A drifted replay is not this design.
        if moved_x or moved_y:
            # Refuse.
            raise ExplainError(422, "stored design could not be replayed")
    # Sensitivity is quoted only for a what-if design that changed the budget.
    sensitivity = _sensitivity(store, design)
    # Sources. These are recomputed even when the claims are already stored.
    facts = build_facts(design, recovered.trace, sensitivity)
    # Claims already written for this design.
    stored_claims = store.list_explanations(design_id)
    # First explanation phrases, or copies the template when the model is down.
    if not stored_claims:
        # Phrase. A failing model still returns verified template claims.
        claims, rephrased, note = phrase_claims(design_id, facts, chat)
        # Replace any empty set with these claims.
        store.save_explanations(design_id, claims)
    # Later reads do not call the model again.
    else:
        # Keep the stored sentences.
        claims = stored_claims
        # An exact copy of the current facts is the template path.
        rephrased = _rephrased(claims, [fact.text for fact in facts])
        # Note for the page.
        note = "stored claims" if rephrased else "template only"
    # Facts, claims, and the rate.
    return ExplanationResponse(
        design_id=design_id,
        facts=facts,
        claims=claims,
        verified_rate=_rate(claims),
        rephrased=rephrased,
        rephrase_note=note,
    )


# Re-solve one what-if and, when it is feasible, append the version diff.
def run_counterfactual(
    store: DesignStore,
    design_id: str,
    request: CounterfactualRequest,
    scorer: StyleScorer,
    catalog: tuple[CatalogItem, ...] | None = None,
) -> CounterfactualResult:
    """Warm-start a solve from the stored design and persist a feasible result."""
    # Design, scene, and requirement, or a 404.
    design, scene, requirement = _load(store, design_id)
    # The tracked catalog unless a test passed a smaller one.
    active_catalog = load_catalog() if catalog is None else catalog
    # Selection and hint building can fail on a missing catalog row.
    try:
        # Hints on. The evaluation script calls prepare_counterfactual directly for the cold path.
        prepared = prepare_counterfactual(
            scene,
            requirement,
            design,
            request,
            active_catalog,
            scorer,
            use_hints=True,
        )
    # A catalog id in the design is no longer in the catalog.
    except ValueError as exc:
        # Client error.
        raise ExplainError(422, str(exc)) from None
    # A feasible design is stored. A rejection leaves the tables unchanged.
    if isinstance(prepared.result, CounterfactualDesign):
        # The requirement is present whenever the result is feasible.
        if prepared.requirement is None:
            # Internal: a feasible result without a requirement cannot be stored.
            raise ExplainError(422, "counterfactual requirement was not built")
        # Scene, design, and version rows.
        _persist(store, design, prepared.result, prepared.requirement)
    # The public union.
    return prepared.result


# List versions, writing the initial snapshot the first time a design is asked about.
def list_design_versions(store: DesignStore, design_id: str) -> VersionsResponse:
    """Return the append-only versions for one design."""
    # The design must exist. Scenes and requirements are not required for the snapshot.
    design = store.get_design(design_id)
    # Unknown id.
    if design is None:
        # HTTP 404.
        raise ExplainError(404, "design not found")
    # Write version 1 once.
    _ensure_snapshot(store, design)
    # Read back in version order.
    versions = store.list_versions(design_id)
    # The response.
    return VersionsResponse(design_id=design_id, versions=versions)
