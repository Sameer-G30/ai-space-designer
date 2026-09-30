"""Phase 11 metric tests. They do not call Ollama, the database, or the GPU."""

# A guessed layout and the live checker.
from spacedesigner.eval.ablation import (
    aggregate_layouts,
    clearance_gaps,
    design_from_guess,
    diff_matches,
    eligible_sun_rows,
    layout_messages,
    missing_categories,
    no_design_row,
    parse_layout_payload,
    rectangle_scene,
    row_is_clean,
    score_design,
    shortlist_items,
    sun_layout_rectangle,
    template_budget,
    template_requirement,
)

# Report text and the blank sheet.
from spacedesigner.eval.report import (
    answer_key,
    blind_assignment,
    rater_sheet,
    render_report,
    violation_svg,
)

# Version diff the what-if path already builds.
from spacedesigner.explain.versions import change_diff

# BOM for the guessed purchases.
from spacedesigner.optimizer.bom import build_bom

# Small fixtures.
from spacedesigner.schemas import CatalogItem

# Phase 3 rooms. Imported after the package so collection can see tests/.
from tests.phase3_samples import sample_catalog, sample_requirement, sample_scene


# A desk placed in the middle of the sample room is clean.
def test_guess_inside_the_room_has_no_violation() -> None:
    """Score one legal coordinate guess with the live checker."""
    # Room.
    scene = sample_scene()
    # Requirement.
    requirement = sample_requirement()
    # One catalog row.
    catalog = sample_catalog()
    # Centre of the 6 m room.
    payload = {"objects": [{"id": "test-desk", "x": 3.0, "y": 3.0, "rotation": 0}]}
    # Build the design.
    design, selected, notes = design_from_guess(payload, scene, requirement, list(catalog))
    # Nothing was skipped.
    assert notes == []
    # One purchase.
    assert len(selected) == 1
    # Score.
    row = score_design(scene, requirement, design, build_bom(selected))
    # No hard finding.
    assert row["violation_count"] == 0
    # Budget holds.
    assert row["budget_ok"] is True
    # The desk is present.
    assert row["must_have_rate"] == 1.0
    # Clean.
    assert row_is_clean(row) is True


# A centre on the wall leaves the footprint outside.
def test_guess_outside_the_room_is_a_violation() -> None:
    """The checker flags a footprint that crosses the wall."""
    # Room.
    scene = sample_scene()
    # Requirement.
    requirement = sample_requirement()
    # Catalog.
    catalog = sample_catalog()
    # Too close to the origin for a 0.8 m desk.
    payload = {"objects": [{"id": "test-desk", "x": 0.1, "y": 0.1, "rotation": 0}]}
    # Build.
    design, selected, _notes = design_from_guess(payload, scene, requirement, list(catalog))
    # Score.
    row = score_design(scene, requirement, design, build_bom(selected))
    # At least the bounds finding.
    assert row["violation_count"] >= 1
    # Not clean.
    assert row_is_clean(row) is False


# Moving a kept chair is a must-keep failure.
def test_moved_must_keep_lowers_the_keep_rate() -> None:
    """A guessed pose that is not the scene pose fails must-keep."""
    # Room with a fixed chair.
    scene = sample_scene(with_fixed=True)
    # Keep that chair and also buy a desk.
    requirement = sample_requirement(keep_fixed=True)
    # Desk row.
    catalog = list(sample_catalog())
    # Chair moved, desk legal.
    payload = {
        "objects": [
            {"id": "fixed-chair", "x": 1.0, "y": 1.0, "rotation": 0},
            {"id": "test-desk", "x": 3.0, "y": 3.0, "rotation": 0},
        ]
    }
    # Build.
    design, selected, _notes = design_from_guess(payload, scene, requirement, catalog)
    # Score.
    row = score_design(scene, requirement, design, build_bom(selected))
    # The keep is not intact.
    assert row["must_keep_rate"] == 0.0
    # The desk is still there.
    assert row["must_have_rate"] == 1.0


# Unknown ids are skipped.
def test_unknown_catalog_id_is_not_invented() -> None:
    """A made-up id does not become a catalog purchase."""
    # Room.
    scene = sample_scene()
    # Requirement.
    requirement = sample_requirement()
    # Real row, unused by the payload.
    catalog = list(sample_catalog())
    # Unknown id.
    payload = {"objects": [{"id": "not-a-real-item", "x": 3.0, "y": 3.0, "rotation": 0}]}
    # Build.
    design, selected, notes = design_from_guess(payload, scene, requirement, catalog)
    # No purchase.
    assert selected == []
    # No object.
    assert design.objects == []
    # The skip is noted.
    assert notes


