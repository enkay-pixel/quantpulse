import type { Exchange } from "../api/types";

/**
 * Market switcher: a menu of the markets that have data. Only those are offered — a switch to
 * an empty market produces a dashboard full of dashes that reads as a bug.
 *
 * A native menu rather than a row of buttons: at seven markets the buttons no longer fit a
 * phone's width, and each option names its market beside the code, since XSWX or XAMS alone
 * tells a reader nothing.
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
  const current = available.find((e) => e.code === selected);

  return (
    <select
      aria-label="Market"
      value={selected}
      onChange={(event) => onSelect(event.target.value)}
      title={
        current
          ? `${current.code} · ${current.currency} · benchmark ${current.benchmark}`
          : undefined
      }
      className="max-w-[12rem] rounded-md px-2 py-1 text-xs font-medium"
      style={{
        background: "var(--surface-1)",
        color: "var(--text-primary)",
        border: "1px solid var(--border)",
      }}
    >
      {available.map((ex) => (
        <option key={ex.code} value={ex.code}>
          {ex.display_name ? `${ex.display_name} (${ex.code})` : ex.code}
        </option>
      ))}
    </select>
  );
}
