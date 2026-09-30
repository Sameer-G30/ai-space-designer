"""Structured requirement parser. Ollama proposes JSON; Pydantic accepts or rejects it."""

# Annotations on Python 3.11.
from __future__ import annotations

# The model returns a JSON string.
import json

# Protocol is the test double's contract.
from typing import Protocol

# ValidationError is the locked-schema failure.
from pydantic import ValidationError

# Readable stop after the retry budget.
from spacedesigner.requirements.errors import ParserFailure

# Closed lists and the attempt budget.
from spacedesigner.requirements.vocab import (
    MAX_PARSE_ATTEMPTS,
    MUST_HAVE_CLASSES,
    MUST_HAVE_SET,
    STYLE_SET,
    STYLE_WORDS,
    WEIGHT_NAMES,
    canonicalize_token,
)

# Locked requirement. This module does not change the schema.
from spacedesigner.schemas.requirement import Requirement


# Anything that can return one assistant string for a chat.
class ChatClient(Protocol):
    """Minimal chat contract shared by Ollama and the tests."""

    # messages are role/content pairs. schema is the JSON schema sent as format.
    def complete(self, messages: list[dict[str, str]], schema: dict) -> str:
        """Return the assistant content."""


# JSON schema sent to Ollama. Extra keys are not required, and the server drops them.
def output_schema() -> dict:
    """Schema for the extracted fields. scene_id and raw_text are set by the server."""
    # One number per weight.
    weight_props = {name: {"type": "number"} for name in WEIGHT_NAMES}
    # The object the model must return.
    return {
        # A single object.
        "type": "object",
        # The extracted fields. Identity fields are not the model's job.
        "required": [
            "budget_inr",
            "must_have",
            "must_keep_object_ids",
            "occupant_count",
            "style",
            "accessibility_required",
            "objective_weights",
        ],
        # Field shapes.
        "properties": {
            # Rupee ceiling.
            "budget_inr": {"type": "number"},
            # Catalog classes only.
            "must_have": {
                "type": "array",
                "items": {"type": "string", "enum": list(MUST_HAVE_CLASSES)},
            },
            # Ids copied from the object list.
            "must_keep_object_ids": {"type": "array", "items": {"type": "string"}},
            # People in the room.
            "occupant_count": {"type": "integer"},
            # One generator style word.
            "style": {"type": "string", "enum": list(STYLE_WORDS)},
            # Wheelchair access.
            "accessibility_required": {"type": "boolean"},
            # All six weights.
            "objective_weights": {
                "type": "object",
                "required": list(WEIGHT_NAMES),
                "properties": weight_props,
            },
        },
    }


# Rules that keep the model inside the locked lists.
def system_prompt() -> str:
    """Instructions for qwen2.5:7b. No new fields and no new style words."""
    # Classes the model may name, comma-separated.
    classes = ", ".join(MUST_HAVE_CLASSES)
    # Style words the model may name.
    styles = ", ".join(STYLE_WORDS)
    # Weights the model must always include.
    weights = ", ".join(WEIGHT_NAMES)
    # One block of rules.
    return "\n".join(
        [
            "You extract one interior-design requirement as a JSON object.",
            "Reply with that object only.",
            f"must_have may contain only these classes: {classes}.",
            "Never put rug, door, or window in must_have.",
            f"style must be exactly one of: {styles}.",
            "Map spaced or hyphenated words onto those tokens.",
            "occupant_count is an integer of at least 1.",
            "budget_inr is the rupee amount stated in the sentence.",
            "accessibility_required is true only when the sentence asks for wheelchair access.",
            f"objective_weights must include {weights}.",
            "Each weight is from 0 to 1.",
            "If the sentence does not state weights, set every weight to 1.",
            "must_keep_object_ids may use only ids from the existing-object list.",
            "When the sentence says to keep a type once, use the first id of that type.",
            "When it names the same type again, use the next id of that type, in list order.",
            "If nothing is kept, use an empty list.",
            "Do not add keys.",
        ]
    )


