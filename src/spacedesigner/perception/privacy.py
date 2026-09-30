"""Privacy pass: drop EXIF and GPS, blur faces. It runs before any model sees the photo."""

# Annotations on Python 3.11.
from __future__ import annotations

# Raw upload bytes are wrapped so Pillow can read them.
import io

# Model path.
from pathlib import Path

# Pillow decodes the upload and re-encodes only the pixels.
from PIL import Image, ImageOps

# EXIF tag id for the 35 mm equivalent focal length. It is a number, not personal data.
EXIF_FOCAL_35MM = 41989

# Largest accepted side in pixels. Bigger photos are shrunk so memory stays bounded.
MAX_SIDE_PX = 2048

# Faces smaller than this many pixels wide are not searched for (they are not identifiable).
MIN_FACE_PX = 24

# YuNet model approved for download (OpenCV Zoo, MIT licence); the bytes are gitignored.
FACE_MODEL = (
    Path(__file__).resolve().parents[3]
    / "models"
    / "pretrained"
    / "face_detection_yunet_2023mar.onnx"
)

# Minimum YuNet score. Low on purpose: a false blur costs little, a missed face costs more.
FACE_SCORE = 0.5

# Gaussian kernel is this fraction of the face width, made odd below.
BLUR_FRACTION = 0.6


# Raised when the upload is not a readable image.
class UnreadableImage(ValueError):
    """The bytes are not a supported image."""


# Result of the pixel-only re-encode.
class CleanImage:
    """A pixel-only RGB image plus the one harmless camera number kept from EXIF."""

    # Store the image and the optional focal length.
    def __init__(self, image: Image.Image, focal_35mm: float | None) -> None:
        """Hold the stripped image and the focal length in millimetres (35 mm equivalent)."""
        # RGB pixels with no metadata attached.
        self.image = image
        # Focal length used to guess the camera field of view, or None when absent.
        self.focal_35mm = focal_35mm


# Decode, read the focal length, then rebuild the image from pixels alone.
def strip_metadata(data: bytes) -> CleanImage:
    """Return pixels only. EXIF, GPS, thumbnails, and ICC profiles do not survive."""
    # Decoding can fail on any bad upload.
    try:
        # Open the bytes without touching the filesystem.
        raw = Image.open(io.BytesIO(data))
        # Force the decode now so errors surface here.
        raw.load()
    # Pillow raises several error types for bad data.
    except Exception as exc:
        # One readable error type for the route.
        raise UnreadableImage("the upload is not a readable image") from exc
    # Read the focal length before the metadata is discarded.
    focal = None
    # Some formats have no EXIF at all.
    try:
        # Value is a rational number or an int; 0 means unknown.
        value = raw.getexif().get(EXIF_FOCAL_35MM)
        # Keep only a plausible positive value.
        focal = float(value) if value and 10 <= float(value) <= 200 else None
    # A broken EXIF block must not fail the upload.
    except Exception:
        # Treat the focal length as unknown.
        focal = None
    # Apply the camera rotation to the pixels so nothing needs the Orientation tag later.
    upright = ImageOps.exif_transpose(raw)
    # Convert to plain RGB, which drops palette and alpha channels.
    rgb = upright.convert("RGB")
    # Shrink very large photos while keeping the aspect ratio.
    rgb.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX))
    # Copy the pixel bytes into a fresh image so no info dict is carried over.
    clean = Image.frombytes("RGB", rgb.size, rgb.tobytes())
    # Return the clean image with the single number kept.
    return CleanImage(clean, focal)


# Re-encode to PNG bytes so a subprocess receives a file with no metadata.
def to_png_bytes(image: Image.Image) -> bytes:
    """Encode an image as PNG without any metadata."""
    # In-memory buffer for the encoded bytes.
    buffer = io.BytesIO()
    # PNG writes no EXIF unless asked.
    image.save(buffer, format="PNG")
    # Return the bytes.
    return buffer.getvalue()


# Find face boxes with the YuNet detector through OpenCV (model file is gitignored).
def detect_faces(image: Image.Image) -> list[tuple[int, int, int, int]]:
    """Return face boxes as x, y, width, height in pixels."""
    # OpenCV and numpy are only in .venv-train, so import them here.
    import cv2
    import numpy as np

    # A missing model must stop the pipeline; skipping the blur would break the privacy rule.
    if not FACE_MODEL.exists():
        # Name the file so the caller can say what is missing.
        raise FileNotFoundError(f"missing face model {FACE_MODEL}")
    # OpenCV expects BGR pixels.
    bgr = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
    # Build the detector for this image size with a low score so weak faces are still blurred.
    detector = cv2.FaceDetectorYN.create(
        str(FACE_MODEL), "", (image.width, image.height), FACE_SCORE, 0.3, 5000
    )
    # Rows are x, y, w, h, five landmarks, and a score; None means no face.
    _, faces = detector.detect(bgr)
    # Nothing found.
    if faces is None:
        # No boxes.
        return []
    # Keep plain ints, dropping boxes that are too small to identify.
    return [(int(f[0]), int(f[1]), int(f[2]), int(f[3])) for f in faces if f[2] >= MIN_FACE_PX]


# Blur each face box in place on a copy of the image.
def blur_faces(image: Image.Image) -> tuple[Image.Image, int]:
    """Return the image with faces blurred and the number of blurred boxes."""
    # OpenCV and numpy are only in .venv-train, so import them here.
    import cv2
    import numpy as np

    # Work on a writable array copy.
    pixels = np.array(image)
    # Boxes to blur.
    boxes = detect_faces(image)
    # Blur each box with a strong Gaussian.
    for x, y, w, h in boxes:
        # Odd kernel size scaled to the face.
        kernel = max(3, int(w * BLUR_FRACTION) // 2 * 2 + 1)
        # Replace the face region with its blurred copy.
        # Clip the box to the image so slicing never wraps.
        x, y = max(x, 0), max(y, 0)
        pixels[y : y + h, x : x + w] = cv2.GaussianBlur(
            pixels[y : y + h, x : x + w], (kernel, kernel), 0
        )
    # Back to a Pillow image plus the count.
    return Image.fromarray(pixels), len(boxes)
