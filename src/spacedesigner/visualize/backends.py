"""GPU backends for inpainting, re-detection, and the advisory critic.

The API process does not import diffusers or ultralytics. Workers run in .venv-train.
Nothing here downloads weights or pulls an Ollama model.
"""

# Annotations on Python 3.11.
from __future__ import annotations

# JSON from the worker's last stdout line.
import json

# Environment for the weight cache path.
import os

# Child processes.
import subprocess

# Temporary PNGs handed to the workers.
import tempfile

# Results the service reads.
from dataclasses import dataclass

# Paths.
from pathlib import Path

# Images passed across the backend boundary.
from PIL import Image

# Advisory critic. Importing it does not load a model.
from spacedesigner.critic.vlm import advise, vl_model_present

# Saved detector path. Importing this module does not load the weights.
from spacedesigner.training.detector import BEST_WEIGHTS

# Detections the consistency matcher consumes.
from spacedesigner.visualize.consistency import Detection

# Repo root: visualize -> spacedesigner -> src -> repo.
ROOT = Path(__file__).resolve().parents[3]

# Interpreter that is allowed to import CUDA torch, diffusers, and ultralytics.
WORKER_PYTHON = ROOT / ".venv-train" / "bin" / "python"

# SD 1.5 inpaint repo id. The cache folder uses this slug.
SD_MODEL = "runwayml/stable-diffusion-inpainting"

# ControlNet-depth repo id.
CONTROL_MODEL = "lllyasviel/control_v11f1p_sd15_depth"

# Seconds one diffusion attempt may run.
DIFFUSION_TIMEOUT_S = 240

# Seconds one detector pass may run.
DETECT_TIMEOUT_S = 120


# One inpaint attempt.
@dataclass
class InpaintOutput:
    """Status, note, optional image, and optional peak MiB."""

    # generated or not_run.
    status: str
    # Sentence safe to show.
    note: str
    # PIL image when status is generated.
    image: Image.Image | None
    # Peak allocated MiB from the worker, if it reported one.
    peak_vram_mib: float | None


# One detector pass.
@dataclass
class DetectOutput:
    """Status, note, boxes, and optional peak MiB."""

    # ok or not_run.
    status: str
    # Sentence safe to show.
    note: str
    # Boxes in the image pixel space.
    detections: list[Detection]
    # Peak allocated MiB.
    peak_vram_mib: float | None


# One critic call.
@dataclass
class CriticOutput:
    """Advisory reading. status advisory does not accept or reject a design."""

    # advisory or not_run.
    status: str
    # Sentence safe to show.
    note: str
    # Aesthetic opinion, or None when the critic did not run.
    plausible: bool | None
    # Aesthetic notes.
    issues: list[str]
    # Hard flags compared with the geometric checker.
    flags: dict[str, bool]


# Hugging Face hub directory, honouring the usual environment overrides.
def _hub_dir() -> Path:
    """Return the local hub cache. This does not create it or download into it."""
    # Explicit hub cache.
    explicit = os.environ.get("HF_HUB_CACHE") or os.environ.get("HUGGINGFACE_HUB_CACHE")
    # Use it when set.
    if explicit:
        # Caller-selected cache.
        return Path(explicit)
    # HF_HOME/hub is the other common layout.
    home = os.environ.get("HF_HOME")
    # Use it when set.
    if home:
        # Standard subfolder.
        return Path(home) / "hub"
    # Default cache on this machine.
    return Path.home() / ".cache" / "huggingface" / "hub"


# True when one snapshot contains every fp16 file the worker will open.
def _fp16_present(repo_id: str, relatives: tuple[str, ...]) -> bool:
    """Return True when the fp16 safetensors are fully downloaded."""
    # Snapshot directory for this repo.
    root = _hub_dir() / _repo_folder(repo_id) / "snapshots"
    # Nothing downloaded.
    if not root.is_dir():
        # Missing.
        return False
    # Each commit snapshot.
    for snap in root.iterdir():
        # Every required relative path must be a real file.
        if snap.is_dir() and all((snap / rel).is_file() for rel in relatives):
            # This snapshot can be loaded with local_files_only.
            return True
    # Still incomplete.
    return False


# Cache folder name diffusers uses for a repo id.
def _repo_folder(repo_id: str) -> str:
    """Return models--org--name."""
    # Slashes become -- in the cache folder.
    return "models--" + repo_id.replace("/", "--")


