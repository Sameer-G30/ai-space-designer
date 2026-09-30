"""Fusion and number extraction. No database and no model weights."""

# Fusion helper.
# Named door constant, read to show extraction does not replace it.
from spacedesigner.optimizer.constants import MIN_DOOR_CLEAR_WIDTH_M
from spacedesigner.rag.hybrid import ChunkHit, reciprocal_rank_fusion

# Extraction. The result has no passage text.
from spacedesigner.rag.numbers import extract_clearances


# A document in both lists outranks a document in only one.
def test_reciprocal_rank_fusion_prefers_overlap() -> None:
    """b is in both rankings, so it sorts first."""
    # Two rankings.
    fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]])
    # Overlap wins.
    assert fused[0] == "b"
    # Stable tie break is not needed for these scores.
    assert fused == ["b", "a", "c"]


# Original sentences, not copied from the standards PDFs.
def test_extract_clearances_returns_metres_and_source_only() -> None:
    """Numbers are converted and the passage is not part of the result."""
    # One hit whose text is written for this test.
    hit = ChunkHit(
        chunk_id="chunk-1",
        source="ada_2010",
        page=12,
        topic="door",
        text="A walking surface needs 915 mm. A door opening is 900 mm. Turning space is 1.525 m.",
        score=1.0,
    )
    # Extract.
    numbers = extract_clearances([hit])
    # Three room-scale numbers.
    assert len(numbers) == 3
    # Names follow the words in front of each number.
    assert [item.name for item in numbers] == ["clear_width", "door_clear_width", "turning_space"]
    # 915 mm, 900 mm, and 1.525 m.
    assert [item.value_m for item in numbers] == [0.915, 0.9, 1.525]
    # Source fields are copied.
    assert numbers[1].source == "ada_2010"
    assert numbers[1].page == 12
    assert numbers[1].topic == "door"
    assert numbers[1].chunk_id == "chunk-1"
    # The result object has no text attribute.
    assert not hasattr(numbers[1], "text")
    # The named solver constant is still the ADA door width, not the 900 mm test value.
    assert MIN_DOOR_CLEAR_WIDTH_M == 0.815


# A huge distance is not a furniture clearance.
def test_extract_skips_values_outside_room_scale() -> None:
    """61 m is outside the clearance range and is dropped."""
    # One oversized number and one clearance.
    hit = ChunkHit(
        chunk_id="chunk-2",
        source="summary_ada_clearances",
        page=None,
        topic="clear_width",
        text="A passing space is required every 61 m. Door clear width is 32 inches.",
        score=0.5,
    )
    # Extract.
    numbers = extract_clearances([hit])
    # Only the door width remains.
    assert len(numbers) == 1
    # 32 inches is 0.813 m at millimetre rounding.
    assert numbers[0].value_m == 0.813
    # The name comes from the word door.
    assert numbers[0].name == "door_clear_width"
    # Summaries have no page.
    assert numbers[0].page is None
