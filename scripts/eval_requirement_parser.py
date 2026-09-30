"""Field-level accuracy and schema-valid rate on 100 synthetic gold requirements."""

# Annotations on Python 3.11.
from __future__ import annotations

# Limit and seed flags.
import argparse

# Gold rooms and requirements. This does not write the 2000-record set.
from spacedesigner.data.synthetic import generate

# Comparison. The gold files and the schema are not modified.
from spacedesigner.requirements.errors import ParserFailure
from spacedesigner.requirements.metrics import (
    SCORED_FIELDS,
    TEXT_GROUNDED_FIELDS,
    field_matches,
    micro_accuracy,
    per_field_accuracy,
)
from spacedesigner.requirements.ollama_client import OllamaChatClient
from spacedesigner.requirements.parser import parse_requirement

# Same seed the generator uses for the on-disk set. The first 100 records match that prefix.
DEFAULT_SEED = 20260930

# The check size named in the phase plan.
DEFAULT_LIMIT = 100


# Parse the flags, call Ollama, and print rates. Failures stay in the rate.
def main() -> int:
    """Return 0 after printing the rates, including when accuracy is low."""
    # Parser.
    parser = argparse.ArgumentParser(description=__doc__)
    # How many gold pairs to score.
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    # Generator seed.
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    # Read them.
    args = parser.parse_args()
    # In-memory gold. Nothing is written under datasets/raw/synthetic.
    scenes, requirements = generate(args.limit, args.seed)
    # HTTP client. qwen stays in the Ollama process.
    client = OllamaChatClient()
    # One bool map per schema-valid parse.
    rows: list[dict[str, bool]] = []
    # Parses that produced a Requirement.
    valid = 0
    # Short failure reasons. Sentences are not copyrighted; still keep the reason short.
    failures: list[str] = []
    # Walk the gold pairs together. generate() returns two lists, not zipped pairs.
    for index, (scene, gold) in enumerate(zip(scenes, requirements, strict=True), start=1):
        # Id and type only, so the prompt cannot copy a must-keep flag.
        objects = [(obj["id"], obj["type"]) for obj in scene["objects"]]
        # One sentence.
        try:
            # Validate with the locked schema. Retries are inside parse_requirement.
            parsed, _attempts = parse_requirement(
                gold["raw_text"],
                gold["scene_id"],
                gold["requirement_id"],
                objects,
                client,
            )
        # Budget spent, or Ollama did not answer. Every scored field counts as a miss.
        except ParserFailure as exc:
            # Count it as not schema-valid.
            failures.append(str(exc)[:240])
            # A failed parse matches no gold field.
            rows.append({name: False for name in SCORED_FIELDS})
            # Progress only.
            print(f"parsed {index}/{len(requirements)} valid={valid}", flush=True)
            # Next sentence.
            continue
        # This one validated.
        valid += 1
        # Score the extracted fields. requirement_id, scene_id, and raw_text are copied, not scored.
        rows.append(field_matches(gold, parsed.model_dump()))
        # Progress only. The headline rates are printed after the loop.
        print(f"parsed {index}/{len(requirements)} valid={valid}", flush=True)
    # Denominator is every gold row, including failures.
    schema_valid_rate = valid / len(requirements) if requirements else 0.0
    # Micro-average over scored fields. A failed parse matches none of them.
    accuracy = micro_accuracy(rows)
    # The same average on the fields the sentence actually states.
    grounded = micro_accuracy(rows, TEXT_GROUNDED_FIELDS)
    # Per-field rates on all 100 rows, so a failed parse counts as a miss.
    by_field = per_field_accuracy(rows)
    # Headline numbers.
    print(f"records {len(requirements)}")
    print(f"schema_valid_rate {schema_valid_rate:.6f}")
    print(f"field_accuracy {accuracy:.6f}")
    print(f"text_grounded_field_accuracy {grounded:.6f}")
    # Each field.
    for name in SCORED_FIELDS:
        # Rate on all records.
        print(f"field {name} {by_field[name]:.6f}")
    # How many never validated.
    print(f"schema_invalid {len(failures)}")
    # Up to five reasons, truncated.
    for reason in failures[:5]:
        # One line.
        print(f"failure {reason}")
    # The script reports the rate. A low rate is still a successful measurement.
    return 0


# Run only as a script.
if __name__ == "__main__":
    # Exit after the report lines.
    raise SystemExit(main())
