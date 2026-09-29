"""Persistence boundary for Phase 3 API routes."""

# Protocol defines the dependency-overridable store contract.
from typing import Protocol

# Session provides one transactional SQLAlchemy unit of work.
from sqlalchemy.orm import Session

# Existing rows match the locked Phase 0 database schema.
from spacedesigner.db.models import DesignRow, RequirementRow, SceneRow

# The shared engine remains lazy until a route performs persistence.
from spacedesigner.db.session import get_engine

# Locked schemas validate values crossing the persistence boundary.
from spacedesigner.schemas import Design, Requirement, SceneGraph


# Route-facing storage contract implemented by Postgres and test fakes.
class DesignStore(Protocol):
    """Define only the operations Phase 3 routes require."""

    # Save or replace one manual scene graph.
    def save_scene(self, scene: SceneGraph) -> None:
        """Persist one scene."""

    # Load a scene by its public identifier.
    def get_scene(self, scene_id: str) -> SceneGraph | None:
        """Return a persisted scene when present."""

    # Save the gold requirement and one feasible design atomically.
    def save_design(self, requirement: Requirement, design: Design) -> None:
        """Persist one successful optimization."""


# PostgreSQL implementation using the existing tables and no migration.
class PostgresDesignStore:
    """Persist Phase 3 records with short transactions."""

    # Save the complete validated scene JSON fields.
    def save_scene(self, scene: SceneGraph) -> None:
        """Upsert one scene graph."""
        # Open one session bound to the lazy shared engine.
        with Session(get_engine()) as session, session.begin():
            # Merge supports repeatable manual corrections by scene id.
            session.merge(
                SceneRow(
                    scene_id=scene.scene_id,
                    version=scene.version,
                    room_type=scene.room_type,
                    dimensions=scene.dimensions.model_dump(mode="json"),
                    openings=[opening.model_dump(mode="json") for opening in scene.openings],
                    objects=[obj.model_dump(mode="json") for obj in scene.objects],
                    confidence=None,
                )
            )

    # Rehydrate one row into the locked scene schema.
    def get_scene(self, scene_id: str) -> SceneGraph | None:
        """Load and validate one scene graph."""
        # Open a read-only unit of work.
        with Session(get_engine()) as session:
            # Fetch directly by primary key.
            row = session.get(SceneRow, scene_id)
            # Return no value for an unknown scene.
            if row is None:
                # Signal not found to the route.
                return None
            # Reassemble and validate the public contract.
            return SceneGraph.model_validate(
                {
                    "scene_id": row.scene_id,
                    "version": row.version,
                    "room_type": row.room_type,
                    "dimensions": row.dimensions,
                    "openings": row.openings,
                    "objects": row.objects,
                }
            )

    # Store the dependent requirement before the design in one transaction.
    def save_design(self, requirement: Requirement, design: Design) -> None:
        """Persist one successful optimization atomically."""
        # Open one transactional session.
        with Session(get_engine()) as session, session.begin():
            # Serialize all structured fields except row columns.
            structured = requirement.model_dump(
                mode="json",
                exclude={"requirement_id", "scene_id", "raw_text"},
            )
            # Upsert the validated requirement.
            session.merge(
                RequirementRow(
                    requirement_id=requirement.requirement_id,
                    scene_id=requirement.scene_id,
                    raw_text=requirement.raw_text,
                    structured=structured,
                )
            )
            # Upsert the one Stage 1 design.
            session.merge(
                DesignRow(
                    design_id=design.design_id,
                    scene_id=design.scene_id,
                    requirement_id=design.requirement_id,
                    weights=design.weights.model_dump(mode="json"),
                    score=design.score,
                    cost=design.cost,
                    objects=[obj.model_dump(mode="json") for obj in design.objects],
                    parent_design_id=design.parent_design_id,
                )
            )


# FastAPI dependency factory kept replaceable in unit tests.
def get_design_store() -> DesignStore:
    """Return the production PostgreSQL store."""
    # Construct a stateless store wrapper.
    return PostgresDesignStore()
