"""Run the GPU pipeline in a child process so the API process never loads CUDA or weights."""

# Annotations on Python 3.11.
from __future__ import annotations

# The worker prints JSON.
import json

# Start the worker.
import subprocess

# Sanitized image goes to a temporary file.
import tempfile

# Best-effort Ollama unload uses the standard library only.
import urllib.request

# Locate the training venv.
from pathlib import Path

# Repo root (src/spacedesigner/perception/runner.py -> three parents up is src; four is the repo).
ROOT = Path(__file__).resolve().parents[3]

# Interpreter with CUDA torch, timm, ultralytics, and transformers.
WORKER_PYTHON = ROOT / ".venv-train" / "bin" / "python"

# Seconds the worker may run before it is stopped.
TIMEOUT_S = 300

# Ollama endpoint and the chat model that must not stay on the GPU.
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:7b"


# Raised when the pipeline cannot give a result.
class PerceptionFailure(RuntimeError):
    """The photo pipeline failed; the message is safe to show the user."""


# Ask Ollama to drop the chat model so the 8 GB GPU is free for the vision models.
def unload_llm() -> None:
    """Send keep_alive 0 to Ollama. Any failure is ignored because Ollama may be off."""
    # Request body that unloads the model without generating text.
    body = json.dumps({"model": OLLAMA_MODEL, "keep_alive": 0}).encode()
    # Build the request.
    request = urllib.request.Request(
        OLLAMA_URL, data=body, headers={"Content-Type": "application/json"}
    )
    # Ollama may not be running, which is fine.
    try:
        # Short timeout: this is housekeeping.
        urllib.request.urlopen(request, timeout=3).read()
    # Network and HTTP errors both mean there is nothing to unload.
    except Exception:
        # Nothing to do.
        return


# Run the worker on PNG bytes that already have no metadata.
def run_worker(png: bytes, focal_35mm: float | None) -> dict:
    """Return the unscaled perception result or raise PerceptionFailure."""
    # The worker interpreter must exist.
    if not WORKER_PYTHON.exists():
        # Tell the user what is missing.
        raise PerceptionFailure(f"missing {WORKER_PYTHON}; see requirements-train.txt")
    # Free GPU memory held by the chat model.
    unload_llm()
    # A temp file holds the sanitized image and is deleted afterwards.
    with tempfile.NamedTemporaryFile(suffix=".png") as handle:
        # Write the pixels.
        handle.write(png)
        # Flush so the child sees all bytes.
        handle.flush()
        # Command line for the worker module.
        command = [str(WORKER_PYTHON), "-m", "spacedesigner.perception.worker", handle.name]
        # Pass the focal length only when EXIF had one.
        if focal_35mm:
            # Add the option.
            command += ["--focal-35mm", str(focal_35mm)]
        # A timeout stops a hung child.
        try:
            # Capture stdout for the JSON line; stderr carries library logging.
            done = subprocess.run(
                command, capture_output=True, text=True, timeout=TIMEOUT_S, cwd=ROOT
            )
        # Report a timeout readably.
        except subprocess.TimeoutExpired:
            # Safe message.
            raise PerceptionFailure("the photo pipeline timed out") from None
    # The payload is the last non-empty stdout line.
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    # No output at all means the child crashed early.
    if not lines:
        # Safe message.
        raise PerceptionFailure("the photo pipeline produced no result")
    # Parse the payload.
    try:
        # JSON from the last line.
        payload = json.loads(lines[-1])
    # A non-JSON last line is a crash trace.
    except json.JSONDecodeError:
        # Safe message.
        raise PerceptionFailure("the photo pipeline returned an unreadable result") from None
    # The worker reports errors as {"error": ...}.
    if "error" in payload:
        # Pass the reason through.
        raise PerceptionFailure(payload["error"])
    # Success.
    return payload


# FastAPI dependency. Tests override it so no GPU or weights are used.
def get_perception_runner():
    """Return the function that runs the pipeline."""
    # The default runner spawns the training-venv worker.
    return run_worker
