"""Ollama HTTP client for qwen2.5:7b. The model stays in Ollama, not in this process."""

# Annotations on Python 3.11.
from __future__ import annotations

# JSON body for the chat request.
import json

# HTTP calls use the standard library so this phase adds no SDK package.
import urllib.error
import urllib.request

# Readable failure when Ollama is down or the model is missing.
from spacedesigner.requirements.errors import ParserFailure

# The only chat model this phase loads.
OLLAMA_MODEL = "qwen2.5:7b"

# Local Ollama HTTP API. The API process does not keep the weights.
OLLAMA_BASE_URL = "http://127.0.0.1:11434"

# A 7B JSON answer can take a while on the first token.
DEFAULT_TIMEOUT_S = 180.0


# Talk to the local Ollama daemon.
class OllamaChatClient:
    """POST /api/chat with a JSON schema and return the assistant string."""

    # Remember the endpoint without opening a connection.
    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = OLLAMA_MODEL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        """Store the URL, the model name, and the per-call timeout."""
        # Daemon origin, without a trailing slash.
        self.base_url = base_url.rstrip("/")
        # Model tag. This phase uses qwen2.5:7b only.
        self.model = model
        # Seconds to wait for one JSON answer.
        self.timeout_s = timeout_s

    # One non-streaming chat call.
    def complete(self, messages: list[dict[str, str]], schema: dict) -> str:
        """Return the assistant content. Raise ParserFailure when Ollama does not answer."""
        # Body requested by the Ollama chat API.
        payload = {
            # Fixed model for this phase.
            "model": self.model,
            # System rules, few-shot turns, and the user sentence.
            "messages": messages,
            # JSON schema so the answer is one object.
            "format": schema,
            # The eval and the API both want the full object, not tokens.
            "stream": False,
            # Keep the model loaded across the 100-sentence check.
            "keep_alive": "30m",
            # Greedy decoding for a repeatable extraction.
            "options": {"temperature": 0, "num_predict": 400},
        }
        # Encode the body as UTF-8 JSON.
        data = json.dumps(payload).encode("utf-8")
        # Chat endpoint on the local daemon.
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        # Network and HTTP failures become a readable parser error.
        try:
            # Wait up to the configured timeout.
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                # Read the whole JSON response.
                raw = response.read().decode("utf-8")
        # HTTP status from Ollama, including a missing model.
        except urllib.error.HTTPError as exc:
            # A short reason is enough. Do not include a URL with secrets.
            detail = exc.reason if isinstance(exc.reason, str) else "HTTP error"
            # Stop. A retry will not install the model.
            raise ParserFailure(
                f"Ollama did not answer for {self.model}: {detail}",
                0,
            ) from None
        # Connection refused, DNS, or a timeout.
        except (urllib.error.URLError, TimeoutError) as exc:
            # reason may be empty on a timeout.
            detail = getattr(exc, "reason", None) or str(exc)
            # Keep the message short.
            raise ParserFailure(
                f"Ollama did not answer for {self.model}: {detail}",
                0,
            ) from None
        # The daemon should return JSON.
        try:
            # Parse the chat envelope.
            body = json.loads(raw)
        # A non-JSON envelope is a daemon failure.
        except json.JSONDecodeError:
            # Do not echo the body; it is not a requirement.
            raise ParserFailure(
                f"Ollama returned a non-JSON envelope for {self.model}",
                0,
            ) from None
        # The assistant message holds the requirement JSON as text.
        message = body.get("message") if isinstance(body, dict) else None
        # Content is a string when the call succeeded.
        content = message.get("content") if isinstance(message, dict) else None
        # An empty answer cannot be validated.
        if not isinstance(content, str) or content.strip() == "":
            # Ask the caller to treat this as a failed attempt only if they retry.
            raise ParserFailure(
                f"Ollama returned an empty answer for {self.model}",
                0,
            ) from None
        # Hand the JSON text to the parser.
        return content


# FastAPI dependency. A new client does not load weights into this process.
def get_chat_client() -> OllamaChatClient:
    """Return a client aimed at the local qwen2.5:7b tag."""
    # Defaults match the phase decision.
    return OllamaChatClient()
