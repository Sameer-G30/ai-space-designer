"""Render exact solver coordinates as simple top-down plans."""

# html escapes user-controlled labels in SVG text.
import html

# Path accepts filesystem destinations from scripts and tests.
from pathlib import Path

# Pillow writes the required raster preview.
from PIL import Image, ImageDraw

# Locked schemas type room and design geometry.
from spacedesigner.schemas import Design, SceneGraph, SceneObject

# Pixels per metre balances readability and output size.
PIXELS_PER_METRE = 100

# Outer padding leaves room for wall strokes and labels.
PADDING_PX = 30

# Stable palette repeats deterministically by object order.
PALETTE = ("#8ecae6", "#ffb703", "#90be6d", "#f28482", "#bdb2ff", "#84a59d")


# Return world-axis dimensions for one right-angle object.
def _world_size(obj: SceneObject) -> tuple[float, float]:
    """Return floor extents after rotation."""
    # Reduce rotation to one of four quarter turns.
    quarter_turn = round(obj.rotation / 90.0) % 4
    # Swap edges for odd quarter turns.
    if quarter_turn in {1, 3}:
        # Return local width on x and local length on y.
        return obj.dimensions[1], obj.dimensions[0]
    # Return local axes unchanged.
    return obj.dimensions[0], obj.dimensions[1]


# Convert a room coordinate to image coordinates.
def _pixel_box(
    scene: SceneGraph,
    obj: SceneObject,
) -> tuple[float, float, float, float]:
    """Map one footprint to a top-left-origin pixel box."""
    # Read its rotated dimensions.
    extent_x, extent_y = _world_size(obj)
    # Compute metric minimum x.
    minimum_x = obj.position[0] - extent_x / 2
    # Compute metric maximum x.
    maximum_x = obj.position[0] + extent_x / 2
    # Compute metric minimum y.
    minimum_y = obj.position[1] - extent_y / 2
    # Compute metric maximum y.
    maximum_y = obj.position[1] + extent_y / 2
    # Map x directly from west to east.
    left = PADDING_PX + minimum_x * PIXELS_PER_METRE
    # Invert y so north appears at the top.
    top = PADDING_PX + (scene.dimensions.width - maximum_y) * PIXELS_PER_METRE
    # Map the maximum x.
    right = PADDING_PX + maximum_x * PIXELS_PER_METRE
    # Map the minimum y after inversion.
    bottom = PADDING_PX + (scene.dimensions.width - minimum_y) * PIXELS_PER_METRE
    # Return Pillow/SVG box coordinates.
    return left, top, right, bottom


# Render a vector plan without introducing another dependency.
def render_svg(scene: SceneGraph, design: Design, destination: str | Path) -> Path:
    """Write a deterministic SVG top-down plan."""
    # Normalize the output path.
    output = Path(destination)
    # Create parent directories for gitignored examples.
    output.parent.mkdir(parents=True, exist_ok=True)
    # Compute complete canvas width.
    width = round(scene.dimensions.length * PIXELS_PER_METRE + 2 * PADDING_PX)
    # Compute complete canvas height.
    height = round(scene.dimensions.width * PIXELS_PER_METRE + 2 * PADDING_PX)
    # Start the XML document and white background.
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
        ),
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        (
            f'<rect x="{PADDING_PX}" y="{PADDING_PX}" '
            f'width="{scene.dimensions.length * PIXELS_PER_METRE:.2f}" '
            f'height="{scene.dimensions.width * PIXELS_PER_METRE:.2f}" '
            'fill="none" stroke="#111111" stroke-width="4"/>'
        ),
    ]
    # Draw each object in stable design order.
    for index, obj in enumerate(design.objects):
        # Convert its footprint.
        left, top, right, bottom = _pixel_box(scene, obj)
        # Select a stable fill color.
        color = PALETTE[index % len(PALETTE)]
        # Escape the category label for XML.
        label = html.escape(obj.type)
        # Draw the footprint rectangle.
        lines.append(
            f'<rect x="{left:.2f}" y="{top:.2f}" width="{right - left:.2f}" '
            f'height="{bottom - top:.2f}" fill="{color}" stroke="#222222"/>'
        )
        # Draw the category near the footprint centre.
        lines.append(
            f'<text x="{(left + right) / 2:.2f}" y="{(top + bottom) / 2:.2f}" '
            'font-size="12" text-anchor="middle" dominant-baseline="middle">'
            f"{label}</text>"
        )
    # Close the vector document.
    lines.append("</svg>")
    # Write one line per element for readable output.
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Return the created path.
    return output


# Render a matching raster plan with Pillow.
def render_png(scene: SceneGraph, design: Design, destination: str | Path) -> Path:
    """Write a deterministic PNG top-down plan."""
    # Normalize the output path.
    output = Path(destination)
    # Create parent directories for gitignored examples.
    output.parent.mkdir(parents=True, exist_ok=True)
    # Compute raster width.
    width = round(scene.dimensions.length * PIXELS_PER_METRE + 2 * PADDING_PX)
    # Compute raster height.
    height = round(scene.dimensions.width * PIXELS_PER_METRE + 2 * PADDING_PX)
    # Create an opaque white RGB image.
    image = Image.new("RGB", (width, height), "white")
    # Create a drawing context.
    draw = ImageDraw.Draw(image)
    # Draw the room boundary.
    draw.rectangle(
        (
            PADDING_PX,
            PADDING_PX,
            width - PADDING_PX,
            height - PADDING_PX,
        ),
        outline="#111111",
        width=4,
    )
    # Draw each footprint in design order.
    for index, obj in enumerate(design.objects):
        # Convert exact metric coordinates to pixels.
        bounds = _pixel_box(scene, obj)
        # Draw the colored object rectangle.
        draw.rectangle(bounds, fill=PALETTE[index % len(PALETTE)], outline="#222222", width=1)
        # Draw a compact category label.
        draw.text((bounds[0] + 3, bounds[1] + 3), obj.type, fill="#111111")
    # Save explicitly as PNG.
    image.save(output, format="PNG")
    # Return the created path.
    return output
