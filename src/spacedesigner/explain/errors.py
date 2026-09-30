"""Errors the Phase 8 routes turn into HTTP responses."""


# A missing design, scene, or requirement, or a counterfactual the solver cannot start.
class ExplainError(Exception):
    """Carry an HTTP status and a short detail string."""

    # Store both fields the route copies onto HTTPException.
    def __init__(self, status_code: int, detail: str) -> None:
        """Remember the status and the detail."""
        # Status the route returns.
        self.status_code = status_code
        # Sentence the client can show.
        self.detail = detail
        # Keep Exception's message aligned with that sentence.
        super().__init__(detail)
