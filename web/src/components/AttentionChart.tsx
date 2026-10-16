import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TooltipProps } from "recharts";

import type { AttentionDay, AttentionHistoryOut } from "../api/types";
import { formatDate, formatNumber } from "../lib/format";

const AXIS_STYLE = { fill: "var(--text-muted)", fontSize: 11 };

function LegendLine({ color, dashed, label }: { color: string; dashed?: boolean; label: string }) {
  return (
    <span className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text-secondary)" }}>
      <svg width="18" height="6" aria-hidden>
        <line
          x1="0"
          y1="3"
          x2="18"
          y2="3"
          stroke={color}
          strokeWidth="2"
          strokeDasharray={dashed ? "4 3" : undefined}
        />
      </svg>
      {label}
    </span>
  );
}

function DayTooltip({ active, payload }: TooltipProps<number, string>) {
  const day = payload?.[0]?.payload as AttentionDay | undefined;
  if (!active || !day) return null;
  const ratio = day.baseline_90d ? day.views_7d / day.baseline_90d : null;
  return (
    <div
      className="rounded-lg border px-3 py-2 text-xs shadow-sm"
      style={{ background: "var(--surface-1)", borderColor: "var(--border)", color: "var(--text-primary)" }}
    >
      <div className="font-medium">{formatDate(day.date)}</div>
      <div className="mt-0.5 tabular" style={{ color: "var(--text-secondary)" }}>
        past week {Math.round(day.views_7d).toLocaleString()} a day
      </div>
      <div className="tabular" style={{ color: "var(--text-secondary)" }}>
        usual {day.baseline_90d === null ? "—" : Math.round(day.baseline_90d).toLocaleString()}
        {ratio === null ? "" : ` · ${formatNumber(ratio, 1)}× usual`}
      </div>
    </div>
  );
}

/** A year of one stock's attention: the past week's mean daily views against its usual level. */
export function AttentionChart({ data }: { data: AttentionHistoryOut }) {
  if (data.days.length === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        No page-view history for {data.ticker} yet.
      </p>
    );
  }
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-4">
        <LegendLine color="var(--series-1)" label="Views a day, past week" />
        <LegendLine color="var(--text-muted)" dashed label="Usual (90-day median before the week)" />
        {data.article ? (
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            Wikipedia: {data.article}
          </span>
        ) : null}
      </div>
      <div className="h-64" role="img" aria-label={`Wikipedia attention over the past year for ${data.ticker}`}>
        <ResponsiveContainer>
          <LineChart data={data.days} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" strokeWidth={1} vertical={false} />
            <XAxis
              dataKey="date"
              tick={AXIS_STYLE}
              stroke="var(--baseline)"
              tickLine={false}
              minTickGap={48}
              tickFormatter={(d: string) => formatDate(d).replace(/,? \d{4}$/, "")}
            />
            <YAxis
              tick={AXIS_STYLE}
              stroke="var(--baseline)"
              tickLine={false}
              width={52}
              tickFormatter={(v: number) => Math.round(v).toLocaleString()}
            />
            <Tooltip content={<DayTooltip />} cursor={{ stroke: "var(--baseline)", strokeWidth: 1 }} />
            <Line
              type="monotone"
              dataKey="baseline_90d"
              name="usual"
              stroke="var(--text-muted)"
              strokeWidth={2}
              strokeDasharray="4 3"
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="views_7d"
              name="past week"
              stroke="var(--series-1)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
