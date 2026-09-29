"""PNG and SVG plan renderer tests."""

# Path types pytest's temporary directory fixture.
from pathlib import Path

# Real solver supplies exact coordinates to the renderer.
from spacedesigner.optimizer import optimize

# Both required render functions are exercised.
from spacedesigner.visualize import render_png, render_svg

# Shared fixtures create one known feasible design.
from tests.phase3_samples import sample_catalog, sample_requirement, sample_scene


# Confirm both formats are materialized.
def test_plan_renderer_writes_png_and_svg(tmp_path: Path) -> None:
    """Render one solver result in both required formats."""
    # Build the source room.
    scene = sample_scene()
    # Solve one compact design.
    result = optimize(scene, sample_requirement(), sample_catalog())
    # The fixture must remain feasible.
    assert result.feasible
    # Render the raster plan.
    png_path = render_png(scene, result.design, tmp_path / "plan.png")
    # Render the vector plan.
    svg_path = render_svg(scene, result.design, tmp_path / "plan.svg")
    # Require a non-empty PNG.
    assert png_path.stat().st_size > 0
    # Require recognizable SVG markup.
    assert "<svg" in svg_path.read_text(encoding="utf-8")
