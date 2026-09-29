"""Build the synthetic-price furniture catalog from measured sizes and cleaned Objaverse meshes.

Dimensions come from SUN RGB-D 3D boxes (measured) and from cleaned Objaverse mesh proportions.
`style_tags` and `material` are project labels, not 3D-FUTURE labels. Prices are synthetic INR.
"""

# Annotations on Python 3.11.
from __future__ import annotations

# Seeded randomness keeps the catalog reproducible.
import random

# Tallies.
from collections import Counter

# Paths and helpers.
from spacedesigner.data.common import (
    cleaning_dir,
    processed_dir,
    read_json,
    read_jsonl,
    write_json,
    write_jsonl,
)

# The 26 taxonomy classes gate every category value.
from spacedesigner.data.taxonomy import FURNITURE_CLASSES

# The locked catalog contract validates every row before it is written.
from spacedesigner.schemas.catalog import CatalogItem

# Seed for every random choice in this module.
SEED = 20260929

# Items built from SUN size tiers per class (mesh items are added on top).
SUN_ITEMS_PER_CLASS = 11

# A mesh item is dropped when an edge falls outside this multiple of the SUN p05..p95 range.
ENVELOPE_LOW, ENVELOPE_HIGH = 0.5, 1.5

# Project style labels (not 3D-FUTURE labels).
STYLES = (
    "modern",
    "scandinavian",
    "minimalist",
    "industrial",
    "traditional",
    "rustic",
    "mid_century",
    "bohemian",
    "contemporary",
)

# Project material labels per category (not 3D-FUTURE labels).
MATERIALS: dict[str, tuple[str, ...]] = {
    "bed": ("solid_wood", "engineered_wood", "metal", "upholstered_fabric"),
    "sofa": ("upholstered_fabric", "leather", "solid_wood"),
    "armchair": ("upholstered_fabric", "leather", "rattan", "solid_wood"),
    "chair": ("solid_wood", "plastic", "metal", "upholstered_fabric", "bamboo"),
    "stool": ("solid_wood", "metal", "plastic", "bamboo"),
    "bench": ("solid_wood", "metal", "upholstered_fabric"),
    "ottoman": ("upholstered_fabric", "leather", "rattan"),
    "table": ("solid_wood", "engineered_wood", "glass", "metal"),
    "desk": ("engineered_wood", "solid_wood", "metal", "bamboo"),
    "coffee_table": ("solid_wood", "glass", "metal", "engineered_wood"),
    "side_table": ("solid_wood", "metal", "glass", "bamboo"),
    "nightstand": ("solid_wood", "engineered_wood", "metal"),
    "dresser": ("solid_wood", "engineered_wood"),
    "cabinet": ("engineered_wood", "solid_wood", "metal"),
    "shelf": ("engineered_wood", "solid_wood", "metal", "bamboo"),
    "tv_stand": ("engineered_wood", "solid_wood", "metal"),
    "tv": ("plastic",),
    "lamp": ("metal", "glass", "bamboo", "plastic"),
    "mirror": ("glass", "solid_wood", "metal"),
    "wall_art": ("engineered_wood", "glass", "metal"),
    "curtain": ("cotton_fabric", "linen_fabric", "polyester_fabric"),
    "plant": ("plastic",),
    "pillow": ("cotton_fabric", "linen_fabric", "polyester_fabric"),
}

# Synthetic base price in INR for a median-sized item of each class. These are project
# assumptions for plausible Indian retail levels, not scraped values.
BASE_PRICE_INR: dict[str, float] = {
    "bed": 28000,
    "sofa": 32000,
    "armchair": 12000,
    "chair": 3500,
    "stool": 1800,
    "bench": 6500,
    "ottoman": 3200,
    "table": 14000,
    "desk": 9500,
    "coffee_table": 6500,
    "side_table": 3000,
    "nightstand": 4500,
    "dresser": 16000,
    "cabinet": 13000,
    "shelf": 7500,
    "tv_stand": 8500,
    "tv": 32000,
    "lamp": 2200,
    "mirror": 3000,
    "wall_art": 2500,
    "curtain": 3500,
    "plant": 1200,
    "pillow": 600,
}

