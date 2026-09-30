"""Map a placed catalog id to a cleaned Objaverse GLB. Missing meshes stay boxes."""

# Annotations on Python 3.11.
from __future__ import annotations

# JSON sidecar written in Phase 2b.
import json

# Cache the sidecar so each placement does not re-read it.
from functools import lru_cache

# GLB paths stay under the gitignored processed tree.
from pathlib import Path

# Tracked cleaning folder and the repository root.
from spacedesigner.data.common import cleaning_dir, repo_root


# Read the provenance sidecar once per process.
@lru_cache(maxsize=1)
def _provenance() -> dict[str, dict]:
    """Return item_id to source record. An empty dict if the sidecar is missing."""
    # Tracked JSON from Phase 2b. It is not part of the locked catalog schema.
    path = cleaning_dir() / "furniture_catalog_provenance.json"
    # A missing sidecar means every item stays a box.
    if not path.is_file():
        # No mesh can be resolved.
        return {}
    # The file is a single JSON object.
    loaded = json.loads(path.read_text(encoding="utf-8"))
    # Only a dict is usable. Anything else is treated as empty.
    if not isinstance(loaded, dict):
        # Refuse a malformed sidecar.
        return {}
    # Item ids map to source records.
    return loaded


# Catalog ids embedded by Stage 1 look like catalog::{item_id}::{index}.
def catalog_item_id(object_id: str) -> str | None:
    """Return the catalog id from a solver object id, or None for a kept object."""
    # The three fields are separated by a double colon.
    parts = object_id.split("::")
    # Kept objects and hand-built ids do not use this shape.
    if len(parts) != 3 or parts[0] != "catalog" or not parts[1] or not parts[2].isdigit():
        # No catalog row.
        return None
    # The middle field is the catalog item id.
    return parts[1]


# Resolve one catalog item to a cleaned GLB that is actually on disk.
def glb_for_item(item_id: str) -> tuple[str, Path] | None:
    """Return (objaverse uid, glb path) when a cleaned mesh exists, else None."""
    # Source record for this item.
    record = _provenance().get(item_id)
    # SUN-tier items have no uid.
    if not isinstance(record, dict):
        # Stay a box.
        return None
    # Uid written by the catalog builder.
    uid = record.get("objaverse_uid")
    # Missing or blank uid.
    if not isinstance(uid, str) or not uid.strip():
        # Stay a box.
        return None
    # Reject a uid that could escape the mesh folder.
    if "/" in uid or "\\" in uid or ".." in uid:
        # Stay a box.
        return None
    # Cleaned export from Phase 2b. This folder is gitignored.
    path = repo_root() / "datasets" / "processed" / "objaverse" / f"{uid}.glb"
    # A catalog row whose file was removed stays a box.
    if not path.is_file():
        # No mesh to load.
        return None
    # The viewer and the placement record both use this pair.
    return uid, path
