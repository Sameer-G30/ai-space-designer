// Small formatters for INR and milliseconds.

// Format a synthetic rupee amount for the budget, the chart, and the bill of materials.
export function formatInr(value: number): string {
  // Use the Indian grouping. The currency symbol marks the unit.
  return new Intl.NumberFormat("en-IN", {
    // Currency formatting.
    style: "currency",
    // Indian rupees.
    currency: "INR",
    // Keep paise when the catalog has them, and drop trailing zeros beyond two digits.
    maximumFractionDigits: 2,
  }).format(value);
}

// Format a rupee amount for a short axis tick, without the currency symbol.
export function formatInrTick(value: number): string {
  // Round to a whole rupee so the axis stays short.
  return new Intl.NumberFormat("en-IN", {
    // No currency symbol.
    maximumFractionDigits: 0,
  }).format(value);
}

// Format a millisecond duration.
export function formatMs(value: number): string {
  // One decimal is enough for a sweep that is usually tens of milliseconds.
  return `${value.toFixed(1)} ms`;
}
