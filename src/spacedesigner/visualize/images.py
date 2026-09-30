"""PNG encoding for the visualize response. No new image library."""

# Annotations on Python 3.11.
from __future__ import annotations

# Base64 fields on the JSON response.
import base64

# In-memory PNG bytes.
import io

# Arrays from the rasterizer.
import numpy as np

# Pillow is already a dependency.
from PIL import Image


# Encode one array as a PNG data payload without the data-URL prefix.
def png_base64(array: np.ndarray) -> str:
    """Return base64 PNG bytes for a gray or RGB uint8 array."""
    # Pillow accepts HxW and HxWx3 uint8 arrays.
    image = Image.fromarray(array)
    # Buffer instead of a file. The caller decides whether to keep the PNG.
    buffer = io.BytesIO()
    # Lossless PNG so unchanged pixels can be compared exactly.
    image.save(buffer, format="PNG")
    # ASCII base64 for JSON.
    return base64.b64encode(buffer.getvalue()).decode("ascii")
