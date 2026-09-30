"""Persistence boundary for Phase 3 API routes."""

# Protocol defines the dependency-overridable store contract.
from typing import Protocol

# delete and select support explanation replacement and version reads.
from sqlalchemy import delete, select

# Session provides one transactional SQLAlchemy unit of work.
from sqlalchemy.orm import Session

# Existing rows match the locked Phase 0 database schema.
from spacedesigner.db.models import (
    DesignRow,
    DesignVersionRow,
    ExplanationRow,
    RequirementRow,
    SceneRow,
)

# The shared engine remains lazy until a route performs persistence.
from spacedesigner.db.session import get_engine

# Explanation claims are Phase 8 rows. The model does not import this store.
from spacedesigner.explain.models import ExplanationClaim

# Locked schemas validate values crossing the persistence boundary.
from spacedesigner.schemas import Design, DesignVersion, Requirement, SceneGraph


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

    # Load one design by its public identifier.
    def get_design(self, design_id: str) -> Design | None:
        """Return a persisted design when present."""

    # Load one requirement by its public identifier.
    def get_requirement(self, requirement_id: str) -> Requirement | None:
        """Return a persisted requirement when present."""

    # Replace the explanation claims stored for one design.
    def save_explanations(self, design_id: str, claims: list[ExplanationClaim]) -> None:
        """Replace explanation rows for one design."""

    # Read the explanation claims stored for one design.
    def list_explanations(self, design_id: str) -> list[ExplanationClaim]:
        """Return explanation rows in identifier order."""

    # Insert one version when that version number is not already stored.
    def append_version(self, version: DesignVersion) -> None:
        """Insert one design version. An existing primary key is left unchanged."""

    # Read every version of one design.
    def list_versions(self, design_id: str) -> list[DesignVersion]:
        """Return versions in ascending version order."""


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

    # Rehydrate one design row into the locked schema.
    def get_design(self, design_id: str) -> Design | None:
        """Load and validate one design."""
        # Open a read-only unit of work.
        with Session(get_engine()) as session:
            # Fetch directly by primary key.
            row = session.get(DesignRow, design_id)
            # Unknown design.
            if row is None:
                # Signal not found.
                return None
            # Rebuild the public contract, including a null parent.
            return Design.model_validate(
                {
                    "design_id": row.design_id,
                    "scene_id": row.scene_id,
                    "requirement_id": row.requirement_id,
                    "weights": row.weights,
                    "score": row.score,
                    "cost": row.cost,
                    "objects": row.objects,
                    "parent_design_id": row.parent_design_id,
                }
            )

    # Rehydrate one requirement row. The structured column omits the three identity fields.
    def get_requirement(self, requirement_id: str) -> Requirement | None:
        """Load and validate one requirement."""
        # Open a read-only unit of work.
        with Session(get_engine()) as session:
            # Fetch directly by primary key.
            row = session.get(RequirementRow, requirement_id)
            # Unknown requirement.
            if row is None:
                # Signal not found.
                return None
            # Identity columns plus the structured payload.
            payload = {
                "requirement_id": row.requirement_id,
                "scene_id": row.scene_id,
                "raw_text": row.raw_text,
                **row.structured,
            }
            # Validate the locked contract.
            return Requirement.model_validate(payload)

    # Replace every claim for one design in a single transaction.
    def save_explanations(self, design_id: str, claims: list[ExplanationClaim]) -> None:
        """Delete previous claims for this design and insert the new ones."""
        # Open one transactional session.
        with Session(get_engine()) as session, session.begin():
            # Drop the previous claims so a second explanation does not duplicate them.
            session.execute(delete(ExplanationRow).where(ExplanationRow.design_id == design_id))
            # Insert the new claims in list order. The identifier already sorts that way.
            for claim in claims:
                # One row per claim.
                session.add(
                    ExplanationRow(
                        explanation_id=claim.explanation_id,
                        design_id=design_id,
                        claim_text=claim.claim_text,
                        supporting_trace_ref=claim.supporting_trace_ref,
                        verified=claim.verified,
                    )
                )

    # Read claims back in identifier order, which is the fact order.
    def list_explanations(self, design_id: str) -> list[ExplanationClaim]:
        """Return the stored claims for one design."""
        # Open a read-only unit of work.
        with Session(get_engine()) as session:
            # Identifier order matches the 0000, 0001 suffixes.
            rows = session.scalars(
                select(ExplanationRow)
                .where(ExplanationRow.design_id == design_id)
                .order_by(ExplanationRow.explanation_id)
            ).all()
            # Validate each row.
            return [
                ExplanationClaim(
                    explanation_id=row.explanation_id,
                    claim_text=row.claim_text,
                    supporting_trace_ref=row.supporting_trace_ref,
                    verified=row.verified,
                )
                for row in rows
            ]

    # Insert a version only when its primary key is new. Existing rows are not updated.
    def append_version(self, version: DesignVersion) -> None:
        """Insert one version row, or leave an existing row untouched."""
        # Open one transactional session.
        with Session(get_engine()) as session, session.begin():
            # Composite primary key.
            existing = session.get(DesignVersionRow, (version.design_id, version.version))
            # Append-only: a repeated version number does not overwrite the diff.
            if existing is not None:
                # Keep the stored row.
                return
            # Insert the new version.
            session.add(
                DesignVersionRow(
                    design_id=version.design_id,
                    version=version.version,
                    scene_id=version.scene_id,
                    parent_version=version.parent_version,
                    diff=version.diff,
                    score=version.score,
                    timestamp=version.timestamp,
                )
            )

    # Read versions in ascending version order.
    def list_versions(self, design_id: str) -> list[DesignVersion]:
        """Return every stored version of one design."""
        # Open a read-only unit of work.
        with Session(get_engine()) as session:
            # Version order, not insertion order.
            rows = session.scalars(
                select(DesignVersionRow)
                .where(DesignVersionRow.design_id == design_id)
                .order_by(DesignVersionRow.version)
            ).all()
            # Validate each row, including the timezone-aware timestamp.
            return [
                DesignVersion.model_validate(
                    {
                        "design_id": row.design_id,
                        "scene_id": row.scene_id,
                        "version": row.version,
                        "parent_version": row.parent_version,
                        "diff": row.diff,
                        "score": row.score,
                        "timestamp": row.timestamp,
                    }
                )
                for row in rows
            ]


# FastAPI dependency factory kept replaceable in unit tests.
def get_design_store() -> DesignStore:
    """Return the production PostgreSQL store."""
    # Construct a stateless store wrapper.
    return PostgresDesignStore()
