// Turn a FastAPI error into one sentence. Do not echo an unexpected body.

// A validation item from FastAPI.
type ValidationItem = {
  // Field path, when present.
  loc?: unknown;
  // Message, when present.
  msg?: unknown;
};

// Join a FastAPI loc array, dropping the body prefix.
function formatLoc(loc: unknown): string {
  // Only arrays are location paths.
  if (!Array.isArray(loc)) {
    // No path.
    return "";
  }
  // Drop the body wrapper and stringify the rest.
  return loc
    // Skip the generic body segment.
    .filter((part) => part !== "body")
    // Keep numbers and strings.
    .map((part) => String(part))
    // Join with dots.
    .join(".");
}

// Read one validation item.
function formatItem(item: unknown): string {
  // Non-objects have no message.
  if (typeof item !== "object" || item === null) {
    // Generic phrase.
    return "invalid request";
  }
  // Narrow to the fields we read.
  const record = item as ValidationItem;
  // Prefer the FastAPI message.
  const msg = typeof record.msg === "string" && record.msg.trim() !== "" ? record.msg : "invalid value";
  // Field path.
  const loc = formatLoc(record.loc);
  // Prefix the message when a path exists.
  return loc === "" ? msg : `${loc}: ${msg}`;
}

// Public formatter used by the proxy routes.
export function formatApiDetail(body: unknown, statusCode: number): string {
  // Only an object can carry FastAPI's detail field.
  if (typeof body === "object" && body !== null && "detail" in body) {
    // The detail value.
    const detail = (body as { detail: unknown }).detail;
    // HTTPException uses a string.
    if (typeof detail === "string" && detail.trim() !== "") {
      // Return it unchanged.
      return detail;
    }
    // Request validation uses a list.
    if (Array.isArray(detail)) {
      // One phrase per item.
      const joined = detail.map((item) => formatItem(item)).join("; ");
      // Use the phrases when they exist.
      if (joined.trim() !== "") {
        // Return the summary.
        return joined;
      }
    }
  }
  // Hide any other body so a traceback or a URL cannot land on the page.
  return `HTTP ${statusCode}`;
}