# Two schema-valid examples in the generator's sentence shape.
def few_shot_messages() -> list[dict[str, str]]:
    """User and assistant turns the model can copy. Both JSON objects are valid extracts."""
    # First example: a kept desk, no accessibility line, weights omitted from the sentence.
    first_user = "\n".join(
        [
            "Existing objects:",
            "- id=home_obj_01 type=chair",
            "- id=home_obj_02 type=desk",
            "Sentence:",
            "I want to redo my home office in a modern style. I need desk, chair. "
            "The budget is 80000 rupees for 1 person. Please keep my desk.",
        ]
    )
    # Gold extract for that sentence.
    first_json = {
        "budget_inr": 80000,
        "must_have": ["chair", "desk"],
        "must_keep_object_ids": ["home_obj_02"],
        "occupant_count": 1,
        "style": "modern",
        "accessibility_required": False,
        "objective_weights": {name: 1 for name in WEIGHT_NAMES},
    }
    # Second example: a spaced style word, three classes, and wheelchair access.
    second_user = "\n".join(
        [
            "Existing objects:",
            "none",
            "Sentence:",
            "I want to redo my living room in a mid century style. "
            "I need sofa, coffee table, lamp. The budget is 120000 rupees for 2 people. "
            "The room must be wheelchair accessible.",
        ]
    )
    # Gold extract for the second sentence.
    second_json = {
        "budget_inr": 120000,
        "must_have": ["coffee_table", "lamp", "sofa"],
        "must_keep_object_ids": [],
        "occupant_count": 2,
        "style": "mid_century",
        "accessibility_required": True,
        "objective_weights": {name: 1 for name in WEIGHT_NAMES},
    }
    # Chat turns in order.
    return [
        {"role": "user", "content": first_user},
        {"role": "assistant", "content": json.dumps(first_json)},
        {"role": "user", "content": second_user},
        {"role": "assistant", "content": json.dumps(second_json)},
    ]


# The turn that carries the user's sentence.
def user_turn(raw_text: str, objects: list[tuple[str, str]]) -> str:
    """Format the object list and the sentence the way the examples do."""
    # No objects means the model must not invent a keep id.
    if not objects:
        # Same word the second example uses.
        object_lines = ["none"]
    else:
        # One id and type per line.
        object_lines = [
            f"- id={object_id} type={object_type}" for object_id, object_type in objects
        ]
    # Match the example layout.
    return "\n".join(["Existing objects:", *object_lines, "Sentence:", raw_text])


# Strip a markdown fence if the model adds one despite the schema.
def parse_json_object(raw: str) -> dict:
    """Return the object in a model reply, or raise ValueError."""
    # Trim outer whitespace.
    text = raw.strip()
    # Drop a leading fence.
    if text.startswith("```"):
        # Remove the first line, which is the fence and an optional language tag.
        text = text.split("\n", 1)[-1]
        # Remove a trailing fence.
        text = text.removesuffix("```").strip()
    # Decode the object.
    try:
        # The schema asks for one object.
        value = json.loads(text)
    # Invalid JSON is a retry, not a success.
    except json.JSONDecodeError as exc:
        # Short reason for the re-prompt.
        raise ValueError(f"invalid JSON: {exc.msg}") from None
    # A list or a string is not a requirement.
    if not isinstance(value, dict):
        # Retry.
        raise ValueError("JSON value must be an object")
    # Hand the object to the field checks.
    return value


# Coerce a model number. Booleans are not numbers here.
def as_float(value: object, label: str) -> float:
    """Return a finite float, or raise ValueError."""
    # Reject bool because bool is a subclass of int.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        # The re-prompt names the field.
        raise ValueError(f"{label} must be a number")
    # Store it as float.
    number = float(value)
    # Reject NaN and infinities before Pydantic sees them.
    if number != number or number in (float("inf"), float("-inf")):
        # Retry.
        raise ValueError(f"{label} must be finite")
    # Usable number.
    return number


