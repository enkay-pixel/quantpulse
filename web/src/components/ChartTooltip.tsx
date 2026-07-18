import type { TooltipProps } from "recharts";

import { formatDate } from "../lib/format";

interface Entry {
  name?: string;
  value?: number | string;
  formatted?: string;
}

export function ChartTooltip({
  active,
  label,
  payload,
  format,
}: TooltipProps<number, string> & { format?: (v: number) => string }) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div
      className="rounded-lg border px-3 py-2 text-xs shadow-sm"
      style={{ background: "var(--surface-1)", borderColor: "var(--border)", color: "var(--text-primary)" }}
    >
      <div className="font-medium">{formatDate(String(label))}</div>
      {payload.map((entry: Entry, i: number) => (
        <div key={i} className="mt-0.5 tabular" style={{ color: "var(--text-secondary)" }}>
          {format && typeof entry.value === "number" ? format(entry.value) : String(entry.value)}
        </div>
      ))}
    </div>
  );
}
