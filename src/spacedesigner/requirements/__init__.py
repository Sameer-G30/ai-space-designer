"""Requirement parser: Ollama qwen2.5:7b structured JSON, validated with Pydantic."""

# Readable failure type.
from spacedesigner.requirements.errors import ParserFailure

# HTTP models.
from spacedesigner.requirements.models import ParseRequest, ParseResponse

# Chat client dependency.
from spacedesigner.requirements.ollama_client import OllamaChatClient, get_chat_client

# Parse plus retrieval.
from spacedesigner.requirements.parser import parse_requirement

# Route helper.
from spacedesigner.requirements.service import parse_and_retrieve

# Names re-exported from this package.
__all__ = [
    "OllamaChatClient",
    "ParseRequest",
    "ParseResponse",
    "ParserFailure",
    "get_chat_client",
    "parse_and_retrieve",
    "parse_requirement",
]
