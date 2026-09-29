// Closed lists the Phase 5 forms are allowed to send. They mirror the locked taxonomy.

// The 15 room types, in taxonomy order.
export const ROOM_TYPES = [
  // Bedroom.
  "bedroom",
  // Living room.
  "living_room",
  // Kitchen.
  "kitchen",
  // Bathroom.
  "bathroom",
  // Dining room.
  "dining_room",
  // Home office.
  "home_office",
  // Kids room.
  "kids_room",
  // Basement.
  "basement",
  // Closet.
  "closet",
  // Corridor.
  "corridor",
  // Entrance hall.
  "entrance_hall",
  // Utility room.
  "utility_room",
  // Pantry.
  "pantry",
  // Home theater.
  "home_theater",
  // Balcony.
  "balcony",
] as const;

// All 26 furniture classes. Kept objects may use any of them.
export const FURNITURE_CLASSES = [
  // Bed.
  "bed",
  // Sofa.
  "sofa",
  // Armchair.
  "armchair",
  // Chair.
  "chair",
  // Stool.
  "stool",
  // Bench.
  "bench",
  // Ottoman.
  "ottoman",
  // Table.
  "table",
  // Desk.
  "desk",
  // Coffee table.
  "coffee_table",
  // Side table.
  "side_table",
  // Nightstand.
  "nightstand",
  // Dresser.
  "dresser",
  // Cabinet.
  "cabinet",
  // Shelf.
  "shelf",
  // TV stand.
  "tv_stand",
  // Television.
  "tv",
  // Lamp.
  "lamp",
  // Mirror.
  "mirror",
  // Wall art.
  "wall_art",
  // Curtain.
  "curtain",
  // Plant.
  "plant",
  // Rug. No catalog rows.
  "rug",
  // Pillow.
  "pillow",
  // Door. A scene opening, not a catalog item.
  "door",
  // Window. A scene opening, not a catalog item.
  "window",
] as const;

// Catalog classes the requirement may require. Rug, door, and window have no rows.
export const MUST_HAVE_CLASSES = [
  // Bed.
  "bed",
  // Sofa.
  "sofa",
  // Armchair.
  "armchair",
  // Chair.
  "chair",
  // Stool.
  "stool",
  // Bench.
  "bench",
  // Ottoman.
  "ottoman",
  // Table.
  "table",
  // Desk.
  "desk",
  // Coffee table.
  "coffee_table",
  // Side table.
  "side_table",
  // Nightstand.
  "nightstand",
  // Dresser.
  "dresser",
  // Cabinet.
  "cabinet",
  // Shelf.
  "shelf",
  // TV stand.
  "tv_stand",
  // Television.
  "tv",
  // Lamp.
  "lamp",
  // Mirror.
  "mirror",
  // Wall art.
  "wall_art",
  // Curtain.
  "curtain",
  // Plant.
  "plant",
  // Pillow.
  "pillow",
] as const;

// Style words already used by the synthetic generator.
export const STYLES = [
  // Modern.
  "modern",
  // Scandinavian.
  "scandinavian",
  // Minimalist.
  "minimalist",
  // Industrial.
  "industrial",
  // Traditional.
  "traditional",
  // Rustic.
  "rustic",
  // Mid-century.
  "mid_century",
  // Bohemian.
  "bohemian",
  // Contemporary.
  "contemporary",
] as const;

// The four walls of the rectangular floor frame.
export const WALLS = [
  // Top edge in the plan. Runs along room length.
  "north",
  // Bottom edge in the plan. Runs along room length.
  "south",
  // Right edge in the plan. Runs along room width.
  "east",
  // Left edge in the plan. Runs along room width.
  "west",
] as const;

// Opening kinds the form can place on a wall.
export const OPENING_TYPES = [
  // Door opening.
  "door",
  // Window opening.
  "window",
] as const;

// Confidence labels accepted by the locked schema.
export const CONFIDENCE_LEVELS = [
  // Tape or typed measurement.
  "high",
  // Neither tape nor depth-only.
  "medium",
  // Depth-only. The solver insets every wall by 0.10 m.
  "low",
] as const;

// The six objective weights. The form must send every one.
export const WEIGHT_NAMES = [
  // Layout term weight.
  "layout",
  // Circulation term weight.
  "circulation",
  // Ergonomics term weight.
  "ergonomics",
  // Budget term weight.
  "budget",
  // Aesthetics term weight.
  "aesthetics",
  // Sustainability term weight.
  "sustainability",
] as const;

