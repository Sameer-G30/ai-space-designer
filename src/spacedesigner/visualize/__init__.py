"""Plan rendering, plus Phase 9 scene-graph maps in the sibling modules.

render_png and render_svg are unchanged. Depth, inpainting, and the critic are not
imported here, so a plan import does not load a GPU library.
"""

# render_png and render_svg expose the two required plan formats.
from spacedesigner.visualize.plan2d import render_png, render_svg

# Keep the package surface explicit.
__all__ = ["render_png", "render_svg"]
