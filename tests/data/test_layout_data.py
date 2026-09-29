"""Phase 2b validation tests: catalog, priors, synthetic records, RAG chunks, Objaverse mapping."""

# Path objects for the tracked files.
# Numeric arrays for the geometry tests.
import numpy as np

# Skips tests whose input files are absent.
import pytest

# Shared readers.
from spacedesigner.data.common import cleaning_dir, processed_dir, raw_dir, read_json, read_jsonl

# Layout rules under test.
from spacedesigner.data.layout_priors import (
    MIN_CLASS_SAMPLES,
    MIN_ROOM_SAMPLES,
    clean_scene_boxes,
    distance_to_polygon_edges,
    point_in_polygon,
)

# Objaverse rules under test.
from spacedesigner.data.objaverse_clean import LVIS_TO_TAXONOMY, choose_up_axis

# Chunking helpers under test.
from spacedesigner.data.rag_chunks import MAX_CHARS, find_running_lines, pick_topic, strip_page

# Generator under test.
from spacedesigner.data.synthetic import generate

# Taxonomy the catalog and assets must use.
from spacedesigner.data.taxonomy import FURNITURE_CLASSES, ROOM_TYPES

# Locked schemas.
from spacedesigner.schemas.catalog import CatalogItem
from spacedesigner.schemas.requirement import Requirement
from spacedesigner.schemas.scene import SceneGraph

# Tracked catalog JSONL.
CATALOG = cleaning_dir() / "furniture_catalog.jsonl"

# Tracked priors JSON.
PRIORS = cleaning_dir() / "layout_priors.json"

# Ignored chunk file.
CHUNKS = processed_dir("rag") / "chunks.jsonl"

# Ignored Objaverse manifest.
MESHES = processed_dir("objaverse") / "manifest.jsonl"


# Catalog rows validate against the locked schema.
def test_catalog_rows_validate_with_positive_dims_and_prices() -> None:
    """Every catalog row parses, has positive size and price, and no embedding."""
    # Read the rows.
    rows = read_jsonl(CATALOG)
    # About 300 to 500 items.
    assert 300 <= len(rows) <= 500
    # Ids are unique.
    assert len({r["item_id"] for r in rows}) == len(rows)
    # Check each row.
    for row in rows:
        # Locked schema, extra keys forbidden.
        item = CatalogItem.model_validate(row)
        # Category is one of the 26 taxonomy classes.
        assert item.category in FURNITURE_CLASSES
        # Positive metres on every axis.
        assert min(item.dims.length, item.dims.width, item.dims.height) > 0
        # Non-negative INR, and positive for every synthetic price here.
        assert item.price > 0
        # Embedding is left null in Phase 2b.
        assert item.embedding is None
        # Style tags exist.
        assert item.style_tags


# Provenance names a source for every item.
def test_catalog_provenance_covers_every_item() -> None:
    """Each item has a named source in the provenance sidecar."""
    # Item ids.
    ids = {r["item_id"] for r in read_jsonl(CATALOG)}
    # Sidecar.
    provenance = read_json(cleaning_dir() / "furniture_catalog_provenance.json")
    # Same keys.
    assert set(provenance) == ids
    # Each entry names a source.
    assert all(p["source"] for p in provenance.values())


# Every published prior states its sample count and meets its minimum.
def test_every_published_prior_meets_its_minimum_sample_count() -> None:
    """No prior is published below its minimum n."""
    # Load the priors.
    priors = read_json(PRIORS)
    # SUN sections.
    sun = priors["sun_rgbd"]
    # Object sizes and wall distances need MIN_CLASS_SAMPLES.
    for section in ("object_size", "wall_distance"):
        # Each class.
        for name, prior in sun[section].items():
            # Class is in the taxonomy.
            assert name in FURNITURE_CLASSES
            # Minimum recorded and met.
            assert prior["min_n"] == MIN_CLASS_SAMPLES and prior["n"] >= prior["min_n"], name
    # Co-occurrence needs MIN_ROOM_SAMPLES rooms.
    for room_type, prior in sun["cooccurrence"].items():
        # Room type is in the taxonomy.
        assert room_type in ROOM_TYPES
        # Minimum recorded and met.
        assert prior["min_n"] == MIN_ROOM_SAMPLES and prior["n_rooms"] >= prior["min_n"]
    # Room size and shape priors need MIN_ROOM_SAMPLES rooms.
    for source, section in (("structured3d", "room_size"), ("cubicasa5k", "room_shape")):
        # Each room type.
        for room_type, prior in priors[source][section].items():
            # Room type is in the taxonomy.
            assert room_type in ROOM_TYPES
            # Minimum recorded and met.
            assert prior["min_n"] == MIN_ROOM_SAMPLES and prior["n"] >= prior["min_n"]


