"""Independent Shapely audit for Stage 1 designs."""

# math compares poses with stable floating-point tolerances.
import math

# Shapely constructs and intersects exact metric floor geometry.
from shapely.geometry import Point, Polygon, box

# Constants are data values only; this module never imports the CP-SAT model.
from spacedesigner.optimizer.constants import (
    LOW_CONFIDENCE_MARGIN_M,
    MIN_CIRCULATION_WIDTH_M,
    MIN_DOOR_CLEAR_WIDTH_M,
    TURNING_SPACE_DIAMETER_M,
)

# BOM lines expose independent accounting inputs.
from spacedesigner.optimizer.models import BomLine

# Locked schemas type every critic input.
from spacedesigner.schemas import Design, Requirement, SceneGraph, SceneObject

# Small area tolerance ignores boundary-only contact.
AREA_TOLERANCE = 1e-8

# Pose tolerance handles JSON floating-point round trips.
POSE_TOLERANCE = 1e-6


# Convert one scene object into its world-axis Shapely footprint.
def _footprint(obj: SceneObject) -> Polygon:
    """Build the exact axis-aligned floor rectangle."""
    # Normalize the rotation to a quarter turn.
    quarter_turn = round(obj.rotation / 90.0) % 4
    # Swap local edges for 90-degree and 270-degree poses.
    if quarter_turn in {1, 3}:
        # World x uses local width.
        extent_x = obj.dimensions[1]
        # World y uses local length.
        extent_y = obj.dimensions[0]
    # Keep local axes for zero and 180 degrees.
    else:
        # World x uses local length.
        extent_x = obj.dimensions[0]
        # World y uses local width.
        extent_y = obj.dimensions[1]
    # Build a rectangle from the centre and half extents.
    return box(
        obj.position[0] - extent_x / 2,
        obj.position[1] - extent_y / 2,
        obj.position[0] + extent_x / 2,
        obj.position[1] + extent_y / 2,
    )


# Build the exact inward approach rectangle for one wall opening.
def _opening_clearance(scene: SceneGraph, index: int) -> Polygon | None:
    """Return an opening's circulation keep-out rectangle."""
    # Select the opening by stable list index.
    opening = scene.openings[index]
    # Read the inward clearance depth.
    depth = MIN_CIRCULATION_WIDTH_M
    # Normalize wall spelling.
    wall = opening.wall.lower()
    # North extends down from the maximum y coordinate.
    if wall == "north":
        # Return the north-wall approach.
        return box(
            opening.position,
            max(0.0, scene.dimensions.width - depth),
            opening.position + opening.width,
            scene.dimensions.width,
        )
    # South extends up from zero y.
    if wall == "south":
        # Return the south-wall approach.
        return box(opening.position, 0.0, opening.position + opening.width, depth)
    # East extends left from the maximum x coordinate.
    if wall == "east":
        # Return the east-wall approach.
        return box(
            max(0.0, scene.dimensions.length - depth),
            opening.position,
            scene.dimensions.length,
            opening.position + opening.width,
        )
    # West extends right from zero x.
    if wall == "west":
        # Return the west-wall approach.
        return box(0.0, opening.position, depth, opening.position + opening.width)
    # Unsupported walls are reported separately by returning no geometry.
    return None


# Compare an output object with the immutable scene pose.
def _same_pose(actual: SceneObject, expected: SceneObject) -> bool:
    """Return whether every fixed pose field is unchanged."""
    # Compare positions component by component.
    positions_match = all(
        math.isclose(left, right, abs_tol=POSE_TOLERANCE)
        for left, right in zip(actual.position, expected.position, strict=True)
    )
    # Compare dimensions component by component.
    dimensions_match = all(
        math.isclose(left, right, abs_tol=POSE_TOLERANCE)
        for left, right in zip(actual.dimensions, expected.dimensions, strict=True)
    )
    # Compare rotation modulo one complete turn.
    rotation_match = math.isclose(
        (actual.rotation - expected.rotation) % 360.0,
        0.0,
        abs_tol=POSE_TOLERANCE,
    )
    # Include identity and category fields in fixed-pose semantics.
    return (
        positions_match
        and dimensions_match
        and rotation_match
        and actual.id == expected.id
        and actual.type == expected.type
    )


