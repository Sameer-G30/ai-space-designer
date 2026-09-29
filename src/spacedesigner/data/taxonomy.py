"""One unified furniture and room-type taxonomy for the Phase 2a CV datasets.

Every synonym below is a label that really appears in SUN RGB-D 2D boxes or in the NYU Depth V2
`names` list (see datasets/metadata/cleaning/label_vocabulary.json). Nothing is invented.
"""

# Annotations on Python 3.11.
from __future__ import annotations

# Regular expressions clean label strings.
import re

# The 26 unified furniture classes. The list index is the YOLO class id.
FURNITURE_CLASSES: tuple[str, ...] = (
    "bed",  # 0: beds, bunk beds
    "sofa",  # 1: sofas, couches, sofa beds
    "armchair",  # 2: SUN sofa_chair, lounge chairs, recliners
    "chair",  # 3: any single-seat chair
    "stool",  # 4: stools and step stools
    "bench",  # 5: benches and piano benches
    "ottoman",  # 6: ottomans and foot rests
    "table",  # 7: dining and general tables
    "desk",  # 8: desks
    "coffee_table",  # 9: coffee and centre tables
    "side_table",  # 10: end tables and side tables
    "nightstand",  # 11: night stands
    "dresser",  # 12: dressers
    "cabinet",  # 13: cabinets and wardrobes
    "shelf",  # 14: shelves and bookshelves
    "tv_stand",  # 15: TV stands
    "tv",  # 16: televisions
    "lamp",  # 17: lamps
    "mirror",  # 18: mirrors
    "wall_art",  # 19: paintings, pictures, posters
    "curtain",  # 20: curtains, blinds, window shades
    "plant",  # 21: indoor plants
    "rug",  # 22: rugs and carpets
    "pillow",  # 23: pillows and cushions
    "door",  # 24: doors
    "window",  # 25: windows
)

# Fast lookup from class name to YOLO id.
FURNITURE_INDEX: dict[str, int] = {name: index for index, name in enumerate(FURNITURE_CLASSES)}

# Normalized source label -> unified class. Keys come from SUN RGB-D boxes and NYU names.
FURNITURE_SYNONYMS: dict[str, str] = {
    # Beds.
    "bed": "bed",  # SUN + NYU
    "bunk_bed": "bed",  # SUN + NYU
    # Sofas.
    "sofa": "sofa",  # SUN + NYU
    "couch": "sofa",  # SUN
    "sofa_bed": "sofa",  # SUN
    # Armchairs.
    "sofa_chair": "armchair",  # SUN
    "lounge_chair": "armchair",  # SUN
    "recliner": "armchair",  # SUN
    "saucer_chair": "armchair",  # SUN
    # Chairs.
    "chair": "chair",  # SUN + NYU
    "plastic_chair": "chair",  # NYU
    "child_chair": "chair",  # SUN
    # Stools.
    "stool": "stool",  # SUN + NYU
    "stepstool": "stool",  # SUN
    "step_stool": "stool",  # NYU
    "piano_stool": "stool",  # SUN
    # Benches.
    "bench": "bench",  # SUN + NYU
    "piano_bench": "bench",  # SUN + NYU
    # Ottomans.
    "ottoman": "ottoman",  # SUN + NYU
    "footrest": "ottoman",  # SUN
    "foot_rest": "ottoman",  # NYU
    # Tables.
    "table": "table",  # SUN + NYU
    "dining_table": "table",  # SUN
    "bar_table": "table",  # SUN
    # Desks.
    "desk": "desk",  # SUN + NYU
    # Coffee tables.
    "coffee_table": "coffee_table",  # SUN + NYU
    "coffeetable": "coffee_table",  # SUN
    "centertable": "coffee_table",  # SUN
    # Side tables.
    "endtable": "side_table",  # SUN
    "end_table": "side_table",  # SUN
    "entable": "side_table",  # SUN typo of endtable
    "side_table": "side_table",  # SUN
    "sidetable": "side_table",  # SUN
    # Night stands.
    "night_stand": "nightstand",  # SUN + NYU
    "nightstand": "nightstand",  # SUN
    # Dressers.
    "dresser": "dresser",  # SUN + NYU
    "desser": "dresser",  # NYU typo of dresser
    # Cabinets.
    "cabinet": "cabinet",  # SUN + NYU
    "display_cabinet": "cabinet",  # SUN
    "wardrobe": "cabinet",  # NYU
    # Shelves.
    "shelf": "shelf",  # SUN
    "shelves": "shelf",  # SUN + NYU
    "bookshelf": "shelf",  # SUN + NYU
    "bookcase": "shelf",  # SUN
    "mini_shelf": "shelf",  # SUN
    # TV stands.
    "tv_stand": "tv_stand",  # SUN + NYU
    # TVs.
    "tv": "tv",  # SUN
    "television": "tv",  # SUN + NYU
    "flat_screen_tv": "tv",  # SUN
    # Lamps.
    "lamp": "lamp",  # SUN + NYU
    # Mirrors.
    "mirror": "mirror",  # SUN + NYU
    # Wall art.
    "painting": "wall_art",  # SUN
    "picture": "wall_art",  # SUN + NYU
    "poster": "wall_art",  # SUN
    "wall_painting": "wall_art",  # SUN
    "wall_frame": "wall_art",  # SUN
    "wallframe": "wall_art",  # SUN
    "pictureframe": "wall_art",  # SUN
    "walldecor": "wall_art",  # SUN
    "wall_decor": "wall_art",  # SUN
    "wall_decoration": "wall_art",  # NYU
    "photo": "wall_art",  # NYU
    # Curtains.
    "curtain": "curtain",  # SUN + NYU
    "blinds": "curtain",  # SUN + NYU
    "window_shade": "curtain",  # SUN
    "venetian_blinds": "curtain",  # SUN
    "curtain_blinds": "curtain",  # SUN
    "window_cover": "curtain",  # NYU
    # Plants.
    "plant": "plant",  # SUN + NYU
    "plant_in_pot": "plant",  # SUN
    "artificial_plant": "plant",  # SUN
    "ornamental_plant": "plant",  # NYU
    # Rugs.
    "rug": "rug",  # SUN + NYU
    "carpet": "rug",  # SUN
    # Pillows.
    "pillow": "pillow",  # SUN + NYU
    "cushion": "pillow",  # SUN
    # Doors.
    "door": "door",  # SUN + NYU
    "hingedoor": "door",  # SUN
    # Windows.
    "window": "window",  # SUN + NYU
    "glass_window": "window",  # SUN
    "window_glass": "window",  # SUN
}

