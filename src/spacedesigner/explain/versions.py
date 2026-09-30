"""Append-only design diffs: items added, removed, and moved, plus cost and score."""

# timezone-aware timestamps match the version schema.
from datetime import datetime, timezone

# DesignVersion is the locked row shape.
from spacedesigner.schemas import Design, DesignVersion

# SceneObject is the placed-furniture record the diff compares.
from spacedesigner.schemas.scene import SceneObject


# Two poses match when the centre, rotation, and size are the same on the grid.
def _same_pose(before: SceneObject, after: SceneObject) -> bool:
    """Return True when the object did not move or resize."""
    # Centre x.
    same_x = abs(before.position[0] - after.position[0]) <= 1e-6
    # Centre y.
    same_y = abs(before.position[1] - after.position[1]) <= 1e-6
    # Rotation in degrees.
    same_rotation = abs(before.rotation - after.rotation) <= 1e-6
    # Length, width, and height.
    pairs = zip(before.dimensions, after.dimensions, strict=True)
    # Every edge matches.
    same_size = all(abs(left - right) <= 1e-6 for left, right in pairs)
    # All four must hold.
    return same_x and same_y and same_rotation and same_size


# One moved item, with both poses, so the UI can show the change without another lookup.
def _moved_entry(before: SceneObject, after: SceneObject) -> dict[str, object]:
    """Describe one object that stayed but changed pose."""
    # The object id is the identity. A new id is an add, not a move.
    return {
        # Stable id.
        "id": after.id,
        # Category, for the table.
        "type": after.type,
        # Previous centre.
        "from_position": [before.position[0], before.position[1]],
        # New centre.
        "to_position": [after.position[0], after.position[1]],
        # Previous rotation.
        "from_rotation": before.rotation,
        # New rotation.
        "to_rotation": after.rotation,
    }


# Diff of a design against an empty room: every object is an addition.
def initial_diff(design: Design) -> dict[str, object]:
    """Snapshot diff for version 1. Cost and score changes are zero."""
    # The five keys every version diff carries.
    return {
        # Every current object id, in design order.
        "items_added": [obj.id for obj in design.objects],
        # Nothing was removed from an empty parent.
        "items_removed": [],
        # Nothing moved.
        "items_moved": [],
        # No earlier cost.
        "cost_change": 0.0,
        # No earlier score.
        "score_change": 0.0,
    }


# Diff of two designs. Extra keys record the what-if parameters.
def change_diff(
    before: Design,
    after: Design,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    """Return added, removed, and moved object ids plus the cost and score deltas."""
    # Index the parent objects.
    before_by_id = {obj.id: obj for obj in before.objects}
    # Index the new objects.
    after_by_id = {obj.id: obj for obj in after.objects}
    # Ids that exist only after the what-if.
    added = [obj.id for obj in after.objects if obj.id not in before_by_id]
    # Ids that exist only before the what-if.
    removed = [obj.id for obj in before.objects if obj.id not in after_by_id]
    # Same id, different pose.
    moved = [
        _moved_entry(before_by_id[obj.id], obj)
        for obj in after.objects
        if obj.id in before_by_id and not _same_pose(before_by_id[obj.id], obj)
    ]
    # Required keys first.
    diff: dict[str, object] = {
        # New object ids.
        "items_added": added,
        # Dropped object ids.
        "items_removed": removed,
        # Pose changes.
        "items_moved": moved,
        # Rupee delta. Negative means the new design costs less.
        "cost_change": after.cost - before.cost,
        # Score delta. Negative means the new design scores lower.
        "score_change": after.score - before.score,
        # The design this diff was computed against.
        "parent_design_id": before.design_id,
        # The design this diff produced.
        "result_design_id": after.design_id,
    }
    # Budget, room size, occupants, and sensitivity ride along when the caller has them.
    if extra:
        # Copy so the caller's dict is not aliased into the row.
        diff.update(extra)
    # The JSON stored in design_versions.diff.
    return diff


# Version 1 for a design that has no rows yet.
def snapshot_version(design: Design, when: datetime | None = None) -> DesignVersion:
    """Build the initial version row. The caller inserts it."""
    # Stamp once.
    timestamp = when or datetime.now(timezone.utc)
    # Validate against the locked schema before the insert.
    return DesignVersion(
        design_id=design.design_id,
        scene_id=design.scene_id,
        version=1,
        parent_version=None,
        diff=initial_diff(design),
        score=design.score,
        timestamp=timestamp,
    )


# A later version on the same design id.
def next_version(
    design_id: str,
    scene_id: str,
    parent_version: int | None,
    version: int,
    diff: dict[str, object],
    score: float,
    when: datetime | None = None,
) -> DesignVersion:
    """Build one append-only row. The first version of a design has no parent version."""
    # Stamp once.
    timestamp = when or datetime.now(timezone.utc)
    # Validate before the insert.
    return DesignVersion(
        design_id=design_id,
        scene_id=scene_id,
        version=version,
        parent_version=parent_version,
        diff=diff,
        score=score,
        timestamp=timestamp,
    )