# Audit all Phase 3 hard constraints independently of CP-SAT.
def audit_design(
    scene: SceneGraph,
    requirement: Requirement,
    design: Design,
    bom: list[BomLine],
) -> list[str]:
    """Return one readable string per hard-constraint violation."""
    # Collect violations without short-circuiting the audit.
    violations: list[str] = []
    # Verify record linkage first.
    if design.scene_id != scene.scene_id:
        # Record scene mismatch.
        violations.append("design scene_id does not match scene")
    # Verify requirement linkage.
    if design.requirement_id != requirement.requirement_id:
        # Record requirement mismatch.
        violations.append("design requirement_id does not match requirement")
    # Apply the low-confidence wall inset independently.
    margin = LOW_CONFIDENCE_MARGIN_M if scene.dimensions.confidence.value == "low" else 0.0
    # Build the usable room polygon.
    usable_room = box(
        margin,
        margin,
        scene.dimensions.length - margin,
        scene.dimensions.width - margin,
    ).buffer(POSE_TOLERANCE)
    # Convert every output object to geometry.
    footprints = [_footprint(obj) for obj in design.objects]
    # Check each footprint against the usable room.
    for obj, footprint in zip(design.objects, footprints, strict=True):
        # Covers permits furniture boundaries to touch usable boundaries.
        if not usable_room.covers(footprint):
            # Name the object that escaped the room.
            violations.append(f"object '{obj.id}' is outside usable room bounds")
    # Audit every unordered furniture pair.
    for left_index, left in enumerate(footprints):
        # Compare only later objects.
        for right_index in range(left_index + 1, len(footprints)):
            # Measure true overlap area rather than boundary contact.
            if left.intersection(footprints[right_index]).area > AREA_TOLERANCE:
                # Name both colliding objects.
                violations.append(
                    f"objects '{design.objects[left_index].id}' and "
                    f"'{design.objects[right_index].id}' overlap"
                )
    # Check every opening and its approach clearance.
    for index, opening in enumerate(scene.openings):
        # Reject unsupported walls explicitly.
        clearance = _opening_clearance(scene, index)
        # A missing polygon means the rectangular frame cannot interpret the wall.
        if clearance is None:
            # Record the unsupported value.
            violations.append(f"opening {index} has unsupported wall '{opening.wall}'")
            # Continue with remaining openings.
            continue
        # Enforce the cited physical door width.
        if opening.type.lower() == "door" and opening.width < MIN_DOOR_CLEAR_WIDTH_M:
            # Record the measured narrow opening.
            violations.append(
                f"door opening {index} is narrower than {MIN_DOOR_CLEAR_WIDTH_M:.3f} m"
            )
        # Keep every furniture footprint out of the approach.
        for obj, footprint in zip(design.objects, footprints, strict=True):
            # Area intersection means the approach is blocked.
            if clearance.intersection(footprint).area > AREA_TOLERANCE:
                # Record both opening and object.
                violations.append(f"object '{obj.id}' blocks opening {index} clearance")
    # Build the complete required fixed-id set.
    required_ids = set(requirement.must_keep_object_ids)
    # Include must-keep flags embedded in the scene.
    required_ids.update(obj.id for obj in scene.objects if obj.must_keep)
    # Index both scene and output objects.
    scene_by_id = {obj.id: obj for obj in scene.objects}
    # Build output index.
    design_by_id = {obj.id: obj for obj in design.objects}
    # Check every required fixed object.
    for object_id in sorted(required_ids):
        # Missing source references are invalid requirements.
        if object_id not in scene_by_id:
            # Record the dangling reference.
            violations.append(f"must-keep object '{object_id}' is absent from scene")
        # Missing output references violate retention.
        elif object_id not in design_by_id:
            # Record the dropped object.
            violations.append(f"must-keep object '{object_id}' is absent from design")
        # Existing output objects must retain the exact pose.
        elif not _same_pose(design_by_id[object_id], scene_by_id[object_id]):
            # Record the moved object.
            violations.append(f"must-keep object '{object_id}' changed pose")
    # Gather output taxonomy categories.
    categories = {obj.type for obj in design.objects}
    # Check every hard required category.
    for category in sorted(set(requirement.must_have)):
        # Missing categories violate functionality.
        if category not in categories:
            # Record the category name.
            violations.append(f"required category '{category}' is absent")
    # Audit the accessible turning circle when requested.
    if requirement.accessibility_required:
        # Place the independently checked circle at room centre.
        turning_circle = Point(
            scene.dimensions.length / 2,
            scene.dimensions.width / 2,
        ).buffer(TURNING_SPACE_DIAMETER_M / 2)
        # Ensure the full circle lies in the usable room.
        if not usable_room.covers(turning_circle):
            # Record physical room insufficiency.
            violations.append(
                f"room cannot contain a {TURNING_SPACE_DIAMETER_M:.3f} m turning space"
            )
        # Ensure no output furniture blocks the circle.
        for obj, footprint in zip(design.objects, footprints, strict=True):
            # Positive area means the turning circle is obstructed.
            if turning_circle.intersection(footprint).area > AREA_TOLERANCE:
                # Name the obstructing object.
                violations.append(f"object '{obj.id}' blocks accessible turning space")
    # Enforce the hard budget against Design.
    if design.cost > requirement.budget_inr + POSE_TOLERANCE:
        # Record both values.
        violations.append(
            f"design cost INR {design.cost:.2f} exceeds budget INR {requirement.budget_inr:.2f}"
        )
    # Recompute cost from the independent BOM.
    bom_total = sum(line.line_total for line in bom)
    # Require exact accounting within floating-point tolerance.
    if not math.isclose(bom_total, design.cost, abs_tol=POSE_TOLERANCE):
        # Record the mismatch.
        violations.append(
            f"BOM total INR {bom_total:.2f} does not equal design cost INR {design.cost:.2f}"
        )
    # Return all observed hard failures.
    return violations
