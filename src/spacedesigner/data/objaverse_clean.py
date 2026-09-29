"""Validate, normalize, and compress the 160 acquired Objaverse GLBs with trimesh.

Only the 160 files already on disk are used. Nothing is downloaded.
"""

# Annotations on Python 3.11.
from __future__ import annotations

# Parses the license log.
# Tallies.
from collections import Counter

# Array math for the transforms.
import numpy as np

# Mesh loading, transforms, and GLB export.
import trimesh

# Texture resizing.
from PIL import Image

# Paths and helpers.
from spacedesigner.data.common import (
    cleaning_dir,
    processed_dir,
    read_json,
    read_jsonl,
    repo_root,
    write_json,
    write_jsonl,
)

# LVIS category -> taxonomy class. Categories with no taxonomy class are dropped as unmapped.
LVIS_TO_TAXONOMY: dict[str, str | None] = {
    "armchair": "armchair",  # armchair
    "bed": "bed",  # bed
    "bench": "bench",  # bench
    "bookcase": "shelf",  # bookcase is a shelf unit
    "bunk_bed": "bed",  # same synonym as SUN bunk_bed
    "cabinet": "cabinet",  # cabinet
    "chair": "chair",  # chair
    "chaise_longue": "armchair",  # lounge seat, same class as SUN lounge_chair
    "coffee_table": "coffee_table",  # coffee table
    "crib": None,  # no taxonomy class for cribs
    "cupboard": "cabinet",  # cupboard is a cabinet
    "desk": "desk",  # desk
    "dining_table": "table",  # SUN dining_table maps to table
    "drawer": None,  # a part or a chest; ambiguous, dropped
    "dresser": "dresser",  # dresser
    "file_cabinet": "cabinet",  # cabinet
    "folding_chair": "chair",  # chair
    "footstool": "ottoman",  # SUN footrest maps to ottoman
    "futon": "sofa",  # sofa bed
    "headboard": None,  # a bed part, not a whole piece
    "highchair": "chair",  # SUN child_chair maps to chair
    "kitchen_table": "table",  # table
    "lamp": "lamp",  # lamp
    "loveseat": "sofa",  # small sofa
    "mattress": None,  # not a taxonomy class
    "music_stool": "stool",  # SUN piano_stool maps to stool
    "ottoman": "ottoman",  # ottoman
    "recliner": "armchair",  # SUN recliner maps to armchair
    "rocking_chair": "chair",  # chair
    "sofa": "sofa",  # sofa
    "sofa_bed": "sofa",  # SUN sofa_bed maps to sofa
    "step_stool": "stool",  # SUN stepstool maps to stool
    "stool": "stool",  # stool
    "table": "table",  # table
    "table_lamp": "lamp",  # lamp
    "wardrobe": "cabinet",  # SUN/NYU wardrobe maps to cabinet
}

# Textures larger than this many pixels on a side are shrunk to it.
MAX_TEXTURE_SIDE = 1024

# Files at or above this size are reported as "large" and compressed harder.
LARGE_BYTES = 5 * 1024 * 1024


def load_scene(path) -> trimesh.Scene | None:
    """Load a GLB into a scene, or return None when it does not load or holds no triangles."""
    # trimesh raises many different errors on corrupt files, so catch broadly and report None.
    try:
        # force="scene" keeps the node graph so transforms compose correctly.
        scene = trimesh.load(str(path), force="scene")
    except Exception:  # noqa: BLE001 - any loader error means the asset is dropped
        # Unreadable file.
        return None
    # Only triangle meshes count as furniture.
    meshes = [g for g in scene.geometry.values() if isinstance(g, trimesh.Trimesh)]
    # No faces at all.
    if not meshes or sum(len(m.faces) for m in meshes) == 0:
        # Nothing to use.
        return None
    # Loaded.
    return scene


def dump_to_meshes(scene: trimesh.Scene) -> list[trimesh.Trimesh]:
    """Return every triangle mesh in world space (node transforms baked in)."""
    # Bake the scene graph into a flat mesh list.
    dumped = scene.dump(concatenate=False)
    # Keep triangle meshes only.
    return [m for m in dumped if isinstance(m, trimesh.Trimesh) and len(m.faces) > 0]