# The prompt names the keep id and does not include an extra retrieved number.
def test_layout_prompt_omits_retrieved_numbers() -> None:
    """Retrieved clearances are not part of the coordinate-guess prompt."""
    # Room with a fixed chair.
    scene = sample_scene(with_fixed=True)
    # Keep it.
    requirement = sample_requirement(keep_fixed=True)
    # No new category, because the chair covers must-have chair... requirement is a desk.
    shortlist = list(sample_catalog())
    # Messages.
    messages = layout_messages(scene, requirement, shortlist)
    # User text.
    user = messages[1]["content"]
    # The keep id is present.
    assert "fixed-chair" in user
    # A number that was never a solver constant is absent.
    assert "9.999" not in user
    # Bad JSON is rejected.
    try:
        # A list is not a layout object.
        parse_layout_payload("[]")
    # Expected.
    except ValueError as exc:
        # Stable reason.
        assert "objects" in str(exc)


# Cheapest row comes first.
def test_shortlist_orders_by_price_then_id() -> None:
    """The first row is the cheapest, matching the Stage 1 sort key."""
    # Two desks.
    cheap = sample_catalog(price=100.0)[0]
    # Dearer desk.
    dear = CatalogItem.model_validate(
        {
            "item_id": "test-desk-dear",
            "category": "desk",
            "dims": {"length": 0.8, "width": 0.5, "height": 0.75},
            "price": 500.0,
            "style_tags": ["modern"],
            "material": "solid_wood",
        }
    )
    # Shortlist.
    chosen = shortlist_items((dear, cheap), ["desk"], per_category=1)
    # Cheapest.
    assert chosen[0].item_id == cheap.item_id


# A kept chair removes that category from the purchase list.
def test_missing_categories_skip_a_kept_type() -> None:
    """Must-have chair is not missing when the chair is must-keep."""
    # Fixed chair.
    scene = sample_scene(with_fixed=True)
    # Chair is both required and kept. Desk is only required.
    requirement = sample_requirement(category="chair", keep_fixed=True)
    # The chair is already kept, so nothing is missing.
    assert missing_categories(scene, requirement) == []


# No design is not a clean room. A clean room and a no-design room average to one half.
def test_aggregate_counts_no_design_as_not_clean() -> None:
    """Clean rate uses every room, not only returned designs."""
    # One clean returned row.
    clean = {
        "returned": True,
        "violation_count": 0,
        "budget_ok": True,
        "must_have_rate": 1.0,
        "must_keep_rate": None,
        "utilization": 0.2,
        "free_floor": 0.8,
        "clearance_clean": True,
        "kinds": [],
    }
    # One refusal.
    missing = no_design_row("no placement")
    # Aggregate.
    summary = aggregate_layouts([clean, missing])
    # Two rooms.
    assert summary["rooms"] == 2
    # One design.
    assert summary["returned"] == 1
    # Violation rate among returned designs is zero.
    assert summary["violation_rate"] == 0.0
    # Clean rate over both rooms is one half.
    assert summary["clean_rate"] == 0.5


# A square floor becomes a 4 m by 3 m room.
def test_sun_rectangle_accepts_a_plausible_floor() -> None:
    """Shapely's minimum rectangle recovers the axis-aligned floor."""
    # One floor polygon and a ceiling height.
    payload = {
        "objects": [
            {
                "polygon": [
                    {
                        "X": [0, 4, 4, 0],
                        "Z": [0, 0, 3, 3],
                        "Ymin": 0.0,
                        "Ymax": 2.5,
                    }
                ]
            }
        ]
    }
    # Rectangle.
    length, width, height = sun_layout_rectangle(payload)
    # Long side.
    assert abs(length - 4.0) < 1e-6
    # Short side.
    assert abs(width - 3.0) < 1e-6
    # Height.
    assert height == 2.5


# A tiny room is dropped.
def test_sun_rectangle_rejects_a_short_side() -> None:
    """A sub-metre side is not a room for this ladder."""
    # 0.4 m square.
    payload = {
        "objects": [
            {
                "polygon": [
                    {"X": [0, 0.4, 0.4, 0], "Z": [0, 0, 0.4, 0.4], "Ymin": 0, "Ymax": 2.5}
                ]
            }
        ]
    }
    # Unusable.
    assert sun_layout_rectangle(payload) is None


# Manifest filter.
def test_eligible_sun_rows_skip_nyu_twins_and_other_splits() -> None:
    """Only non-NYU test rows with a template room type are eligible."""
    # Mixed rows.
    rows = [
        {"id": "b", "split": "test", "has_test_geometry": True, "room_type": "bedroom"},
        {
            "id": "a",
            "split": "test",
            "has_test_geometry": True,
            "room_type": "bedroom",
            "overlaps_nyu_depth_v2": True,
        },
        {"id": "c", "split": "train", "has_test_geometry": True, "room_type": "bedroom"},
        {"id": "d", "split": "test", "has_test_geometry": True, "room_type": "kitchen"},
    ]
    # One row, sorted by id.
    chosen = eligible_sun_rows(rows)
    # Only b.
    assert [row["id"] for row in chosen] == ["b"]


