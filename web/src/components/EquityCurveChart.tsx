import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { EquityCurve } from "../api/types";
import { formatDate, formatNumber } from "../lib/format";
import { ChartTooltip } from "./ChartTooltip";

const AXIS_STYLE = { fill: "var(--text-muted)", fontSize: 11 };

export function EquityCurveChart({ curve }: { curve: EquityCurve }) {
  if (curve.points.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm" style={{ color: "var(--text-muted)" }}>
        No portfolio history yet — the daily pipeline populates this after its first runs.
      </div>
    );
  }
  return (
    <div className="h-64" role="img" aria-label="Paper portfolio equity curve">
      <ResponsiveContainer>
        <LineChart data={curve.points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" strokeWidth={1} vertical={false} />
          <XAxis
            dataKey="date"
            tick={AXIS_STYLE}
            tickFormatter={(d: string) => formatDate(d)}
            stroke="var(--baseline)"
            tickLine={false}
            minTickGap={48}
          />
          <YAxis
            tick={AXIS_STYLE}
            stroke="var(--baseline)"
            tickLine={false}
            width={48}
            domain={["auto", "auto"]}
            tickFormatter={(v: number) => formatNumber(v, 2)}
          />
          <Tooltip
            content={<ChartTooltip format={(v) => `equity ${formatNumber(v, 4)}`} />}
            cursor={{ stroke: "var(--baseline)", strokeWidth: 1 }}
          />
          <Line
            type="monotone"
            dataKey="equity"
            stroke="var(--series-1)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
