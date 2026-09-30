"""Advisory VLM critic. It never accepts, rejects, or rewrites a design."""

# Annotations on Python 3.11.
from __future__ import annotations

# JSON body for the Ollama chat call.
import json

# Local HTTP only. This module does not pull a model.
import urllib.error
import urllib.request

# The four hard flags compared with the geometric checker.
from spacedesigner.critic.disagreement import HARD_KINDS

# Critic model named in the plan. It is not pulled by this module.
VLM_MODEL = "qwen2.5vl:7b"

# Same local daemon the parser uses.
OLLAMA_BASE_URL = "http://127.0.0.1:11434"

# JSON schema sent as Ollama's format field.
CRITIC_SCHEMA = {
    "type": "object",
    "properties": {
        "plausible": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "overlap": {"type": "boolean"},
        "clearance": {"type": "boolean"},
        "budget": {"type": "boolean"},
        "missing": {"type": "boolean"},
    },
    "required": ["plausible", "issues", "overlap", "clearance", "budget", "missing"],
}


# True when the daemon already has a qwen2.5vl tag. This does not pull one.
def vl_model_present(base_url: str = OLLAMA_BASE_URL) -> bool:
    """Return True when /api/tags lists a qwen2.5vl model."""
    # Tags endpoint.
    request = urllib.request.Request(f"{base_url.rstrip('/')}/api/tags", method="GET")
    # The daemon may be off.
    try:
        # Short timeout. This is a presence check.
        with urllib.request.urlopen(request, timeout=3) as response:
            # Parse the tag list.
            payload = json.loads(response.read().decode("utf-8"))
    # Down, slow, or not JSON.
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        # Treat that as not present. Do not pull.
        return False
    # Model records.
    models = payload.get("models", []) if isinstance(payload, dict) else []
    # Any tag whose name starts with the critic family.
    for model in models:
        # Name field.
        name = str(model.get("name", "")) if isinstance(model, dict) else ""
        # qwen2.5vl:7b and a bare qwen2.5vl both count.
        if name.split(":", 1)[0] == "qwen2.5vl":
            # Present.
            return True
    # Not pulled.
    return False


# Ask the VLM for an advisory reading of one image.
def advise(
    image_base64: str,
    summary: str,
    base_url: str = OLLAMA_BASE_URL,
    timeout_s: float = 180.0,
) -> dict:
    """Return plausible, issues, and the four hard flags. Raise if Ollama does not answer."""
    # The model is told it cannot change the design.
    prompt = (
        "You are an advisory interior-design critic. You cannot accept, reject, or move furniture. "
        "Look at the image and the design summary. Reply with JSON only. "
        "plausible is your aesthetic opinion. issues is a short list of aesthetic notes. "
        "Set overlap, clearance, budget, or missing to true only if the image itself shows that "
        "hard problem. The geometric checker remains authoritative.\n"
        f"Design summary: {summary}"
    )
    # Ollama chat body. keep_alive 0 unloads the vision model after this call.
    payload = {
        "model": VLM_MODEL,
        "messages": [{"role": "user", "content": prompt, "images": [image_base64]}],
        "format": CRITIC_SCHEMA,
        "stream": False,
        "keep_alive": 0,
        "options": {"temperature": 0},
    }
    # Encode JSON.
    data = json.dumps(payload).encode("utf-8")
    # Chat endpoint.
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    # Network failures become a readable error for the caller to turn into not_run.
    try:
        # Wait for one JSON answer.
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            # Response body.
            body = json.loads(response.read().decode("utf-8"))
    # The daemon did not answer.
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        # The service records not_run. It does not pull the model.
        raise RuntimeError(f"ollama critic unavailable: {exc}") from None
    # Assistant string.
    content = body.get("message", {}).get("content", "") if isinstance(body, dict) else ""
    # Parse the JSON object.
    try:
        # One object.
        parsed = json.loads(content)
    # Not JSON.
    except json.JSONDecodeError as exc:
        # The service records not_run.
        raise RuntimeError("ollama critic returned non-json") from exc
    # Require the fields the disagreement logger reads.
    if not isinstance(parsed, dict):
        # Not an object.
        raise RuntimeError("ollama critic returned a non-object")
    # Flags default to false when a key is missing, so a partial reply cannot invent a flag.
    flags = {kind: bool(parsed.get(kind)) for kind in HARD_KINDS}
    # Issues must be a list of strings.
    issues = parsed.get("issues", [])
    # Drop anything that is not text.
    clean_issues = [str(item) for item in issues] if isinstance(issues, list) else []
    # Advisory payload. The caller logs it and still returns the design.
    return {
        "plausible": bool(parsed.get("plausible")),
        "issues": clean_issues,
        "flags": flags,
    }
