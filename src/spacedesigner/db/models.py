"""SQLAlchemy models for blueprint section 38 and the design_versions table."""

# datetime is the Python type for timestamp columns.
from datetime import datetime

# Any is the value type for JSON payloads whose keys are not fixed yet.
from typing import Any

# VECTOR is pgvector's unbounded vector type.
from pgvector.sqlalchemy import VECTOR

# Column types and the foreign-key helper.
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func

# JSONB stores the structured documents from the blueprint sketch.
from sqlalchemy.dialects.postgresql import JSONB

# Mapped and mapped_column declare typed columns.
from sqlalchemy.orm import Mapped, mapped_column

# Base carries the metadata Alembic inspects.
from spacedesigner.db.base import Base


# One persisted scene graph.
class SceneRow(Base):
    """Row in the scenes table."""

    # Table name from blueprint section 38.
    __tablename__ = "scenes"
    # Primary key for the room.
    scene_id: Mapped[str] = mapped_column(String, primary_key=True)
    # Current scene-graph version stored on this row.
    version: Mapped[int] = mapped_column(nullable=False)
    # Room category.
    room_type: Mapped[str] = mapped_column(String, nullable=False)
    # Room dimensions object, including its confidence.
    dimensions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Door and window list.
    openings: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    # Object list.
    objects: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    # Optional summary of nested confidence values. Writers arrive in a later phase.
    confidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Time the row was inserted.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


# One persisted requirement.
class RequirementRow(Base):
    """Row in the requirements table."""

    # Table name from blueprint section 38.
    __tablename__ = "requirements"
    # Primary key for the requirement.
    requirement_id: Mapped[str] = mapped_column(String, primary_key=True)
    # Scene the requirement belongs to.
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.scene_id"), nullable=False)
    # Original user text.
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Structured constraint fields from the requirement schema.
    structured: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


# One persisted candidate design.
class DesignRow(Base):
    """Row in the designs table."""

    # Table name from blueprint section 38.
    __tablename__ = "designs"
    # Primary key for the design.
    design_id: Mapped[str] = mapped_column(String, primary_key=True)
    # Scene the design was solved against.
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.scene_id"), nullable=False)
    # Requirement the design was solved against.
    requirement_id: Mapped[str] = mapped_column(
        ForeignKey("requirements.requirement_id"),
        nullable=False,
    )
    # Objective weights used for this candidate.
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Combined objective score.
    score: Mapped[float] = mapped_column(Float, nullable=False)
    # Total cost in Indian rupees.
    cost: Mapped[float] = mapped_column(Float, nullable=False)
    # Placed objects.
    objects: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    # Earlier design this row was derived from, if any.
    parent_design_id: Mapped[str | None] = mapped_column(
        ForeignKey("designs.design_id"),
        nullable=True,
    )


# One furniture catalog item.
class CatalogItemRow(Base):
    """Row in the furniture_catalog table."""

    # Table name from blueprint section 38.
    __tablename__ = "furniture_catalog"
    # Primary key for the catalog item.
    item_id: Mapped[str] = mapped_column(String, primary_key=True)
    # Taxonomy category.
    category: Mapped[str] = mapped_column(String, nullable=False)
    # Length, width, and height.
    dims: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Price in Indian rupees.
    price: Mapped[float] = mapped_column(Float, nullable=False)
    # Style labels.
    style_tags: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    # Primary material.
    material: Mapped[str] = mapped_column(String, nullable=False)
    # Embedding with no fixed length, until a later phase chooses a model.
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR(), nullable=True)


# One chunk of the retrieval corpus.
class RagChunkRow(Base):
    """Row in the rag_chunks table."""

    # Table name from blueprint section 38.
    __tablename__ = "rag_chunks"
    # Primary key for the chunk.
    chunk_id: Mapped[str] = mapped_column(String, primary_key=True)
    # Document or standard this chunk came from.
    source: Mapped[str] = mapped_column(String, nullable=False)
    # Chunk text.
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Embedding with no fixed length, until a later phase chooses a model.
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR(), nullable=True)
    # Source metadata such as page and topic. The column name stays metadata.
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False)


# One explanation claim attached to a design.
class ExplanationRow(Base):
    """Row in the explanations table."""

    # Table name from blueprint section 38.
    __tablename__ = "explanations"
    # Surrogate key, because one design can have many claims.
    explanation_id: Mapped[str] = mapped_column(String, primary_key=True)
    # Design this claim explains.
    design_id: Mapped[str] = mapped_column(ForeignKey("designs.design_id"), nullable=False)
    # Sentence or claim text.
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Pointer back into the optimizer trace that supports the claim.
    supporting_trace_ref: Mapped[str] = mapped_column(String, nullable=False)
    # Whether the faithfulness check accepted the claim.
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False)


# One append-only design version.
class DesignVersionRow(Base):
    """Row in the design_versions table."""

    # Table name requested for blueprint section 25.
    __tablename__ = "design_versions"
    # Design this version belongs to. Part of the primary key.
    design_id: Mapped[str] = mapped_column(
        ForeignKey("designs.design_id"),
        primary_key=True,
    )
    # Version number within that design. Part of the primary key.
    version: Mapped[int] = mapped_column(primary_key=True)
    # Scene this version belongs to.
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.scene_id"), nullable=False)
    # Previous version number, empty for the first version.
    parent_version: Mapped[int | None] = mapped_column(nullable=True)
    # Diff payload. Its keys are defined in a later phase.
    diff: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Score stored with this version.
    score: Mapped[float] = mapped_column(Float, nullable=False)
    # Time this version was recorded.
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
