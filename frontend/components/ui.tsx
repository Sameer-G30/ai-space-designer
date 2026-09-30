// Presentational primitives. No logic lives here.
import type { ReactNode } from "react";

// A labelled number tile.
export function Stat({ label, value }: { label: string; value: string }) {
  // Tile.
  return (
    <div className="rounded-xl bg-accent-50 px-4 py-3">
      {/* Caption. */}
      <p className="text-xs uppercase tracking-wide text-stone-500">{label}</p>
      {/* Figure. */}
      <p className="font-display text-xl font-semibold text-stone-900">{value}</p>
    </div>
  );
}

// Small rounded status chip.
export function StatusPill({ ok, children }: { ok: boolean; children: ReactNode }) {
  // Green when ok, rose otherwise.
  const tone = ok ? "bg-sage-50 text-sage-600 border-sage-600/30" : "bg-rose-50 text-rose-800 border-rose-200";
  // Chip.
  return <span className={`inline-flex items-center rounded-full border px-3 py-1 text-sm ${tone}`}>{children}</span>;
}