# Anything not published is listed as omitted with its count.
def test_omitted_priors_are_named_with_counts_below_the_minimum() -> None:
    """Each omitted prior has a count below its minimum and a reason naming the source."""
    # Load the priors.
    priors = read_json(PRIORS)
    # Every omission list.
    for source in ("sun_rgbd", "structured3d", "cubicasa5k"):
        # Each entry.
        for omitted in priors[source]["omitted"]:
            # Below the minimum.
            assert omitted["n"] < omitted["min_n"]
            # A reason is written.
            assert omitted["missing"]


# Generated records validate against the locked Pydantic schemas.
def test_synthetic_records_validate_against_locked_schemas() -> None:
    """A fresh 100-record run validates, links scene to requirement, and keeps ids unique."""
    # Generate with a fixed seed.
    scenes, requirements = generate(100, seed=7)
    # Same length.
    assert len(scenes) == len(requirements) == 100
    # Unique scene ids.
    assert len({s["scene_id"] for s in scenes}) == 100
    # Check each pair.
    for scene, requirement in zip(scenes, requirements):
        # Locked scene schema.
        graph = SceneGraph.model_validate(scene)
        # Locked requirement schema.
        model = Requirement.model_validate(requirement)
        # The requirement points at its own scene.
        assert model.scene_id == graph.scene_id
        # Every must-keep id exists in the scene.
        assert set(model.must_keep_object_ids) <= {o.id for o in graph.objects}
        # Must-keep ids match the object flags.
        assert set(model.must_keep_object_ids) == {o.id for o in graph.objects if o.must_keep}


# The generated set on disk also validates.
def test_generated_synthetic_set_on_disk_validates() -> None:
    """Every record in datasets/raw/synthetic validates. Skipped when the set is absent."""
    # Location of the ignored set.
    folder = raw_dir("synthetic")
    # The set is gitignored, so it may not exist.
    if not (folder / "scenes.jsonl").exists():
        # Nothing to check.
        pytest.skip("datasets/raw/synthetic is not generated")
    # Every scene.
    for row in read_jsonl(folder / "scenes.jsonl"):
        # Locked schema.
        SceneGraph.model_validate(row)
    # Every requirement.
    for row in read_jsonl(folder / "requirements.jsonl"):
        # Locked schema.
        Requirement.model_validate(row)


# Geometry helpers behave on a unit square.
def test_point_in_polygon_and_wall_distance() -> None:
    """Inside and outside points are told apart, and the wall distance is correct."""
    # A 4 m by 3 m room.
    room = np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 3.0], [0.0, 3.0]])
    # Inside.
    assert point_in_polygon(np.array([1.0, 1.0]), room)
    # Outside.
    assert not point_in_polygon(np.array([5.0, 1.0]), room)
    # One metre from the nearest wall.
    assert distance_to_polygon_edges(np.array([1.0, 1.5]), room) == pytest.approx(1.0)


# One SUN-style object entry for the filter tests.
def sun_object(name: str, x: float, z: float, size: float = 0.6, top: float = 0.5) -> dict:
    """Build a square SUN object with a footprint centred at (x, z)."""
    # Half edge.
    h = size / 2
    # Polygon in the SUN annotation shape.
    return {
        "name": name,
        "polygon": [
            {
                "X": [x - h, x + h, x + h, x - h],
                "Z": [z - h, z - h, z + h, z + h],
                "Ymin": top,
                "Ymax": top + 0.8,
            }
        ],
    }


