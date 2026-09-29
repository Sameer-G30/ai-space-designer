"""Deterministic bill-of-material aggregation."""

# defaultdict accumulates repeated catalog identifiers.
from collections import defaultdict

# BomLine is the API-safe aggregate record.
from spacedesigner.optimizer.models import BomLine

# CatalogItem supplies item metadata and validated prices.
from spacedesigner.schemas import CatalogItem


# Aggregate selected catalog rows by stable item identifier.
def build_bom(selected_items: list[CatalogItem]) -> list[BomLine]:
    """Build stable BOM lines whose totals equal the purchased-item cost."""
    # Store the count for each selected item.
    quantities: dict[str, int] = defaultdict(int)
    # Store one metadata record for each selected identifier.
    by_id: dict[str, CatalogItem] = {}
    # Count every selected catalog row.
    for item in selected_items:
        # Increment this item's quantity.
        quantities[item.item_id] += 1
        # Keep the validated item for line metadata.
        by_id[item.item_id] = item
    # Build lines in identifier order for reproducibility.
    return [
        # Validate each computed aggregate.
        BomLine(
            # Preserve the catalog identifier.
            item_id=item_id,
            # Preserve the taxonomy category.
            category=by_id[item_id].category,
            # Report the accumulated quantity.
            qty=quantities[item_id],
            # Preserve the unit price.
            unit_price=by_id[item_id].price,
            # Compute the exact line total from quantity and unit price.
            line_total=quantities[item_id] * by_id[item_id].price,
        )
        # Sort identifiers so output does not depend on selection order.
        for item_id in sorted(quantities)
    ]
