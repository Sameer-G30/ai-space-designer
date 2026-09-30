"""Parse a sentence and attach retrieved numbers. Solver constants are copied, not edited."""

# Annotations on Python 3.11.
from __future__ import annotations

# Named geometry constants. This module only reads them.
from spacedesigner.optimizer.constants import (
    GRID_SIZE_M,
    LOW_CONFIDENCE_MARGIN_M,
    MIN_CIRCULATION_WIDTH_M,
    MIN_DOOR_CLEAR_WIDTH_M,
    TURNING_SPACE_DIAMETER_M,
)

# Empty-index and driver failures.
from spacedesigner.rag.hybrid import ChunkHit, HybridRetriever, RetrievalUnavailable

# Number extraction. The passage stays out of the response.
from spacedesigner.rag.numbers import extract_clearances

# HTTP models.
from spacedesigner.requirements.models import (
    ParseRequest,
    ParseResponse,
    RetrievedNumber,
    SolverConstant,
)

# Chat contract.
from spacedesigner.requirements.parser import ChatClient, parse_requirement

# Added to the user sentence so a style-only request still retrieves clearances.
STANDARDS_QUERY = (
    "accessible clear width door opening turning space knee clearance ergonomic seat height"
)

# The five named constants, in a stable order, copied from the optimizer module.
SOLVER_CONSTANTS: tuple[tuple[str, float], ...] = (
    ("grid", GRID_SIZE_M),
    ("low_confidence_margin", LOW_CONFIDENCE_MARGIN_M),
    ("circulation", MIN_CIRCULATION_WIDTH_M),
    ("door_clear_width", MIN_DOOR_CLEAR_WIDTH_M),
    ("turning_space", TURNING_SPACE_DIAMETER_M),
)


# Requirement id when the client does not send one.
def default_requirement_id(scene_id: str) -> str:
    """Match the form, which uses requirement-{scene id}."""
    # Prefix the scene id.
    return f"requirement-{scene_id}"


# Copy the named constants into response objects.
def solver_constant_models() -> list[SolverConstant]:
    """Return the unchanged constants for the response."""
    # One model per constant.
    return [SolverConstant(name=name, value_m=value) for name, value in SOLVER_CONSTANTS]


# Search, then extract numbers. Failures become a note, not a lost parse.
def retrieve_numbers(
    sentence: str, retriever: HybridRetriever
) -> tuple[list[RetrievedNumber], str]:
    """Return (numbers, note). The note is ok or a readable reason the list is empty."""
    # The sentence plus the standards terms.
    query = f"{sentence} {STANDARDS_QUERY}"
    # Hits from the index.
    try:
        # Top 5 after the top-20 rerank.
        hits: list[ChunkHit] = retriever.search(query, limit=5)
    # Empty index or a hidden driver error.
    except RetrievalUnavailable as exc:
        # No numbers. The requirement is still returned.
        return [], str(exc)
    # A model-load failure must not discard the parsed requirement or leak a URL.
    except Exception:
        # Stable note.
        return [], "The standards index could not be read."
    # Extract structured numbers. Passages are not copied out.
    numbers = extract_clearances(hits)
    # Explain an empty extraction.
    if not numbers:
        # The search ran.
        return [], "ok; no clearance numbers in the top chunks"
    # Convert to the HTTP model.
    models = [
        RetrievedNumber(
            name=item.name,
            value_m=item.value_m,
            source=item.source,
            page=item.page,
            topic=item.topic,
            chunk_id=item.chunk_id,
        )
        for item in numbers
    ]
    # Search and extraction both ran.
    return models, "ok"


# The route body.
def parse_and_retrieve(
    request: ParseRequest,
    client: ChatClient,
    retriever: HybridRetriever,
) -> ParseResponse:
    """Validate a requirement and attach retrieved numbers and the unchanged constants."""
    # Id from the form, or the same default the form uses.
    requirement_id = request.requirement_id or default_requirement_id(request.scene_id)
    # Object pairs for the prompt. The must-keep flag is not included.
    objects = [(item.id, item.type) for item in request.objects]
    # Model call, retries, and Pydantic. ParserFailure propagates to the route.
    requirement, attempts = parse_requirement(
        request.raw_text,
        request.scene_id,
        requirement_id,
        objects,
        client,
    )
    # Retrieval is best-effort beside the parse.
    retrieved, note = retrieve_numbers(request.raw_text, retriever)
    # One response. Constants are the module values, not the retrieved numbers.
    return ParseResponse(
        requirement=requirement,
        retrieved=retrieved,
        solver_constants_m=solver_constant_models(),
        retrieval_note=note,
        attempts=attempts,
    )