// Visible names for the six weights.
export const WEIGHT_LABELS: Record<(typeof WEIGHT_NAMES)[number], string> = {
  // Layout label.
  layout: "Layout",
  // Circulation label.
  circulation: "Circulation",
  // Ergonomics label.
  ergonomics: "Ergonomics",
  // Budget label.
  budget: "Budget",
  // Aesthetics label.
  aesthetics: "Aesthetics",
  // Sustainability label.
  sustainability: "Sustainability",
};

// Scene graphs created by this form start at version 1.
export const SCENE_VERSION = 1;

// Low-confidence inset, matching optimizer LOW_CONFIDENCE_MARGIN_M.
export const LOW_CONFIDENCE_INSET_M = 0.1;

// Palette shared by the plan and the box view. Same order as the Python plan.
export const PLAN_PALETTE = [
  // First object.
  "#8ecae6",
  // Second object.
  "#ffb703",
  // Third object.
  "#90be6d",
  // Fourth object.
  "#f28482",
  // Fifth object.
  "#bdb2ff",
  // Sixth object, then the palette repeats.
  "#84a59d",
] as const;

// Tailwind classes for text inputs and selects.
export const inputClassName =
  // Full-width field with a visible border.
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-2 py-2 text-sm text-zinc-900";

// Tailwind classes for field labels.
export const labelClassName = "block text-sm font-medium text-zinc-800";

// Prices are synthetic. The catalog has no retailer prices and no ratings.
export const PRICE_NOTE =
  // Shown beside the budget field and the bill of materials.
  "Catalog prices are synthetic INR. They are not retailer prices, and the catalog has no ratings.";

// Style tags and materials are project labels, not 3D-FUTURE attributes.
export const STYLE_NOTE =
  // Shown beside the style select.
  "These style words match the synthetic generator. Catalog style tags and materials are project labels.";

// Sustainability is a lookup. Five catalog materials are missing and score 0.5.
export const SUSTAINABILITY_NOTE =
  // Shown when the selected design prints its sustainability term.
  "Sustainability is a material lookup, not a certification. leather, rattan, linen_fabric, polyester_fabric, and cotton_fabric are missing from the lookup and use 0.5.";

// This phase does not parse a sentence into a requirement.
export const PARSER_NOTE =
  // Shown instead of a free-text box.
  "This form sends a structured requirement. It does not parse a sentence.";

// Rug, door, and window are absent from the catalog.
export const ABSENT_NOTE =
  // Shown above the must-have checkboxes.
  "Rug, door, and window are not catalog choices. Doors and windows are openings on the walls.";

// How opening position is measured on each wall.
export const POSITION_NOTE =
  // Shown above the opening rows.
  "Position is metres from the west end on the north and south walls, and from the south end on the east and west walls.";

// A narrow door is a readable infeasible result.
export const DOOR_NOTE =
  // Shown above the opening rows.
  "A door narrower than 0.815 m is returned as infeasible and is not drawn.";

// Floor frame used by the plan.
export const PLAN_NOTE =
  // Shown under the plan.
  "Top view. Length runs west to east, width runs south to north, and north is up. Position is the footprint centre. A rotation of 90 or 270 swaps length and width.";

// Floor frame used by the box view.
export const BOX_NOTE =
  // Shown under the canvas.
  "Floor x is world X, floor y is world Z, and height is world Y. These are boxes at the solver coordinates, not GLB models.";

// Replace underscores so a taxonomy token is easier to read.
export function readableToken(value: string): string {
  // Split the token on underscores.
  return value.replaceAll("_", " ");
}

// Pick a stable plan color from the object index.
export function planColor(index: number): string {
  // Wrap around the palette.
  const color = PLAN_PALETTE[index % PLAN_PALETTE.length];
  // The modulo always hits an entry. The fallback keeps the type a string.
  return color ?? PLAN_PALETTE[0];
}

// Build the requirement id from the scene id. There is no separate parser id.
export function requirementIdFor(sceneId: string): string {
  // Prefix the trimmed scene id so the requirement id is non-empty when the scene id is.
  return `requirement-${sceneId.trim()}`;
}