# The 15 unified room types. The list index is the classifier label id.
ROOM_TYPES: tuple[str, ...] = (
    "bedroom",  # 0
    "living_room",  # 1
    "kitchen",  # 2
    "bathroom",  # 3
    "dining_room",  # 4
    "home_office",  # 5
    "kids_room",  # 6
    "basement",  # 7
    "closet",  # 8
    "corridor",  # 9
    "entrance_hall",  # 10
    "utility_room",  # 11
    "pantry",  # 12
    "home_theater",  # 13
    "balcony",  # 14
)

# Fast lookup from room type to id.
ROOM_TYPE_INDEX: dict[str, int] = {name: index for index, name in enumerate(ROOM_TYPES)}

# Official Places365 category strings (from categories_places365.txt) chosen as indoor home classes.
PLACES_INDOOR_CATEGORIES: dict[str, str] = {
    "/b/bedroom": "bedroom",  # home bedroom
    "/b/bedchamber": "bedroom",  # older name for a bedroom
    "/l/living_room": "living_room",  # home living room
    "/t/television_room": "living_room",  # TV lounge
    "/k/kitchen": "kitchen",  # home kitchen
    "/b/bathroom": "bathroom",  # home bathroom
    "/d/dining_room": "dining_room",  # home dining room
    "/h/home_office": "home_office",  # home office
    "/c/childs_room": "kids_room",  # child bedroom
    "/n/nursery": "kids_room",  # baby room
    "/p/playroom": "kids_room",  # play room
    "/b/basement": "basement",  # basement
    "/c/closet": "closet",  # closet
    "/c/corridor": "corridor",  # corridor
    "/e/entrance_hall": "entrance_hall",  # entrance hall
    "/u/utility_room": "utility_room",  # utility or laundry room
    "/p/pantry": "pantry",  # pantry
    "/h/home_theater": "home_theater",  # home theater
    "/b/balcony/interior": "balcony",  # enclosed balcony
}

# SUN RGB-D scene.txt strings mapped to room types. Anything not listed is dropped as unmapped.
SUN_SCENE_TO_ROOM: dict[str, str] = {
    "bedroom": "bedroom",  # 1084 images
    "living_room": "living_room",  # 524 images
    "kitchen": "kitchen",  # 498 images
    "bathroom": "bathroom",  # 624 images
    "dining_room": "dining_room",  # 200 images
    "dining_area": "dining_room",  # 397 images
    "dinette": "dining_room",  # 10 images
    "home_office": "home_office",  # 169 images
    "study": "home_office",  # 26 images
    "playroom": "kids_room",  # 31 images
    "basement": "basement",  # 26 images
    "corridor": "corridor",  # 373 images
    "indoor_balcony": "balcony",  # 2 images
}

# NYU sceneTypes mapped to room types (kept as metadata on NYU records only).
NYU_SCENE_TO_ROOM: dict[str, str] = {
    "bedroom": "bedroom",  # NYU bedroom
    "living_room": "living_room",  # NYU living room
    "kitchen": "kitchen",  # NYU kitchen
    "bathroom": "bathroom",  # NYU bathroom
    "dining_room": "dining_room",  # NYU dining room
    "dinette": "dining_room",  # NYU dinette
    "home_office": "home_office",  # NYU home office
    "study": "home_office",  # NYU study
    "study_room": "home_office",  # NYU study room
    "playroom": "kids_room",  # NYU playroom
    "basement": "basement",  # NYU basement
    "foyer": "entrance_hall",  # NYU foyer
    "laundry_room": "utility_room",  # NYU laundry room
    "indoor_balcony": "balcony",  # NYU indoor balcony
}

# Compiled once: anything that is not a letter or digit becomes one underscore.
_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalize_label(raw: str) -> str:
    """Lowercase, trim, and join words with single underscores."""
    # Lowercase and trim outer whitespace first.
    lowered = str(raw).strip().lower()
    # Replace runs of spaces, hyphens, and slashes with one underscore, then trim underscores.
    return _NON_WORD.sub("_", lowered).strip("_")


def map_furniture(raw: str) -> str | None:
    """Return the unified class for a raw SUN or NYU label, or None when unmapped."""
    # Normalize first so 'Night Stand' and 'night_stand' hit the same key.
    return FURNITURE_SYNONYMS.get(normalize_label(raw))


def map_sun_scene(raw: str) -> str | None:
    """Return the room type for a SUN RGB-D scene string, or None when unmapped."""
    # SUN scene strings are already lowercase with underscores; normalize anyway.
    return SUN_SCENE_TO_ROOM.get(normalize_label(raw))


def map_nyu_scene(raw: str) -> str | None:
    """Return the room type for an NYU scene type, or None when unmapped."""
    # Same normalization as SUN.
    return NYU_SCENE_TO_ROOM.get(normalize_label(raw))