def choose_up_axis(extents_y_up: np.ndarray, target_ratio: float | None) -> str:
    """Pick "y" (glTF standard) or "z" as the up axis using the class height-to-length ratio.

    Objaverse GLBs follow glTF (Y up), but some authors exported Z up. For each candidate the
    height over the longer floor edge is compared, in log space, to the SUN RGB-D median for the
    class. With no class prior the glTF default is kept.
    """
    # No prior for this class: trust the glTF convention.
    if target_ratio is None:
        # Default.
        return "y"
    # Candidate 1: Y up. Height is Y, floor edges are X and Z.
    ratio_y = extents_y_up[1] / max(extents_y_up[0], extents_y_up[2])
    # Candidate 2: Z up. Height is Z, floor edges are X and Y.
    ratio_z = extents_y_up[2] / max(extents_y_up[0], extents_y_up[1])
    # Log distance to the target for each.
    dist_y = abs(np.log(max(ratio_y, 1e-6)) - np.log(target_ratio))
    # Second candidate.
    dist_z = abs(np.log(max(ratio_z, 1e-6)) - np.log(target_ratio))
    # Choose the closer one; ties keep Y.
    return "z" if dist_z < dist_y - 0.1 else "y"


def shrink_textures(meshes: list[trimesh.Trimesh]) -> int:
    """Downscale any base-colour texture larger than MAX_TEXTURE_SIDE. Return how many shrank."""
    # Count of shrunk textures.
    shrunk = 0
    # Look at every mesh.
    for mesh in meshes:
        # Only PBR materials carry the base colour texture we handle.
        material = getattr(mesh.visual, "material", None)
        # Texture image, when present.
        image = getattr(material, "baseColorTexture", None)
        # No texture.
        if image is None:
            # Next mesh.
            continue
        # Shrink only when a side is too large.
        if max(image.size) > MAX_TEXTURE_SIDE:
            # Scale factor.
            factor = MAX_TEXTURE_SIDE / max(image.size)
            # New size with a floor of one pixel.
            size = (max(1, int(image.width * factor)), max(1, int(image.height * factor)))
            # Resample with a high-quality filter.
            material.baseColorTexture = image.resize(size, Image.LANCZOS)
            # Count it.
            shrunk += 1
    # Give the count back.
    return shrunk


def normalize_meshes(
    meshes: list[trimesh.Trimesh], target_length_m: float | None, target_ratio: float | None
) -> tuple[list[trimesh.Trimesh], dict]:
    """Fix the up axis, centre on the floor, and scale to metres. Returns (meshes, info)."""
    # Bounds of everything together, as a (2, 3) array.
    lo = np.min([m.bounds[0] for m in meshes], axis=0)
    # Upper corner.
    hi = np.max([m.bounds[1] for m in meshes], axis=0)
    # Extent per axis as loaded.
    extents = hi - lo
    # Choose which axis is up.
    up = choose_up_axis(extents, target_ratio)
    # Z-up sources rotate -90 degrees about X so that Z becomes Y.
    rotation = (
        trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]) if up == "z" else np.eye(4)
    )
    # Apply the rotation to every mesh (copies, so the loaded scene is untouched).
    rotated = [m.copy() for m in meshes]
    # Rotate each copy.
    for mesh in rotated:
        # In-place transform on the copy.
        mesh.apply_transform(rotation)
    # New bounds after rotation.
    lo = np.min([m.bounds[0] for m in rotated], axis=0)
    # Upper corner.
    hi = np.max([m.bounds[1] for m in rotated], axis=0)
    # Floor edges are X and Z; height is Y.
    floor_long = float(max(hi[0] - lo[0], hi[2] - lo[2]))
    # Uniform scale so the longer floor edge equals the class median length from SUN RGB-D.
    scale = (target_length_m / floor_long) if target_length_m and floor_long > 0 else 1.0
    # Move the footprint centre to the origin and the bottom to y = 0, then scale.
    shift = np.array([-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2])
    # Apply shift then scale to every mesh.
    for mesh in rotated:
        # Translate to the origin.
        mesh.apply_translation(shift)
        # Uniform scale about the origin.
        mesh.apply_scale(scale)
    # Final dimensions in metres: length (longer floor edge), width, height.
    size = (hi - lo) * scale
    # Sort the two floor edges so length >= width.
    length, width = sorted((float(size[0]), float(size[2])), reverse=True)
    # Describe what was done.
    return rotated, {
        "up_axis_source": up,
        "scale_factor": round(float(scale), 6),
        "dims_m": {
            "length": round(length, 4),
            "width": round(width, 4),
            "height": round(float(size[1]), 4),
        },
    }