# Coerce an occupant count that may have arrived as 2.0.
def as_int(value: object, label: str) -> int:
    """Return an integer, or raise ValueError."""
    # A whole-valued float is accepted. A bool is not.
    if isinstance(value, bool):
        # Retry.
        raise ValueError(f"{label} must be an integer")
    # Already an int.
    if isinstance(value, int):
        # Done.
        return value
    # 2.0 is an integer count. 2.5 is not.
    if isinstance(value, float) and value.is_integer():
        # Convert.
        return int(value)
    # Anything else fails this attempt.
    raise ValueError(f"{label} must be an integer")


# Accept JSON booleans and a few obvious spellings.
def as_bool(value: object) -> bool:
    """Return accessibility_required, or raise ValueError."""
    # Native JSON boolean.
    if isinstance(value, bool):
        # Done.
        return value
    # A model that ignored the schema may say "true".
    if isinstance(value, str) and value.strip().lower() in {"true", "yes"}:
        # Treat that as true.
        return True
    # The same for false.
    if isinstance(value, str) and value.strip().lower() in {"false", "no"}:
        # Treat that as false.
        return False
    # Retry.
    raise ValueError("accessibility_required must be a boolean")


# Build a Requirement from model JSON plus the server-owned fields.
def assemble_requirement(
    payload: dict,
    scene_id: str,
    raw_text: str,
    requirement_id: str,
    objects: list[tuple[str, str]],
) -> Requirement:
    """Validate closed lists, then the locked Requirement model."""
    # Budget.
    budget = as_float(payload.get("budget_inr"), "budget_inr")
    # Negative money fails the schema too, but say it clearly.
    if budget < 0:
        # Retry.
        raise ValueError("budget_inr must be 0 or greater")
    # Classes before canonicalization.
    raw_classes = payload.get("must_have")
    # The field must be a list.
    if not isinstance(raw_classes, list):
        # Retry.
        raise ValueError("must_have must be a list")
    # Canonical tokens.
    classes: list[str] = []
    # Check each requested class.
    for item in raw_classes:
        # Only strings can be class names.
        if not isinstance(item, str):
            # Retry.
            raise ValueError("must_have entries must be strings")
        # "coffee table" becomes coffee_table.
        token = canonicalize_token(item)
        # Rug, door, window, and unknown words are rejected.
        if token not in MUST_HAVE_SET:
            # Name the allowed set so the retry can correct it.
            raise ValueError(f"must_have contains {token or item!r}, which is not a catalog class")
        # Keep the first copy only.
        if token not in classes:
            # Record it.
            classes.append(token)
    # Match the generator, which stores classes in sorted order.
    classes = sorted(classes)
    # Keep ids.
    raw_ids = payload.get("must_keep_object_ids")
    # The field must be a list.
    if not isinstance(raw_ids, list):
        # Retry.
        raise ValueError("must_keep_object_ids must be a list")
    # Ids the sentence is allowed to name.
    allowed_ids = [object_id for object_id, _object_type in objects]
    # Fast lookup.
    allowed_set = set(allowed_ids)
    # Accepted ids.
    keep_ids: list[str] = []
    # Check each id.
    for item in raw_ids:
        # Only strings can be ids.
        if not isinstance(item, str) or item.strip() == "":
            # Retry.
            raise ValueError("must_keep_object_ids entries must be non-empty strings")
        # The model must not invent an id.
        if item not in allowed_set:
            # Retry with the legal ids.
            raise ValueError("must_keep_object_ids must be chosen from the existing object ids")
        # Drop duplicates.
        if item not in keep_ids:
            # Keep the model's order.
            keep_ids.append(item)
    # People.
    occupants = as_int(payload.get("occupant_count"), "occupant_count")
    # The schema requires at least one.
    if occupants < 1:
        # Retry.
        raise ValueError("occupant_count must be at least 1")
    # Style token.
    raw_style = payload.get("style")
    # Style must be a string before canonicalization.
    if not isinstance(raw_style, str):
        # Retry.
        raise ValueError("style must be a string")
    # "mid century" becomes mid_century.
    style = canonicalize_token(raw_style)
    # Only the nine generator words.
    if style not in STYLE_SET:
        # Retry.
        raise ValueError(f"style must be one of: {', '.join(STYLE_WORDS)}")
    # Accessibility flag.
    accessible = as_bool(payload.get("accessibility_required"))
    # Weight object.
    raw_weights = payload.get("objective_weights")
    # It must be an object.
    if not isinstance(raw_weights, dict):
        # Retry.
        raise ValueError("objective_weights must be an object")
    # The six numbers.
    weights: dict[str, float] = {}
    # Every name is required.
    for name in WEIGHT_NAMES:
        # Missing key.
        if name not in raw_weights:
            # Retry.
            raise ValueError(f"objective_weights.{name} is required")
        # Coerce.
        weights[name] = as_float(raw_weights[name], f"objective_weights.{name}")
    # The locked model is the last gate. Unknown keys are not copied in.
    candidate = {
        # Server-owned id.
        "requirement_id": requirement_id,
        # The scene the user is editing, not a value from the model.
        "scene_id": scene_id,
        # The sentence they typed.
        "raw_text": raw_text,
        # Extracted budget.
        "budget_inr": budget,
        # Extracted classes.
        "must_have": classes,
        # Extracted keep ids.
        "must_keep_object_ids": keep_ids,
        # Extracted people count.
        "occupant_count": occupants,
        # Extracted style.
        "style": style,
        # Extracted flag.
        "accessibility_required": accessible,
        # Extracted weights.
        "objective_weights": weights,
    }
    # Pydantic enforces bounds and extra=forbid on this object.
    try:
        # Validate.
        return Requirement.model_validate(candidate)
    # Turn the schema error into a short retry reason.
    except ValidationError as exc:
        # The first error is enough for the re-prompt.
        first = exc.errors()[0]["msg"] if exc.errors() else "schema validation failed"
        # Retry.
        raise ValueError(first) from None