# Material price multiplier (synthetic).
MATERIAL_FACTOR: dict[str, float] = {
    "solid_wood": 1.35,
    "engineered_wood": 0.85,
    "metal": 1.0,
    "upholstered_fabric": 1.1,
    "leather": 1.7,
    "glass": 1.15,
    "rattan": 1.3,
    "plastic": 0.6,
    "bamboo": 1.05,
    "cotton_fabric": 1.0,
    "linen_fabric": 1.25,
    "polyester_fabric": 0.75,
}

# Size tier names in order.
TIERS = ("small", "medium", "large")


def tier_dims(prior: dict, tier: str, rng: random.Random) -> tuple[float, float, float]:
    """Sample (length, width, height) inside the measured band of one size tier."""
    # Percentile bands: small = p25..p50 below the median, medium = p40-ish, large = p50..p75.
    band = {"small": ("p25", "p25"), "medium": ("p25", "p75"), "large": ("p50", "p75")}[tier]
    # Sample each edge between the two percentiles of the band.
    out = []
    # Each measured edge.
    for edge in ("length_m", "width_m", "height_m"):
        # Lower percentile value.
        lo = prior[edge][band[0]]
        # Upper percentile value.
        hi = prior[edge][band[1]]
        # Small tier samples a bit under p25 so it differs from the medium band.
        if tier == "small":
            # Between p05 and p25.
            lo, hi = prior[edge]["p05"], prior[edge]["p25"]
        # Uniform draw inside the band.
        out.append(rng.uniform(lo, hi))
    # Length is the longer floor edge by definition.
    length, width = max(out[0], out[1]), min(out[0], out[1])
    # Round to centimetres and keep positive.
    return round(length, 2), round(width, 2), round(out[2], 2)


def synthetic_price(
    category: str, dims: tuple[float, float, float], material: str, prior: dict, rng: random.Random
) -> float:
    """Synthetic INR price: class base x size factor x material factor x lognormal noise."""
    # Volume of this item.
    volume = dims[0] * dims[1] * dims[2]
    # Median volume from the measured percentiles.
    median = prior["length_m"]["p50"] * prior["width_m"]["p50"] * prior["height_m"]["p50"]
    # Bigger items cost more, with diminishing returns.
    size_factor = (volume / median) ** 0.6
    # Multiplicative noise around 1.
    noise = rng.lognormvariate(0.0, 0.15)
    # Combine and round to the nearest 50 rupees.
    price = BASE_PRICE_INR[category] * size_factor * MATERIAL_FACTOR[material] * noise
    # Never below 100 INR.
    return float(max(100, round(price / 50) * 50))


def pick_style(rng: random.Random) -> list[str]:
    """Pick one to three distinct project style tags."""
    # Number of tags.
    count = rng.choice((1, 2, 2, 3))
    # Distinct tags in a stable order.
    return sorted(rng.sample(STYLES, count))


