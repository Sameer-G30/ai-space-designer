"""HTTP models for POST /requirements. The locked Requirement schema is nested, not changed."""

# Annotations on Python 3.11.
from __future__ import annotations

# Field expresses the non-empty id rule.
from pydantic import Field

# SchemaModel rejects keys that are not in the contract.
from spacedesigner.schemas.base import SchemaModel

# The locked requirement, validated before it is returned.
from spacedesigner.schemas.requirement import Requirement


# One existing scene object the sentence may ask to keep.
class ObjectRef(SchemaModel):
    """Id and type only. The must-keep flag is not sent, so the parser cannot copy it."""

    # Scene-object id.
    id: str = Field(min_length=1)
    # Taxonomy class name as the form stored it.
    type: str = Field(min_length=1)


# Body accepted by POST /requirements.
class ParseRequest(SchemaModel):
    """Sentence plus the scene it belongs to."""

    # Scene the user is editing. Copied onto the requirement.
    scene_id: str = Field(min_length=1)
    # The sentence they typed.
    raw_text: str = Field(min_length=1)
    # Optional id. The form sends requirement-{scene_id}.
    requirement_id: str | None = None
    # Existing objects, used only to resolve must-keep ids.
    objects: list[ObjectRef] = Field(default_factory=list)


# One clearance or ergonomic number taken from a retrieved chunk.
class RetrievedNumber(SchemaModel):
    """A number with its chunk source. The chunk prose is not included."""

    # Short label such as door_clear_width or turning_space.
    name: str = Field(min_length=1)
    # Value converted to metres.
    value_m: float
    # ada_2010, mohua_2021, or a summary source id.
    source: str = Field(min_length=1)
    # PDF page, or null for a project summary.
    page: int | None
    # Topic stored on the chunk.
    topic: str = Field(min_length=1)
    # Chunk primary key, so the number can be traced without quoting the text.
    chunk_id: str = Field(min_length=1)


# One named solver constant, recorded unchanged beside the parse.
class SolverConstant(SchemaModel):
    """A constant from optimizer/constants.py. This phase does not edit it."""

    # Constant name.
    name: str = Field(min_length=1)
    # Value in metres.
    value_m: float


# Successful parse body.
class ParseResponse(SchemaModel):
    """Validated requirement, retrieved numbers, and the unchanged solver constants."""

    # Schema-valid requirement. scene_id and raw_text come from the request.
    requirement: Requirement
    # Numbers from the reranked chunks. Empty when retrieval finds none.
    retrieved: list[RetrievedNumber]
    # The five named constants, copied, not replaced.
    solver_constants_m: list[SolverConstant]
    # ok, or why the retrieved list is empty.
    retrieval_note: str
    # Model calls used, including the successful one.
    attempts: int
