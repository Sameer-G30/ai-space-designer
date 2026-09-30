"""Faithfulness checks against templated facts. No model is loaded."""

# The checker and the fact type.
from spacedesigner.explain.faithfulness import claim_is_verified
from spacedesigner.explain.models import TemplatedFact
from spacedesigner.explain.rephrase import phrase_claims

# The error a down model raises.
from spacedesigner.requirements.errors import ParserFailure


# Two facts with one price and one clearance.
def _facts() -> list[TemplatedFact]:
    """Return a tiny fact list."""
    # Cost and a clearance sentence.
    return [
        TemplatedFact(ref="design.cost", text="The catalog cost is INR 1000.00."),
        TemplatedFact(
            ref="trace.binding_constraints.circulation",
            text="circulation: furniture clearance is at least 0.915 m",
        ),
    ]


# A sentence that copies a fact is verified.
def test_copied_fact_is_verified() -> None:
    """Accept a sentence whose numbers and domain words are in the facts."""
    # The cost sentence, with the same number written without trailing zeros.
    claim = "The catalog cost is INR 1000."
    # The checker allows the shorter spelling of the same quantity.
    assert claim_is_verified(claim, _facts()) is True


# An invented price is rejected.
def test_invented_number_is_rejected() -> None:
    """Reject a price the facts do not state."""
    # A quantity that is not 1000 and not 0.915.
    claim = "The catalog cost is INR 999999.99."
    # The checker fails the claim.
    assert claim_is_verified(claim, _facts()) is False


# A sentence with no trace content is rejected.
def test_unsupported_sentence_is_rejected() -> None:
    """Reject a sentence that does not use a fact number or a fact domain word."""
    # No number and no domain word from the fact list.
    claim = "The layout feels welcoming and bright."
    # Not a trace claim.
    assert claim_is_verified(claim, _facts()) is False


# A domain word the facts never use is rejected even without a new number.
def test_unknown_domain_word_is_rejected() -> None:
    """Reject a reason word that the facts do not contain."""
    # door is a domain word and it is absent from these facts.
    claim = "The door was the reason for this layout."
    # The word is not grounded.
    assert claim_is_verified(claim, _facts()) is False


# A client that always fails.
class _Down:
    """Stand-in that behaves like Ollama being unreachable."""

    # The phrasing call.
    def complete(self, messages: list[dict[str, str]], schema: dict) -> str:
        """Raise the same error the Ollama client raises."""
        # Message and attempt count.
        raise ParserFailure("Ollama did not answer", 0)


# When the model does not answer, the template is stored and every claim is verified.
def test_unreachable_model_keeps_the_template() -> None:
    """A ParserFailure falls back to the facts instead of failing the explanation."""
    # Facts.
    facts = _facts()
    # Phrase with the failing client.
    claims, rephrased, note = phrase_claims("design-x", facts, _Down())
    # The model did not rephrase.
    assert rephrased is False
    # The note names the failure.
    assert "Ollama did not answer" in note
    # One claim per fact, copied and verified.
    assert len(claims) == len(facts)
    assert all(claim.verified for claim in claims)
    assert [claim.claim_text for claim in claims] == [fact.text for fact in facts]