def build_catalog() -> tuple[list[dict], dict, dict]:
    """Return (catalog rows, provenance by item_id, build stats)."""
    # Seeded generator.
    rng = random.Random(SEED)
    # Measured priors from SUN RGB-D.
    priors = read_json(cleaning_dir() / "layout_priors.json")["sun_rgbd"]["object_size"]
    # Cleaned Objaverse manifest.
    meshes = read_jsonl(processed_dir("objaverse") / "manifest.jsonl")
    # Output rows.
    rows: list[dict] = []
    # Provenance by item id.
    provenance: dict[str, dict] = {}
    # Reasons for dropped candidates.
    dropped: Counter = Counter()
    # Running index per class.
    counters: Counter = Counter()
    # Classes with no measured prior have no catalog items.
    skipped_classes = [c for c in FURNITURE_CLASSES if c not in priors]

    def add(category: str, dims: tuple[float, float, float], material: str, source: dict) -> None:
        """Validate one item against the locked schema and record it."""
        # Next index for this class.
        counters[category] += 1
        # Stable id.
        item_id = f"cat_{category}_{counters[category]:03d}"
        # Row with exactly the schema fields; embedding stays null.
        row = {
            "item_id": item_id,
            "category": category,
            "dims": {"length": dims[0], "width": dims[1], "height": dims[2]},
            "price": synthetic_price(category, dims, material, priors[category], rng),
            "style_tags": pick_style(rng),
            "material": material,
            "embedding": None,
        }
        # Validation raises if the contract is broken.
        CatalogItem.model_validate(row)
        # Record the row and where it came from.
        rows.append(row)
        # Provenance lives outside the locked schema.
        provenance[item_id] = source

    # Mesh-based items first: real proportions from cleaned Objaverse meshes.
    for mesh in meshes:
        # Class and its measured prior.
        category = mesh["taxonomy_class"]
        # Classes without a prior cannot be anchored.
        if category not in priors:
            # Count it.
            dropped["mesh_class_has_no_sun_prior"] += 1
            # Next mesh.
            continue
        # Measured prior.
        prior = priors[category]
        # Draw a target length inside the measured interquartile range.
        target = rng.uniform(prior["length_m"]["p25"], prior["length_m"]["p75"])
        # Scale factor from the normalized mesh (already at the p50 length).
        factor = target / mesh["dims_m"]["length"]
        # Scaled dimensions in metres.
        dims = (
            round(mesh["dims_m"]["length"] * factor, 2),
            round(mesh["dims_m"]["width"] * factor, 2),
            round(mesh["dims_m"]["height"] * factor, 2),
        )
        # Any edge outside the plausible envelope drops the mesh from the catalog.
        envelope_ok = all(
            ENVELOPE_LOW * prior[edge]["p05"] <= value <= ENVELOPE_HIGH * prior[edge]["p95"]
            for edge, value in zip(("length_m", "width_m", "height_m"), dims)
        )
        # Positive dimensions are required by the schema.
        if not envelope_ok or min(dims) <= 0:
            # Count it.
            dropped["mesh_dims_outside_sun_envelope"] += 1
            # Next mesh.
            continue
        # Material from the class list.
        material = rng.choice(MATERIALS[category])
        # Add the item.
        add(
            category,
            dims,
            material,
            {
                "source": "objaverse_mesh_proportions_scaled_into_sun_length_band",
                "objaverse_uid": mesh["uid"],
                "objaverse_license": mesh["license"],
                "sun_prior_n": prior["n"],
            },
        )
    # SUN-tier items: measured percentile bands per class.
    for category in FURNITURE_CLASSES:
        # No prior, no items.
        if category not in priors:
            # Next class.
            continue
        # Measured prior.
        prior = priors[category]
        # Items for this class.
        for index in range(SUN_ITEMS_PER_CLASS):
            # Cycle through the three tiers.
            tier = TIERS[index % len(TIERS)]
            # Dimensions inside the tier band.
            dims = tier_dims(prior, tier, rng)
            # Material from the class list.
            material = rng.choice(MATERIALS[category])
            # Add the item.
            add(
                category,
                dims,
                material,
                {
                    "source": "sun_rgbd_annotation3Dfinal_percentile_tier",
                    "tier": tier,
                    "sun_prior_n": prior["n"],
                },
            )
    # Build stats for the report.
    stats = {
        "items": len(rows),
        "items_from_objaverse_meshes": sum(1 for p in provenance.values() if "objaverse_uid" in p),
        "items_from_sun_tiers": sum(1 for p in provenance.values() if "tier" in p),
        "items_by_category": dict(sorted(Counter(r["category"] for r in rows).items())),
        "categories_without_items": skipped_classes,
        "mesh_candidates_dropped": dict(sorted(dropped.items())),
        "price_inr": {
            "min": min(r["price"] for r in rows),
            "max": max(r["price"] for r in rows),
            "median": sorted(r["price"] for r in rows)[len(rows) // 2],
        },
        "prices_are_synthetic": True,
    }
    # Give everything back.
    return rows, provenance, stats


def run() -> dict:
    """Build the catalog, write the JSONL and provenance, and return the stats."""
    # Build in memory.
    rows, provenance, stats = build_catalog()
    # Tracked JSONL, checkable without the database.
    write_jsonl(cleaning_dir() / "furniture_catalog.jsonl", rows)
    # Tracked provenance sidecar (source per item; not part of the locked schema).
    write_json(cleaning_dir() / "furniture_catalog_provenance.json", provenance)
    # Tracked stats.
    write_json(cleaning_dir() / "furniture_catalog_summary.json", stats)
    # Give the stats back.
    return stats
