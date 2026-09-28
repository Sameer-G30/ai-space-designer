"""Create the Phase 0 tables from blueprint sections 25 and 38.

Revision ID: c550d1f16744
Revises:
Create Date: 2026-09-28 23:30:40.768477

"""

# Sequence and Union type the revision pointers Alembic stores.
from collections.abc import Sequence

# SQLAlchemy column types used to build the tables.
import sqlalchemy as sa

# Alembic operation helper.
from alembic import op

# VECTOR renders the unbounded pgvector column type.
from pgvector.sqlalchemy import VECTOR

# JSONB renders the PostgreSQL JSON columns.
from sqlalchemy.dialects import postgresql

# Revision id stored in alembic_version after this migration runs.
revision: str = "c550d1f16744"
# This is the first migration, so nothing comes before it.
down_revision: str | Sequence[str] | None = None
# This revision is not a branch point.
branch_labels: str | Sequence[str] | None = None
# This revision does not depend on another branch.
depends_on: str | Sequence[str] | None = None


# Create the extension and the seven foundation tables.
def upgrade() -> None:
    """Create the Phase 0 schema."""
    # Install pgvector before any vector column is created.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Catalog items, with an embedding column whose length is not fixed yet.
    op.create_table(
        "furniture_catalog",
        # Primary key for the item.
        sa.Column("item_id", sa.String(), nullable=False),
        # Taxonomy category.
        sa.Column("category", sa.String(), nullable=False),
        # Length, width, and height.
        sa.Column("dims", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        # Price in Indian rupees.
        sa.Column("price", sa.Float(), nullable=False),
        # Style labels.
        sa.Column("style_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        # Primary material.
        sa.Column("material", sa.String(), nullable=False),
        # Optional embedding.
        sa.Column("embedding", VECTOR(), nullable=True),
        # Primary key constraint.
        sa.PrimaryKeyConstraint("item_id"),
    )
    # Retrieval chunks, with an embedding column whose length is not fixed yet.
    op.create_table(
        "rag_chunks",
        # Primary key for the chunk.
        sa.Column("chunk_id", sa.String(), nullable=False),
        # Document this chunk came from.
        sa.Column("source", sa.String(), nullable=False),
        # Chunk text.
        sa.Column("text", sa.Text(), nullable=False),
        # Optional embedding.
        sa.Column("embedding", VECTOR(), nullable=True),
        # Source metadata such as page and topic.
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        # Primary key constraint.
        sa.PrimaryKeyConstraint("chunk_id"),
    )
    # Scene graphs.
    op.create_table(
        "scenes",
        # Primary key for the room.
        sa.Column("scene_id", sa.String(), nullable=False),
        # Current scene-graph version.
        sa.Column("version", sa.Integer(), nullable=False),
        # Room category.
        sa.Column("room_type", sa.String(), nullable=False),
        # Room dimensions, including confidence.
        sa.Column("dimensions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        # Doors and windows.
        sa.Column("openings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        # Objects in the room.
        sa.Column("objects", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        # Optional confidence summary. Nested confidence stays inside the JSON.
        sa.Column("confidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Insertion time.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Primary key constraint.
        sa.PrimaryKeyConstraint("scene_id"),
    )
    # Requirements, each tied to one scene.
    op.create_table(
        "requirements",
        # Primary key for the requirement.
        sa.Column("requirement_id", sa.String(), nullable=False),
        # Scene this requirement belongs to.
        sa.Column("scene_id", sa.String(), nullable=False),
        # Original user text.
        sa.Column("raw_text", sa.Text(), nullable=False),
        # Structured constraint fields.
        sa.Column("structured", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        # Foreign key back to scenes.
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.scene_id"]),
        # Primary key constraint.
        sa.PrimaryKeyConstraint("requirement_id"),
    )
    # Candidate designs.
    op.create_table(
        "designs",
        # Primary key for the design.
        sa.Column("design_id", sa.String(), nullable=False),
        # Scene the design was solved against.
        sa.Column("scene_id", sa.String(), nullable=False),
        # Requirement the design was solved against.
        sa.Column("requirement_id", sa.String(), nullable=False),
        # Objective weights used for this candidate.
        sa.Column("weights", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        # Combined objective score.
        sa.Column("score", sa.Float(), nullable=False),
        # Total cost in Indian rupees.
        sa.Column("cost", sa.Float(), nullable=False),
        # Placed objects.
        sa.Column("objects", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        # Earlier design this row was derived from, if any.
        sa.Column("parent_design_id", sa.String(), nullable=True),
        # Self foreign key for the parent design.
        sa.ForeignKeyConstraint(["parent_design_id"], ["designs.design_id"]),
        # Foreign key back to requirements.
        sa.ForeignKeyConstraint(["requirement_id"], ["requirements.requirement_id"]),
        # Foreign key back to scenes.
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.scene_id"]),
        # Primary key constraint.
        sa.PrimaryKeyConstraint("design_id"),
    )
    # Append-only design versions from blueprint section 25, plus design_id.
    op.create_table(
        "design_versions",
        # Design this version belongs to.
        sa.Column("design_id", sa.String(), nullable=False),
        # Version number within that design.
        sa.Column("version", sa.Integer(), nullable=False),
        # Scene this version belongs to.
        sa.Column("scene_id", sa.String(), nullable=False),
        # Previous version number, empty for the first version.
        sa.Column("parent_version", sa.Integer(), nullable=True),
        # Diff payload. Its keys are defined in a later phase.
        sa.Column("diff", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        # Score stored with this version.
        sa.Column("score", sa.Float(), nullable=False),
        # Time this version was recorded.
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        # Foreign key back to designs.
        sa.ForeignKeyConstraint(["design_id"], ["designs.design_id"]),
        # Foreign key back to scenes.
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.scene_id"]),
        # One row per design and version number.
        sa.PrimaryKeyConstraint("design_id", "version"),
    )
    # Explanation claims. explanation_id exists because one design has many claims.
    op.create_table(
        "explanations",
        # Surrogate primary key.
        sa.Column("explanation_id", sa.String(), nullable=False),
        # Design this claim explains.
        sa.Column("design_id", sa.String(), nullable=False),
        # Claim text.
        sa.Column("claim_text", sa.Text(), nullable=False),
        # Pointer back into the optimizer trace.
        sa.Column("supporting_trace_ref", sa.String(), nullable=False),
        # Whether the faithfulness check accepted the claim.
        sa.Column("verified", sa.Boolean(), nullable=False),
        # Foreign key back to designs.
        sa.ForeignKeyConstraint(["design_id"], ["designs.design_id"]),
        # Primary key constraint.
        sa.PrimaryKeyConstraint("explanation_id"),
    )


# Drop the tables and the extension this migration created.
def downgrade() -> None:
    """Remove the Phase 0 schema."""
    # Drop children before parents.
    op.drop_table("explanations")
    # Drop versions before designs.
    op.drop_table("design_versions")
    # Drop designs before requirements and scenes.
    op.drop_table("designs")
    # Drop requirements before scenes.
    op.drop_table("requirements")
    # Drop scenes after every table that references them.
    op.drop_table("scenes")
    # Retrieval chunks do not reference the other tables.
    op.drop_table("rag_chunks")
    # Catalog items do not reference the other tables.
    op.drop_table("furniture_catalog")
    # Remove the extension this migration installed.
    op.execute("DROP EXTENSION IF EXISTS vector")