def clean_asset(record: dict, size_priors: dict, out_dir) -> tuple[dict | None, str | None]:
    """Clean one asset. Returns (manifest_row, None) or (None, drop_reason)."""
    # Map the LVIS category.
    taxonomy = LVIS_TO_TAXONOMY.get(record["category"])
    # No taxonomy class.
    if taxonomy is None:
        # Dropped as unmapped.
        return None, "unmapped_lvis_category"
    # Source file.
    source = repo_root() / record["relative_path"]
    # Missing file.
    if not source.exists():
        # Nothing to load.
        return None, "file_missing"
    # Load with trimesh.
    scene = load_scene(source)
    # Failed to load.
    if scene is None:
        # Dropped.
        return None, "trimesh_load_failed"
    # Flatten to world-space meshes.
    meshes = dump_to_meshes(scene)
    # Nothing left after flattening.
    if not meshes:
        # Dropped.
        return None, "no_triangles"
    # Any non-finite vertex breaks normalization.
    if not all(np.isfinite(m.vertices).all() for m in meshes):
        # Dropped.
        return None, "non_finite_vertices"
    # SUN RGB-D prior for the class, when published.
    prior = size_priors.get(taxonomy)
    # Median longer floor edge.
    target_length = prior["length_m"]["p50"] if prior else None
    # Median height over length.
    target_ratio = prior["height_m"]["p50"] / prior["length_m"]["p50"] if prior else None
    # Degenerate flat or line meshes cannot be normalized.
    lo = np.min([m.bounds[0] for m in meshes], axis=0)
    # Upper corner.
    hi = np.max([m.bounds[1] for m in meshes], axis=0)
    # Any zero extent is degenerate.
    if (hi - lo).min() <= 1e-9:
        # Dropped.
        return None, "degenerate_extent"
    # Normalize.
    normalized, info = normalize_meshes(meshes, target_length, target_ratio)
    # Merge duplicate vertices to shrink the file.
    for mesh in normalized:
        # Merge in place.
        mesh.merge_vertices()
    # Shrink big textures.
    shrunk = shrink_textures(normalized)
    # Output path keeps the uid.
    target = out_dir / f"{record['uid']}.glb"
    # Export a fresh scene made of the cleaned meshes.
    trimesh.Scene(normalized).export(str(target))
    # One manifest row.
    return {
        "uid": record["uid"],
        "lvis_category": record["category"],
        "taxonomy_class": taxonomy,
        "license": record["license"],
        "source_bytes": record["bytes"],
        "cleaned_bytes": target.stat().st_size,
        "was_large": record["bytes"] >= LARGE_BYTES,
        "n_faces": int(sum(len(m.faces) for m in normalized)),
        "textures_shrunk": shrunk,
        "cleaned_path": str(target.relative_to(repo_root())),
        **info,
    }, None


def run() -> dict:
    """Clean all 160 assets, write the manifest and a summary, and return the summary."""
    # Output folder (gitignored).
    out_dir = processed_dir("objaverse")
    # Size priors mined from SUN RGB-D drive the scale and up-axis choice.
    priors = read_json(cleaning_dir() / "layout_priors.json")["sun_rgbd"]["object_size"]
    # License log, one row per acquired asset.
    records = read_jsonl(repo_root() / "datasets" / "metadata" / "objaverse_asset_licenses.jsonl")
    # Good rows.
    rows: list[dict] = []
    # Drop reasons.
    dropped: Counter = Counter()
    # Asset uids dropped, with reasons.
    dropped_assets: list[dict] = []
    # Clean each.
    for record in records:
        # One asset.
        row, reason = clean_asset(record, priors, out_dir)
        # Dropped.
        if row is None:
            # Count and remember.
            dropped[reason] += 1
            # Remember which uid.
            dropped_assets.append(
                {"uid": record["uid"], "category": record["category"], "reason": reason}
            )
            # Next asset.
            continue
        # Kept.
        rows.append(row)
    # Manifest goes with the meshes (gitignored) and a copy of the summary is tracked.
    write_jsonl(out_dir / "manifest.jsonl", rows)
    # Byte totals.
    source_total = sum(r["source_bytes"] for r in rows)
    # Cleaned total.
    cleaned_total = sum(r["cleaned_bytes"] for r in rows)
    # Summary.
    summary = {
        "assets_in_license_log": len(records),
        "assets_cleaned": len(rows),
        "assets_dropped": dict(sorted(dropped.items())),
        "dropped_assets": dropped_assets,
        "taxonomy_class_histogram": dict(
            sorted(Counter(r["taxonomy_class"] for r in rows).items())
        ),
        "up_axis_source_histogram": dict(Counter(r["up_axis_source"] for r in rows)),
        "license_histogram": dict(Counter(r["license"] for r in rows)),
        "source_bytes": source_total,
        "cleaned_bytes": cleaned_total,
        "large_files": sum(1 for r in rows if r["was_large"]),
        "scale_rule": (
            "Objaverse has no real-world unit. The longer floor edge of each mesh is scaled to the "
            "SUN RGB-D median length of its class, so mesh proportions are real and mesh size is "
            "SUN-anchored."
        ),
        "up_axis_rule": (
            "glTF Y-up by default; Z-up is chosen when its height/length ratio is closer to the "
            "SUN RGB-D median for the class."
        ),
    }
    # Tracked summary.
    write_json(cleaning_dir() / "objaverse_summary.json", summary)
    # Give it back.
    return summary
