"""Template sentences built only from an optimizer trace and the stored design."""

# TemplatedFact is the sentence plus its source pointer.
from spacedesigner.explain.models import TemplatedFact

# The stored design supplies cost and score. The trace supplies the rest.
from spacedesigner.schemas import Design, OptimizerTrace


# Turn one trace into the sentences the model may rephrase.
def build_facts(
    design: Design,
    trace: OptimizerTrace,
    sensitivity_score_per_inr: float | None = None,
) -> list[TemplatedFact]:
    """Return one fact per cost, score, binding constraint, objective term, and rejection count."""
    # Sentences in a stable order. The rephraser is asked to keep this order.
    facts: list[TemplatedFact] = []
    # Cost is the stored design total, which the bill of materials already matches.
    facts.append(
        TemplatedFact(
            ref="design.cost",
            text=f"The catalog cost is INR {design.cost:.2f}.",
        )
    )
    # Score is the stored weighted score, not a new estimate.
    facts.append(
        TemplatedFact(
            ref="design.score",
            text=f"The design score is {design.score:.6f}.",
        )
    )
    # Each binding constraint is copied from the trace detail, which already holds the numbers.
    for binding in trace.binding_constraints:
        # The ref names the constraint so a claim can point back at it.
        facts.append(
            TemplatedFact(
                ref=f"trace.binding_constraints.{binding.name}",
                text=f"{binding.name}: {binding.detail}",
            )
        )
    # Each objective term is a unit-interval number from the trace.
    for name, value in trace.objective_terms.model_dump().items():
        # Six terms, in schema order.
        facts.append(
            TemplatedFact(
                ref=f"trace.objective_terms.{name}",
                text=f"The {name} objective term is {float(value):.6f}.",
            )
        )
    # The rejection list can be long, so the fact keeps the count rather than every row.
    facts.append(
        TemplatedFact(
            ref="trace.rejected_items",
            text=f"The solver rejected {len(trace.rejected_items)} catalog items.",
        )
    )
    # Sensitivity exists only after a budget what-if. It is not invented for other designs.
    if sensitivity_score_per_inr is not None:
        # Six decimals match the score fact so the checker sees one spelling.
        facts.append(
            TemplatedFact(
                ref="counterfactual.sensitivity_score_per_inr",
                text=(
                    "The score change per rupee of budget change is "
                    f"{sensitivity_score_per_inr:.6f}."
                ),
            )
        )
    # The list the prompt and the checker share.
    return facts