# Template budget and requirement stay on the locked schema.
def test_template_requirement_matches_the_scene() -> None:
    """The real-room template validates and names the scene."""
    # Two prices.
    catalog = sample_catalog(category="bed", price=8000.0)
    # Budget.
    budget = template_budget(catalog, ("bed",))
    # At least the rounded floor.
    assert budget >= 5000
    # Scene.
    scene = rectangle_scene("sun_00001", "bedroom", 4.0, 3.0, 2.5)
    # Requirement. Bedroom wants a bed and a nightstand, so use home_office's caller...
    # template_requirement looks up REAL_MUST_HAVE, which needs both categories in the
    # budget helper only. The requirement itself does not price them.
    requirement = template_requirement("sun_00001", "home_office", 20000.0)
    # Same id.
    assert requirement.scene_id == scene.scene_id
    # Desk and chair.
    assert requirement.must_have == ["desk", "chair"]
    # High confidence. The annotation is not a depth estimate.
    assert scene.dimensions.confidence.value == "high"
    # No openings, so this test does not pretend a door was seen.
    assert scene.openings == []


# Retrieved numbers are compared and never marked applied.
def test_clearance_gap_is_not_applied() -> None:
    """A different door width is recorded as a gap and not applied."""
    # One mapped number and one unmapped number.
    gaps = clearance_gaps([("door_clear_width", 0.9), ("seat_height", 0.45)])
    # Door differs from 0.815 m.
    assert gaps[0]["differs"] is True
    # Not applied.
    assert gaps[0]["applied"] is False
    # Seat height is not a solver constant.
    assert gaps[1]["solver_constant"] is None
    # Still not applied.
    assert gaps[1]["applied"] is False


# Diff helper agrees with the version module.
def test_diff_matches_the_version_diff() -> None:
    """A diff built by change_diff matches the two designs."""
    # Room.
    scene = sample_scene()
    # Requirement.
    requirement = sample_requirement()
    # Catalog.
    catalog = list(sample_catalog())
    # First pose.
    before, selected, _notes = design_from_guess(
        {"objects": [{"id": "test-desk", "x": 3.0, "y": 3.0, "rotation": 0}]},
        scene,
        requirement,
        catalog,
    )
    # Second pose. Same objects, so the diff has a move or equal poses.
    after, _selected, _notes = design_from_guess(
        {"objects": [{"id": "test-desk", "x": 3.2, "y": 3.0, "rotation": 0}]},
        scene,
        requirement,
        catalog,
    )
    # The purchase was used.
    assert selected
    # Existing diff.
    diff = change_diff(before, after)
    # The helper agrees.
    assert diff_matches(before, after, diff) is True


# The report cites the limitation and does not invent a preference score.
def test_report_states_the_limitation_and_leaves_scores_blank() -> None:
    """The markdown names the tape-measure limit and a blank preference sheet."""
    # Minimal summary.
    text = render_report(
        {
            "seed": 20261001,
            "synthetic_rooms": 1,
            "sun_rooms": 1,
            "rungs": [{"step": 1, "name": "parsing", "text": "Not a RoomGPT call."}],
            "preference": {"pairs": 0, "collected": False},
            "not_run": ["RoomGPT was not called."],
            "parser": {"status": "not_run", "reason": "test"},
            "rag": {"status": "not_run", "reason": "test"},
        }
    )
    # Limitation.
    assert "tape-measured" in text
    # Prior numbers are labelled.
    assert "Previously recorded" in text
    # Phase 9 is not promoted to a large set.
    assert "one image" in text
    # Preference was not collected.
    assert "not collected" in text
    # Sheet.
    sheet = rater_sheet([{"pair": 1, "scene_id": "syn", "left": "cp_sat", "right": "llm"}])
    # Blank collection flag.
    assert "Scores collected: no." in sheet
    # The choice cell is empty. The header is the only place those words appear as labels.
    assert "| 1 | pairs/pair_01_a.png | pairs/pair_01_b.png |  |  |  |" in sheet
    # Key has methods and no score column.
    key = answer_key([{"pair": 1, "scene_id": "syn", "left": "cp_sat", "right": "llm"}])
    # Methods.
    assert "cp_sat" in key
    # No filled choice.
    assert "tie" not in key


# Blinding is deterministic and uses only the two methods.
def test_blind_assignment_is_stable() -> None:
    """The same seed puts the same method on the left."""
    # Two draws.
    first = blind_assignment(20261001, ["room-a", "room-b"])
    # Again.
    second = blind_assignment(20261001, ["room-a", "room-b"])
    # Same.
    assert first == second
    # Legal labels.
    assert {first[0]["left"], first[0]["right"]} == {"cp_sat", "llm"}


# The plot names a series.
def test_violation_svg_contains_the_label() -> None:
    """The SVG is a document and includes the series name."""
    # One bar.
    svg = violation_svg([("synth CP-SAT", 0.25), ("synth LLM", None)])
    # Document.
    assert svg.startswith("<svg")
    # Label.
    assert "synth CP-SAT" in svg
    # Clipped value text.
    assert "0.250" in svg
