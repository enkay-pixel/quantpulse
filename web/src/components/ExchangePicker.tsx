import type { Exchange } from "../api/types";

/**
 * Market switcher. Only markets with data are selectable — offering a switch to an
 * empty market produces a dashboard full of dashes that reads as a bug.
 */
export function ExchangePicker({
  exchanges,
  selected,
  onSelect,
}: {
  exchanges: Exchange[];
  selected: string;
  onSelect: (code: string) => void;
}) {
  const available = exchanges.filter((e) => e.configured);
  if (available.length < 2) return null; // nothing to switch between

  return (
    <div className="flex items-center gap-1" role="group" aria-label="Market">
      {available.map((ex) => {
        const active = ex.code === selected;
        return (
          <button
            key={ex.code}
            type="button"
            onClick={() => onSelect(ex.code)}
            aria-pressed={active}
            title={`${ex.code} · ${ex.currency} · benchmark ${ex.benchmark}`}
            className="rounded-md px-2.5 py-1 text-xs font-medium transition-colors"
            style={{
              background: active ? "var(--surface-1)" : "transparent",
              color: active ? "var(--text-primary)" : "var(--text-muted)",
              border: `1px solid ${active ? "var(--border)" : "transparent"}`,
            }}
          >
            {ex.code}
          </button>
        );
      })}
    </div>
  );
}
