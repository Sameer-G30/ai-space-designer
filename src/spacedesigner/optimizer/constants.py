"""Named Phase 3 geometry constants grounded in the tracked notes."""

# Solver coordinates advance in five-centimetre cells.
GRID_SIZE_M = 0.05

# Low-confidence rooms lose this inset on every wall.
LOW_CONFIDENCE_MARGIN_M = 0.10

# ADA section 403.5.1 gives the usual accessible-route clear width.
MIN_CIRCULATION_WIDTH_M = 0.915

# ADA section 404.2.3 gives the minimum clear door opening.
MIN_DOOR_CLEAR_WIDTH_M = 0.815

# ADA section 304.3.1 gives the minimum circular turning diameter.
TURNING_SPACE_DIAMETER_M = 1.525

# A short deterministic limit keeps the 200-room gate bounded.
MAX_SOLVE_TIME_SECONDS = 2.0
