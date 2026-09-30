"""Ask qwen2.5:7b to rephrase templated facts. It is not given the trace itself."""

# json reads the sentences array.
import json

# Protocol is the test double's contract. The parser client satisfies it.
from typing import Protocol

# The checker decides verified after the model answers.
from spacedesigner.explain.faithfulness import claim_is_verified, supporting_ref

# Stored claim shape.
from spacedesigner.explain.models import ExplanationClaim, TemplatedFact

# The same failure the parser raises when Ollama does not answer.
from spacedesigner.requirements.errors import ParserFailure

# JSON object the model must return. One sentence per fact.
REPHRASE_SCHEMA = {
    # A single object.
    "type": "object",
    # The only key.
    "required": ["sentences"],
    # A list of strings.
    "properties": {"sentences": {"type": "array", "items": {"type": "string"}}},
}

# Rules that keep the model from adding quantities.
SYSTEM_PROMPT = "\n".join(
    [
        "You rephrase interior-design facts into plain sentences.",
        "Use only the facts below.",
        "Copy every number exactly.",
        "Do not add a measurement, a price, a count, or a reason that is not in the facts.",
        "Return one JSON object with a sentences array.",
        "Write one sentence per fact, in the same order.",
    ]
)


# Anything that can return one assistant string. OllamaChatClient.complete matches this.
class RephraseClient(Protocol):
    """Minimal chat contract for explanation phrasing."""

    # schema is the JSON schema sent as Ollama's format field.
    def complete(self, messages: list[dict[str, str]], schema: dict) -> str:
        """Return the assistant content."""


# Build the user message from the facts alone.
def fact_message(facts: list[TemplatedFact]) -> str:
    """List the facts the model may rephrase. The raw trace is not included."""
    # One bullet per fact, without the internal ref, so the model does not invent labels.
    lines = [f"- {fact.text}" for fact in facts]
    # A short header plus the bullets.
    return "\n".join(["Facts:", *lines])


# Read a sentences array from a model reply.
def _sentences(raw: str) -> list[str]:
    """Return the stripped sentences, or an empty list when the reply is not that object."""
    # Trim outer whitespace.
    text = raw.strip()
    # Drop a markdown fence if the model added one.
    if text.startswith("```"):
        # Remove the opening fence line.
        text = text.split("\n", 1)[-1]
        # Remove a trailing fence.
        text = text.removesuffix("```").strip()
    # Decode the object.
    try:
        # The schema asks for one object.
        value = json.loads(text)
    # Invalid JSON means the reply cannot be checked as claims.
    except json.JSONDecodeError:
        # Caller falls back to the template.
        return []
    # A list or a string is not the schema.
    if not isinstance(value, dict):
        # Fall back.
        return []
    # The sentences field.
    sentences = value.get("sentences")
    # It must be a list.
    if not isinstance(sentences, list):
        # Fall back.
        return []
    # Keep non-empty strings only.
    cleaned = [item.strip() for item in sentences if isinstance(item, str) and item.strip()]
    # Cap the list so a runaway reply cannot fill the table.
    return cleaned[:20]


# Turn model sentences into claims. Length-matched replies keep the fact order as the source.
def claims_from_sentences(
    design_id: str,
    facts: list[TemplatedFact],
    sentences: list[str],
) -> list[ExplanationClaim]:
    """Verify each sentence and point it at a fact."""
    # Pair by index when the model followed the one-sentence-per-fact rule.
    paired = len(sentences) == len(facts)
    # Claims in reply order.
    claims: list[ExplanationClaim] = []
    # Check every sentence.
    for index, sentence in enumerate(sentences):
        # The matching fact when the counts agree, otherwise the closest fact.
        paired_ref = facts[index].ref if paired else supporting_ref(sentence, facts)
        # An invented number or domain word fails even when the index matches.
        verified = claim_is_verified(sentence, facts)
        # A failed claim still records the closest fact so the UI can show the source.
        ref = paired_ref if verified else supporting_ref(sentence, facts)
        # Stable id so a repeated explanation replaces the same keys.
        claims.append(
            ExplanationClaim(
                explanation_id=f"{design_id}:{index:04d}",
                claim_text=sentence,
                supporting_trace_ref=ref,
                verified=verified,
            )
        )
    # The list to store.
    return claims


# One rephrase call. ParserFailure and a bad object both return no claims.
def rephrase_facts(facts: list[TemplatedFact], chat: RephraseClient) -> list[str]:
    """Return the model's sentences. Raise ParserFailure when the daemon does not answer."""
    # System rules, then the facts. No other context.
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": fact_message(facts)},
    ]
    # Prefer a longer cap. A test double that only accepts two arguments still works.
    try:
        # Explanation replies are longer than one requirement object.
        raw = chat.complete(messages, REPHRASE_SCHEMA, num_predict=700)  # type: ignore[call-arg]
    # The parser's test doubles, and the Protocol, take two arguments.
    except TypeError:
        # Same call the requirement parser makes.
        raw = chat.complete(messages, REPHRASE_SCHEMA)
    # Parse the sentences. An empty list tells the caller to keep the template.
    return _sentences(raw)


# Claims that copy the facts. They verify by construction and do not call a model.
def template_claims(design_id: str, facts: list[TemplatedFact]) -> list[ExplanationClaim]:
    """Store the facts themselves as verified claims."""
    # One claim per fact.
    return [
        ExplanationClaim(
            explanation_id=f"{design_id}:{index:04d}",
            claim_text=fact.text,
            supporting_trace_ref=fact.ref,
            verified=True,
        )
        for index, fact in enumerate(facts)
    ]


# Rephrase when the client answers, otherwise keep the template.
def phrase_claims(
    design_id: str,
    facts: list[TemplatedFact],
    chat: RephraseClient | None,
) -> tuple[list[ExplanationClaim], bool, str]:
    """Return claims, whether a model produced them, and a short note."""
    # No client means the template is the explanation.
    if chat is None:
        # Tests that pass None stay offline.
        return template_claims(design_id, facts), False, "template only"
    # The daemon, or a double, may fail.
    try:
        # Ask for a rephrase. The facts are the only numbers in the prompt.
        sentences = rephrase_facts(facts, chat)
    # Ollama is down, timed out, or returned an empty body.
    except ParserFailure as exc:
        # Keep the template and record why.
        return template_claims(design_id, facts), False, str(exc)
    # A reply that is not the sentences object is not stored as model text.
    if not sentences:
        # The template is still a faithful explanation.
        return template_claims(design_id, facts), False, "model reply was not a sentences array"
    # Check every sentence against the facts.
    claims = claims_from_sentences(design_id, facts, sentences)
    # The model answered, whether or not every sentence verified.
    return claims, True, "rephrased from the templated facts"