# Whether .venv-train can import diffusers and both weight folders exist.
def diffusion_status() -> tuple[bool, str]:
    """Return (ready, note). A false result does not start a download."""
    # The training interpreter has to exist.
    if not WORKER_PYTHON.is_file():
        # Nothing to spawn.
        return False, "diffusion not run: .venv-train is missing"
    # Ask that interpreter. The API's own venv must not gain a CUDA or diffusers install.
    try:
        # A short import check.
        checked = subprocess.run(
            [str(WORKER_PYTHON), "-c", "import diffusers"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=ROOT,
        )
    # The check itself hung.
    except subprocess.TimeoutExpired:
        # Do not start a download.
        return False, "diffusion not run: could not check the diffusers install"
    # Missing package.
    if checked.returncode != 0:
        # The approved install has not happened.
        return False, "diffusion not run: diffusers is not installed in .venv-train"
    # fp16 safetensors the worker loads. Full fp32 bins are not required.
    needed = {
        CONTROL_MODEL: ("diffusion_pytorch_model.fp16.safetensors",),
        SD_MODEL: (
            "unet/diffusion_pytorch_model.fp16.safetensors",
            "vae/diffusion_pytorch_model.fp16.safetensors",
            "text_encoder/model.fp16.safetensors",
        ),
    }
    # Both checkpoints are required. Segmentation is rendered but is not a second ControlNet.
    for repo_id, relatives in needed.items():
        # Incomplete downloads do not count.
        if not _fp16_present(repo_id, relatives):
            # Name the missing repo. Do not call from_pretrained here.
            return False, f"diffusion not run: local weights for {repo_id} are not installed"
    # The worker may load with local_files_only.
    return True, "ready"


# Parse a peak field that may be missing.
def _peak(payload: dict) -> float | None:
    """Return a float peak, or None."""
    # Worker field.
    value = payload.get("peak_vram_mib")
    # Numbers only.
    if isinstance(value, (int, float)):
        # MiB.
        return float(value)
    # Absent.
    return None


# Last JSON object on stdout.
def _last_json(stdout: str) -> dict | None:
    """Return the last JSON object, or None when stdout has none."""
    # Non-empty lines. Library logs may precede the payload.
    lines = [line for line in stdout.splitlines() if line.strip()]
    # Nothing printed.
    if not lines:
        # No payload.
        return None
    # Parse from the end so a warning line above the payload is skipped.
    for line in reversed(lines):
        # Try one line.
        try:
            # JSON object.
            payload = json.loads(line)
        # Not JSON.
        except json.JSONDecodeError:
            # Try the previous line.
            continue
        # Only objects are payloads.
        if isinstance(payload, dict):
            # Use it.
            return payload
    # No JSON object.
    return None


# Real backends. Tests replace the whole object.
class VisualizeBackends:
    """Call the workers when their weights are already on disk."""

    # Cache the diffusion check for the attempts of one request.
    def __init__(self) -> None:
        """No process is started at construction."""
        # Filled on the first inpaint call.
        self._diffusion: tuple[bool, str] | None = None

    # One diffusion attempt.
    def inpaint(
        self,
        base: Image.Image,
        mask: Image.Image,
        depth: Image.Image,
        prompt: str,
        seed: int,
    ) -> InpaintOutput:
        """Return a generated image, or not_run when weights are absent."""
        # Check once per request.
        if self._diffusion is None:
            # Does not download.
            self._diffusion = _cached_diffusion_status()
        # Unpack.
        ready, reason = self._diffusion
        # Missing install or weights.
        if not ready:
            # The service still returns the scene-graph maps.
            return InpaintOutput("not_run", reason, None, None)
        # Files the worker reads. The image is copied into memory before this directory is removed.
        with tempfile.TemporaryDirectory() as folder:
            # Root of this attempt.
            root = Path(folder)
            # Base RGB.
            base.save(root / "base.png")
            # Mask.
            mask.save(root / "mask.png")
            # Depth.
            depth.save(root / "depth.png")
            # Output path.
            out = root / "out.png"
            # Module in this repo, interpreter in .venv-train.
            command = [
                str(WORKER_PYTHON),
                "-m",
                "spacedesigner.visualize.diffusion_worker",
                "--base",
                str(root / "base.png"),
                "--mask",
                str(root / "mask.png"),
                "--depth",
                str(root / "depth.png"),
                "--out",
                str(out),
                "--prompt",
                prompt,
                "--seed",
                str(seed),
            ]
            # Run and capture.
            try:
                # The child exits before the critic or the detector starts.
                done = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=DIFFUSION_TIMEOUT_S,
                    cwd=ROOT,
                )
            # Hung child.
            except subprocess.TimeoutExpired:
                # Not a design rejection.
                return InpaintOutput("not_run", "diffusion timed out", None, None)
            # Last JSON object on stdout.
            payload = _last_json(done.stdout)
            # No payload.
            if payload is None:
                # The design is unchanged.
                return InpaintOutput("not_run", "diffusion produced no result", None, None)
            # Peak, when the worker measured one.
            peak = _peak(payload)
            # A note from the worker, or a fallback.
            note = str(payload.get("note") or "diffusion did not generate")
            # Missing weights and CUDA failures use not_run.
            if payload.get("status") != "generated" or not out.is_file():
                # Do not download from here.
                return InpaintOutput("not_run", note, None, peak)
            # Load pixels before the temporary directory is deleted.
            with Image.open(out) as handle:
                # Copy so the file can close.
                image = handle.convert("RGB").copy()
        # Generated image. The parent still composites the locked pixels.
        return InpaintOutput("generated", note, image, peak)

    # Re-detect furniture on one composited image.
    def detect(self, image: Image.Image) -> DetectOutput:
        """Re-run the saved detector, or not_run when its weights are missing."""
        # Weight file from Phase 7a.
        if not BEST_WEIGHTS.is_file():
            # Do not train a replacement.
            return DetectOutput(
                "not_run",
                "consistency not run: detector weights are missing",
                [],
                None,
            )
        # The worker interpreter.
        if not WORKER_PYTHON.is_file():
            # Cannot import ultralytics here.
            return DetectOutput("not_run", "consistency not run: .venv-train is missing", [], None)
        # Image file for the child.
        with tempfile.TemporaryDirectory() as folder:
            # Path.
            png = Path(folder) / "image.png"
            # Write RGB.
            image.save(png)
            # Detector module.
            command = [str(WORKER_PYTHON), "-m", "spacedesigner.visualize.detect_worker", str(png)]
            # Run.
            try:
                # One model, then the process exits.
                done = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=DETECT_TIMEOUT_S,
                    cwd=ROOT,
                )
            # Hung child.
            except subprocess.TimeoutExpired:
                # No boxes.
                return DetectOutput("not_run", "consistency not run: detector timed out", [], None)
            # Parse before the temp file is deleted. The JSON is in memory.
            payload = _last_json(done.stdout)
        # No JSON.
        if payload is None:
            # No boxes.
            return DetectOutput(
                "not_run",
                "consistency not run: detector produced no result",
                [],
                None,
            )
        # Worker error object.
        if "error" in payload:
            # Pass the reason through. Do not download.
            return DetectOutput("not_run", f"consistency not run: {payload['error']}", [], None)
        # Boxes.
        detections: list[Detection] = []
        # One record.
        for row in payload.get("detections", []):
            # Need a dict with a box.
            if not isinstance(row, dict) or not isinstance(row.get("xyxy"), list):
                # Skip a bad row.
                continue
            # Four numbers.
            box = row["xyxy"]
            # A short box is ignored.
            if len(box) != 4:
                # Skip.
                continue
            # Append a matcher record.
            detections.append(
                Detection(
                    category=str(row.get("category", "")),
                    score=float(row.get("score", 0.0)),
                    xyxy=(float(box[0]), float(box[1]), float(box[2]), float(box[3])),
                )
            )
        # Ok even when the list is empty. An empty list is a mismatch, not a missing weight.
        return DetectOutput("ok", "detector ran", detections, _peak(payload))

    # Advisory critic. A missing model is not_run.
    def critic(self, image_base64: str, summary: str) -> CriticOutput:
        """Ask qwen2.5vl when it is already pulled. This does not run ollama pull."""
        # Presence check only.
        if not vl_model_present():
            # The geometric checker still stands.
            return CriticOutput(
                "not_run",
                "critic not run: qwen2.5vl:7b is not pulled",
                None,
                [],
                {},
            )
        # The vision call unloads itself with keep_alive 0.
        try:
            # One advisory reading.
            payload = advise(image_base64, summary)
        # Down daemon or a bad reply.
        except RuntimeError as exc:
            # Not a rejection.
            return CriticOutput("not_run", str(exc), None, [], {})
        # Advisory. The service logs disagreements and still returns the same design.
        return CriticOutput(
            "advisory",
            "advisory only; the geometric checker was not overridden",
            bool(payload["plausible"]),
            list(payload["issues"]),
            dict(payload["flags"]),
        )


# Last ready result, kept for the process so the import subprocess runs once.
_READY_STATUS: tuple[bool, str] | None = None


# Only a positive result is cached, so installing weights later is still noticed.
def _cached_diffusion_status() -> tuple[bool, str]:
    """Return diffusion_status(), remembering a ready answer."""
    # Module-level cache.
    global _READY_STATUS
    # Reuse a previous ready answer.
    if _READY_STATUS is not None:
        # No subprocess.
        return _READY_STATUS
    # Fresh check.
    status = diffusion_status()
    # Remember success only.
    if status[0]:
        # Store it.
        _READY_STATUS = status
    # Hand back the result.
    return status


# FastAPI dependency.
def get_visualize_backends() -> VisualizeBackends:
    """Return the real backends. Tests override this."""
    # A new instance per request so the diffusion check is fresh.
    return VisualizeBackends()
