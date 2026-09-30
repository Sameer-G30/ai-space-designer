"""Privacy pass tests: metadata is gone, the focal length survives, bad bytes are rejected."""

# In-memory byte buffers.
import io

# pytest marks and raises.
import pytest

# Pillow builds test images with EXIF.
from PIL import Image

# Code under test.
from spacedesigner.perception.privacy import UnreadableImage, strip_metadata, to_png_bytes


# Build a JPEG that carries GPS, a camera make, and a focal length.
def jpeg_with_exif() -> bytes:
    """Return JPEG bytes with personal-looking EXIF."""
    # Plain red image.
    image = Image.new("RGB", (64, 48), (200, 30, 30))
    # Empty EXIF block to fill.
    exif = Image.Exif()
    # Camera make (personal-ish metadata).
    exif[271] = "TestCam"
    # 35 mm equivalent focal length.
    exif[41989] = 28
    # GPS sub-block with a latitude reference and value.
    gps = exif.get_ifd(0x8825)
    # Latitude reference.
    gps[1] = "N"
    # Latitude value.
    gps[2] = (12.0, 34.0, 56.0)
    # Write the GPS block back into the EXIF.
    exif[0x8825] = gps
    # Encode with the EXIF attached.
    buffer = io.BytesIO()
    # Save as JPEG.
    image.save(buffer, format="JPEG", exif=exif)
    # Return the bytes.
    return buffer.getvalue()


# The input really has the metadata, so the next test means something.
def test_fixture_contains_gps_and_make() -> None:
    """Confirm the fixture carries EXIF before stripping."""
    # Re-open the fixture.
    exif = Image.open(io.BytesIO(jpeg_with_exif())).getexif()
    # Make and GPS block are present.
    assert exif.get(271) == "TestCam"
    # GPS latitude is present.
    assert exif.get_ifd(0x8825).get(1) == "N"


# Stripped output has no EXIF, GPS, or info dict, even after re-encoding.
def test_strip_metadata_removes_exif_and_gps() -> None:
    """No EXIF or GPS survives, and the pixels do."""
    # Strip the fixture.
    clean = strip_metadata(jpeg_with_exif())
    # The in-memory image has no EXIF entries.
    assert len(clean.image.getexif()) == 0
    # The PNG that goes to the worker has none either.
    reopened = Image.open(io.BytesIO(to_png_bytes(clean.image)))
    # No EXIF after the round trip.
    assert len(reopened.getexif()) == 0
    # No leftover info entries such as a profile or a thumbnail.
    assert "exif" not in reopened.info
    # Size and colour survive.
    assert reopened.size == (64, 48)
    # Pixel colour stays close to the source (JPEG is lossy).
    assert reopened.getpixel((10, 10))[0] > 150


# The harmless focal length is kept for field-of-view; nothing else is.
def test_strip_metadata_keeps_only_the_focal_length() -> None:
    """Return the 35 mm focal length from EXIF."""
    # Strip the fixture.
    clean = strip_metadata(jpeg_with_exif())
    # The one kept number.
    assert clean.focal_35mm == 28.0


# A photo with no EXIF has no focal length.
def test_strip_metadata_without_exif_has_no_focal_length() -> None:
    """Return None when the photo carries no focal length."""
    # PNG has no EXIF.
    buffer = io.BytesIO()
    # Encode a plain image.
    Image.new("RGB", (8, 8)).save(buffer, format="PNG")
    # Strip it.
    assert strip_metadata(buffer.getvalue()).focal_35mm is None


# Non-image bytes give a readable error type.
def test_strip_metadata_rejects_non_images() -> None:
    """Raise UnreadableImage for text bytes."""
    # Text is not an image.
    with pytest.raises(UnreadableImage):
        strip_metadata(b"not an image")


# Large photos are shrunk to bound memory.
def test_strip_metadata_shrinks_large_photos() -> None:
    """Cap the longest side."""
    # Oversized canvas.
    buffer = io.BytesIO()
    # Encode it.
    Image.new("RGB", (4000, 1000)).save(buffer, format="PNG")
    # Strip it.
    clean = strip_metadata(buffer.getvalue())
    # Longest side is capped and the ratio kept.
    assert clean.image.size == (2048, 512)


# Face blur needs OpenCV, which only .venv-train has, so the test skips elsewhere.
def test_blur_faces_runs_without_faces() -> None:
    """A blank image has no faces and comes back the same size."""
    # Skip in the main venv.
    pytest.importorskip("cv2")
    # The face model is gitignored; skip when it is absent.
    from spacedesigner.perception.privacy import FACE_MODEL, blur_faces

    # Model missing on this machine.
    if not FACE_MODEL.exists():
        # Nothing to test.
        pytest.skip("face model not on disk")
    # Blank image.
    image = Image.new("RGB", (320, 240), (90, 90, 90))
    # Run the blur.
    out, count = blur_faces(image)
    # No faces, same size.
    assert count == 0
    # Size unchanged.
    assert out.size == image.size
