"""Parser tests with a scripted chat client. No Ollama process is required."""

# JSON replies.
import json

# Locked requirement, used to confirm the examples validate.
from spacedesigner.requirements.errors import ParserFailure

# Field comparison.
from spacedesigner.requirements.metrics import SCORED_FIELDS, field_matches, micro_accuracy

# Assemble, examples, and the retry loop.
from spacedesigner.requirements.parser import (
    assemble_requirement,
    few_shot_messages,
    parse_requirement,
)

# Weight names for a complete object.
from spacedesigner.requirements.vocab import WEIGHT_NAMES


# Replies in order. Each complete() call consumes one.
class ScriptedChat:
    """Stand-in for Ollama."""

    # Store the scripted strings.
    def __init__(self, replies: list[str]) -> None:
        """Keep the replies and a call counter."""
        # Remaining replies.
        self._replies = list(replies)
        # How many times the parser called the model.
        self.calls = 0

    # Return the next scripted answer.
    def complete(self, messages: list[dict[str, str]], schema: dict) -> str:
        """Pop one reply. schema is accepted and ignored."""
        # Count the attempt.
        self.calls += 1
        # The schema is part of the contract even when unused.
        assert "properties" in schema
        # The prompt is non-empty.
        assert messages
        # Next scripted string.
        return self._replies.pop(0)


# A schema-shaped extract. Extra keys are included so the assembler must ignore them.
def extract_json(**overrides: object) -> str:
    """Build one model reply."""
    # Baseline that passes the closed lists.
    payload: dict[str, object] = {
        # Rupees.
        "budget_inr": 80000,
        # Unsorted on purpose. The assembler sorts them.
        "must_have": ["desk", "chair"],
        # Nothing kept.
        "must_keep_object_ids": [],
        # One person.
        "occupant_count": 1,
        # A generator style.
        "style": "modern",
        # No wheelchair line.
        "accessibility_required": False,
        # All six weights at 1.
        "objective_weights": {name: 1 for name in WEIGHT_NAMES},
        # The model must not be able to override the scene.
        "scene_id": "wrong-scene",
    }
    # Test-specific changes.
    payload.update(overrides)
    # One JSON string.
    return json.dumps(payload)


# The two few-shot JSON objects assemble into locked Requirement values.
def test_few_shot_examples_are_schema_valid() -> None:
    """The examples in the prompt must themselves validate."""
    # User, assistant, user, assistant.
    messages = few_shot_messages()
    # First assistant JSON.
    first = json.loads(messages[1]["content"])
    # Objects named in that example.
    objects = [("home_obj_01", "chair"), ("home_obj_02", "desk")]
    # Assemble with server-owned identity fields.
    requirement = assemble_requirement(first, "scene-1", "sentence one", "req-1", objects)
    # The kept desk id survived.
    assert requirement.must_keep_object_ids == ["home_obj_02"]
    # Style is a generator word.
    assert requirement.style == "modern"
    # Second assistant JSON.
    second = json.loads(messages[3]["content"])
    # No objects in that example.
    other = assemble_requirement(second, "scene-2", "sentence two", "req-2", [])
    # Spaced style word was already the token in the example.
    assert other.style == "mid_century"
    # Wheelchair sentence.
    assert other.accessibility_required is True
    # Three classes, sorted by the assembler.
    assert other.must_have == ["coffee_table", "lamp", "sofa"]


# Spaced class and style words are canonicalized before validation.
def test_spaced_words_map_onto_closed_lists() -> None:
    """coffee table and Mid-Century become catalog tokens without a retry."""
    # Model used spaces and capitals.
    raw = extract_json(must_have=["coffee table"], style="Mid-Century")
    # Decode.
    payload = json.loads(raw)
    # Assemble.
    requirement = assemble_requirement(payload, "scene-1", "text", "req-1", [])
    # Class token.
    assert requirement.must_have == ["coffee_table"]
    # Style token.
    assert requirement.style == "mid_century"


# Rug is not a catalog choice, so the attempt fails.
def test_rug_is_rejected() -> None:
    """must_have cannot name rug."""
    # Illegal class.
    payload = json.loads(extract_json(must_have=["rug"]))
    # The attempt raises.
    try:
        # Assemble.
        assemble_requirement(payload, "scene-1", "text", "req-1", [])
    # Expected.
    except ValueError as exc:
        # The reason names the class.
        assert "rug" in str(exc)
    else:
        # The assertion above must run.
        raise AssertionError("rug was accepted")


# A bad first answer is replaced by a valid second answer.
def test_retry_then_valid() -> None:
    """Invalid JSON spends one attempt. The second attempt is returned."""
    # First reply is not JSON. Second reply is valid.
    client = ScriptedChat(["not json", extract_json()])
    # Parse.
    requirement, attempts = parse_requirement(
        "A modern desk.",
        "room-1",
        "requirement-room-1",
        [],
        client,
    )
    # Both calls were used.
    assert attempts == 2
    # Both replies were consumed.
    assert client.calls == 2
    # Server-owned fields, not the model's scene_id.
    assert requirement.scene_id == "room-1"
    # The sentence is stored as given.
    assert requirement.raw_text == "A modern desk."
    # Sorted classes.
    assert requirement.must_have == ["chair", "desk"]


# Two bad answers stop with a readable error.
def test_retry_budget_fails_readably() -> None:
    """After two invalid replies the parser raises ParserFailure."""
    # Neither reply is JSON.
    client = ScriptedChat(["{", "{"])
    # Expect a failure.
    try:
        # Parse.
        parse_requirement("A modern desk.", "room-1", "requirement-room-1", [], client)
    # The budget is two attempts.
    except ParserFailure as exc:
        # The message names the budget.
        assert "2 attempts" in str(exc)
        # The count is stored.
        assert exc.attempts == 2
    else:
        # The assertion above must run.
        raise AssertionError("invalid JSON was accepted")


# An invented keep id is a validation error.
def test_unknown_keep_id_is_rejected() -> None:
    """must_keep ids have to be in the object list."""
    # The model invented an id.
    payload = json.loads(extract_json(must_keep_object_ids=["missing"]))
    # Assemble against a different id.
    try:
        # Only obj-1 exists.
        assemble_requirement(payload, "scene-1", "text", "req-1", [("obj-1", "chair")])
    # Expected.
    except ValueError as exc:
        # The reason mentions the field.
        assert "must_keep_object_ids" in str(exc)
    else:
        # The assertion above must run.
        raise AssertionError("invented id was accepted")


# Field accuracy is a micro-average and does not score identity fields.
def test_field_accuracy_counts_each_scored_field() -> None:
    """One matching record and one miss produce the expected rate."""
    # Gold.
    gold = {
        "budget_inr": 80000,
        "must_have": ["chair"],
        "must_keep_object_ids": [],
        "occupant_count": 1,
        "style": "modern",
        "accessibility_required": False,
        "objective_weights": {name: 1 for name in WEIGHT_NAMES},
    }
    # Exact copy.
    match = field_matches(gold, gold)
    # Every scored field matches.
    assert all(match.values())
    # The scored set is the twelve names.
    assert len(SCORED_FIELDS) == 12
    # A style miss.
    missed = dict(gold)
    # Different style.
    missed["style"] = "rustic"
    # Compare.
    partial = field_matches(gold, missed)
    # Style is the only miss.
    assert partial["style"] is False
    # Eleven of twelve fields match, twice would be 23/24 if the first row is perfect.
    assert micro_accuracy([match, partial]) == 23 / 24