# Parse one sentence, re-prompting once on invalid JSON or a closed-list failure.
def parse_requirement(
    raw_text: str,
    scene_id: str,
    requirement_id: str,
    objects: list[tuple[str, str]],
    client: ChatClient,
) -> tuple[Requirement, int]:
    """Return (requirement, attempts). Raise ParserFailure when the budget is spent."""
    # A blank sentence is not sent to the model.
    if raw_text.strip() == "":
        # No attempt was made.
        raise ParserFailure("raw_text is empty", 0)
    # A blank scene id cannot be copied onto the requirement.
    if scene_id.strip() == "":
        # No attempt was made.
        raise ParserFailure("scene_id is empty", 0)
    # The form always sends an id. Reject a blank override.
    if requirement_id.strip() == "":
        # No attempt was made.
        raise ParserFailure("requirement_id is empty", 0)
    # Schema shared by every attempt.
    schema = output_schema()
    # System rules, two examples, then this sentence.
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt()},
        *few_shot_messages(),
        {"role": "user", "content": user_turn(raw_text, objects)},
    ]
    # Last validation reason, shown if every attempt fails.
    last_error = "no model output"
    # Attempt numbers start at 1.
    for attempt in range(1, MAX_PARSE_ATTEMPTS + 1):
        # Ask Ollama, or the test double. Transport errors propagate.
        raw = client.complete(messages, schema)
        # Validate this answer.
        try:
            # JSON, closed lists, then the locked schema.
            requirement = assemble_requirement(
                parse_json_object(raw),
                scene_id,
                raw_text,
                requirement_id,
                objects,
            )
        # Invalid JSON or a bad field. Re-prompt if an attempt remains.
        except ValueError as exc:
            # Remember the reason.
            last_error = str(exc)
            # Show the model its own answer and the reason.
            messages.append({"role": "assistant", "content": raw})
            # Ask for a corrected object only.
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"That JSON failed validation: {last_error} "
                        "Reply with corrected JSON only."
                    ),
                }
            )
            # Next attempt, or fall through after the last one.
            continue
        # The requirement is schema-valid.
        return requirement, attempt
    # The retry budget is spent.
    raise ParserFailure(
        (
            f"Could not parse a requirement after {MAX_PARSE_ATTEMPTS} attempts. "
            f"Last error: {last_error}"
        ),
        MAX_PARSE_ATTEMPTS,
    )
