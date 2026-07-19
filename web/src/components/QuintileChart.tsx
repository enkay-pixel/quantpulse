import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Quintiles } from "../api/types";
import { formatNumber } from "../lib/format";

const AXIS_STYLE = { fill: "var(--text-muted)", fontSize: 11 };
// Ordinal blue ramp: quintile 1 (strongest signal) darkest.
const RAMP = ["var(--seq-650)", "var(--seq-550)", "var(--seq-450)", "var(--seq-350)", "var(--seq-250)"];

export function QuintileChart({ quintiles }: { quintiles: Quintiles }) {
  const [window, setWindow] = useState<"overall" | "recent">("overall");
  const data = quintiles[window].map((q) => ({
    quintile: `Q${q.signal_quintile}`,
    bps: q.avg_next_day_return * 10_000,
    n_days: q.n_days,
  }));

  if (quintiles.overall.length === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        Appears after the first dbt transform run.
      </p>
    );
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
          Avg next-day return per signal quintile (Q1 = strongest signal). A useful model
          slopes downward left to right.
        </p>
        <div className="flex gap-1" role="group" aria-label="History window">
          {(["overall", "recent"] as const).map((w) => (
            <button
              key={w}
              onClick={() => setWindow(w)}
              aria-pressed={window === w}
              className="rounded px-2 py-0.5 text-xs font-medium"
              style={{
                background: window === w ? "var(--grid)" : "transparent",
                color: window === w ? "var(--text-primary)" : "var(--text-muted)",
              }}
            >
              {w === "overall" ? "All history" : "Last ~30d"}
            </button>
          ))}
        </div>
      </div>
      <div className="h-56" role="img" aria-label="Average next-day return per signal quintile">
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" strokeWidth={1} vertical={false} />
            <XAxis dataKey="quintile" tick={AXIS_STYLE} stroke="var(--baseline)" tickLine={false} />
            <YAxis
              tick={AXIS_STYLE}
              stroke="var(--baseline)"
              tickLine={false}
              width={44}
              tickFormatter={(v: number) => `${formatNumber(v, 0)}bp`}
            />
            <Tooltip
              cursor={{ fill: "var(--grid)", opacity: 0.4 }}
              contentStyle={{
                background: "var(--surface-1)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                fontSize: 12,
                color: "var(--text-primary)",
              }}
              formatter={(value) => [`${formatNumber(Number(value), 1)} bps`, "avg next-day"]}
            />
            <ReferenceLine y={0} stroke="var(--baseline)" />
            <Bar dataKey="bps" radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {data.map((entry, i) => (
                <Cell key={entry.quintile} fill={RAMP[i] ?? RAMP[RAMP.length - 1]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
