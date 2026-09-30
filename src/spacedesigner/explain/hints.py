"""Previous poses turned into CP-SAT cell hints. Hints are not extra constraints."""

# Catalog lookup and the grid the solver already uses.
from spacedesigner.optimizer.constants import GRID_SIZE_M
from spacedesigner.optimizer.stage1_cpsat import _ceil_cells

# Stored objects carry centres. The solver wants start cells.
from spacedesigner.schemas import CatalogItem, Design

# Prefix Stage 1 writes on every purchased object id.
CATALOG_PREFIX = "catalog::"


# Read the catalog item id and the placement index from a Stage 1 object id.
def catalog_identity(object_id: str) -> tuple[str, int] | None:
    """Return (item_id, index) for a purchased object, or None for a kept object."""
    # Kept furniture uses the user's id.
    if not object_id.startswith(CATALOG_PREFIX):
        # Not a catalog row.
        return None
    # catalog::{item_id}::{index}. Item ids in this catalog contain no extra colons.
    parts = object_id.split("::")
    # A malformed id is not a hint source.
    if len(parts) != 3:
        # Caller skips it.
        return None
    # The index is the placement order from the solve that wrote the id.
    try:
        # Parse the suffix.
        index = int(parts[2])
    # A non-numeric suffix is not a Stage 1 id.
    except ValueError:
        # Skip.
        return None
    # Item id plus the order it was placed in.
    return parts[1], index


# Purchased rows in the order that reproduces Stage 1 object ids.
def selection_from_design(
    design: Design,
    catalog: tuple[CatalogItem, ...],
) -> list[CatalogItem]:
    """Return the catalog rows the design placed, in placement-index order."""
    # Index the catalog once.
    by_id = {item.item_id: item for item in catalog}
    # (index, item) pairs before sorting.
    found: list[tuple[int, CatalogItem]] = []
    # Walk the design, including kept objects, and keep only purchases.
    for obj in design.objects:
        # Parse the id.
        identity = catalog_identity(obj.id)
        # A kept object has nothing to re-select.
        if identity is None:
            # Next object.
            continue
        # Item id and placement index.
        item_id, index = identity
        # The row must still be in the catalog.
        item = by_id.get(item_id)
        # A deleted catalog row cannot be placed again.
        if item is None:
            # Say which id is missing.
            raise ValueError(f"catalog item '{item_id}' is not in the catalog")
        # Keep the index so object ids stay stable.
        found.append((index, item))
    # Stage 1 enumerates the selection in this order.
    found.sort(key=lambda pair: pair[0])
    # The rows only.
    return [item for _, item in found]


# Cell hints for items the previous design placed.
def hints_from_design(
    design: Design,
    catalog: tuple[CatalogItem, ...],
) -> dict[str, tuple[int, int, int]]:
    """Map item id to (start x cell, start y cell, rotation bit)."""
    # Index the catalog once.
    by_id = {item.item_id: item for item in catalog}
    # Hints keyed by catalog item id. One purchase per category keeps the key unique.
    hints: dict[str, tuple[int, int, int]] = {}
    # Walk placed objects.
    for obj in design.objects:
        # Parse the id.
        identity = catalog_identity(obj.id)
        # Kept objects are fixed by constraints, not by hints.
        if identity is None:
            # Next object.
            continue
        # Item id is the hint key.
        item_id, _index = identity
        # Need the true local edges, because the stored dimensions are the catalog size.
        item = by_id.get(item_id)
        # Skip an id the catalog no longer has. selection_from_design reports that case.
        if item is None:
            # Next object.
            continue
        # Quarter turns. Stage 1 only emits 0 and 90, and the bit is 1 for a swapped footprint.
        quarter = round(obj.rotation / 90.0) % 4
        # Odd quarters swap length and width.
        rotated = 1 if quarter % 2 == 1 else 0
        # Local edges in cells, using the same rounding as the solver.
        base_x = _ceil_cells(item.dims.length)
        # Width is independent.
        base_y = _ceil_cells(item.dims.width)
        # World cell counts after the swap.
        extent_x = base_y if rotated else base_x
        # The other axis.
        extent_y = base_x if rotated else base_y
        # The stored position is the centre of the cell footprint, not of the raw metres.
        start_x = int(round((obj.position[0] - extent_x * GRID_SIZE_M / 2) / GRID_SIZE_M))
        # Same conversion on y.
        start_y = int(round((obj.position[1] - extent_y * GRID_SIZE_M / 2) / GRID_SIZE_M))
        # One hint for this item.
        hints[item_id] = (start_x, start_y, rotated)
    # The table optimize() reads.
    return hints
