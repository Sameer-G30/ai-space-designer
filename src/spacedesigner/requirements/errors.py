"""Errors the requirement parser can show to a caller."""


# Raised when the model cannot produce a schema-valid requirement.
class ParserFailure(Exception):
    """A readable parse failure after the retry budget, or an unreachable model."""

    # Store the attempt count beside the message.
    def __init__(self, message: str, attempts: int) -> None:
        """Remember how many model calls were used."""
        # Keep the count for the API and the eval script.
        self.attempts = attempts
        # The message is the HTTP detail.
        super().__init__(message)