# The ATISS-style object filters report their reasons.
def test_scene_box_filters_report_drop_reasons() -> None:
    """Unmapped, null, outside-floor, tiny, and overlapping objects are dropped with reasons."""
    # A 4 m square floor.
    floor = np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]])
    # One of each case plus two good chairs.
    objects = [
        sun_object("chair", 1.0, 1.0),
        sun_object("chair", 3.0, 3.0),
        sun_object("paper", 2.0, 2.0),
        None,
        sun_object("table", 9.0, 9.0),
        sun_object("lamp", 2.0, 1.0, size=0.01),
        sun_object("chair", 1.05, 1.0),
    ]
    # Filter.
    kept, reasons = clean_scene_boxes(objects, floor)
    # Two chairs survive.
    assert [b["category"] for b in kept] == ["chair", "chair"]
    # Each drop reason is counted once.
    assert reasons == {
        "unmapped_class": 1,
        "null_entry": 1,
        "outside_floor": 1,
        "implausible_size": 1,
        "heavy_overlap": 1,
    }


# Objaverse categories map only to real taxonomy classes.
def test_objaverse_mapping_targets_are_taxonomy_classes() -> None:
    """Every mapped LVIS category lands on one of the 26 classes."""
    # Each mapping value.
    for target in LVIS_TO_TAXONOMY.values():
        # None means dropped as unmapped; otherwise it must be a taxonomy class.
        assert target is None or target in FURNITURE_CLASSES


# The up-axis rule prefers the orientation that matches the class proportions.
def test_up_axis_choice_uses_class_ratio() -> None:
    """A tall-in-Z chair is rotated, a normal glTF chair is not."""
    # Chair-like ratio: height a bit above the floor edge.
    assert choose_up_axis(np.array([0.5, 0.9, 0.5]), 1.4) == "y"
    # Same chair modelled with Z up.
    assert choose_up_axis(np.array([0.5, 0.5, 0.9]), 1.4) == "z"
    # No prior keeps the glTF default.
    assert choose_up_axis(np.array([0.5, 0.5, 0.9]), None) == "y"


# Header and footer stripping.
def test_strip_page_removes_running_lines_and_page_numbers() -> None:
    """Lines that repeat across pages and bare page numbers are removed."""
    # Three pages sharing a header and a numbered footer.
    pages = [[f"Running Title {n}", "Body text here.", str(n)] for n in range(1, 30)]
    # Repeated lines.
    running = find_running_lines(pages)
    # The header is found regardless of the number in it.
    assert "running title #" in running
    # Strip one page.
    kept, removed = strip_page(pages[0], running)
    # Every line repeats on all pages here, so nothing is kept.
    assert kept == []
    # Header and page number were counted as removed.
    assert removed == 3


# Topic tags.
def test_pick_topic_names_a_topic() -> None:
    """Known keywords give a topic and anything else is general."""
    # A door sentence.
    assert pick_topic("Door hinge side clearance") == "door"
    # No keyword.
    assert pick_topic("Purpose of this document") == "general"


# The chunk file on disk follows the row contract.
def test_rag_chunks_have_metadata_and_bounded_size() -> None:
    """Each chunk has source, page, topic metadata and no embedding. Skipped when absent."""
    # The ignored file may not exist.
    if not CHUNKS.exists():
        # Nothing to check.
        pytest.skip("datasets/processed/rag is not generated")
    # Read the rows.
    rows = read_jsonl(CHUNKS)
    # Some chunks exist.
    assert rows
    # Ids are unique.
    assert len({r["chunk_id"] for r in rows}) == len(rows)
    # Check each row.
    for row in rows:
        # Metadata carries source, page, and topic keys.
        assert {"source", "page", "topic"} <= set(row["metadata"])
        # Source column matches the metadata.
        assert row["source"] == row["metadata"]["source"]
        # No embedding key is stored in Phase 2b.
        assert "embedding" not in row
        # Chunks are not empty. A single long sentence may exceed the soft limit.
        assert row["text"].strip()
        # Soft limit with head-room for one long sentence.
        assert len(row["text"]) <= MAX_CHARS * 3


# Cleaned Objaverse meshes use taxonomy classes.
def test_cleaned_objaverse_manifest_uses_taxonomy_classes() -> None:
    """Every cleaned mesh has a taxonomy class and positive metre dimensions."""
    # The ignored manifest may not exist.
    if not MESHES.exists():
        # Nothing to check.
        pytest.skip("datasets/processed/objaverse is not generated")
    # Check each row.
    for row in read_jsonl(MESHES):
        # Class in the taxonomy.
        assert row["taxonomy_class"] in FURNITURE_CLASSES
        # Positive size.
        assert min(row["dims_m"].values()) > 0
