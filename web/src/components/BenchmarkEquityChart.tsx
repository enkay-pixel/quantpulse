import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { EquityCurve } from "../api/types";
import { formatDate, formatNumber } from "../lib/format";
import { ChartTooltip } from "./ChartTooltip";

const AXIS_STYLE = { fill: "var(--text-muted)", fontSize: 11 };

interface Row {
  date: string;
  equity_replay: number | null;
  equity_live: number | null;
  benchmark: number | null;
  horizon: number | null;
}

function toRows(curve: EquityCurve): {
  rows: Row[];
  liveStart: string | null;
  hasReplay: boolean;
} {
  const hasPhases = curve.points.some((p) => p.phase !== null);
  const hasReplay = curve.points.some((p) => p.phase === "replay");
  let liveStart: string | null = null;
  const rows = curve.points.map((p, i) => {
    const live = p.phase === "live";
    if (live && liveStart === null) liveStart = p.date;
    // Bridge: the last replay point also feeds the live series so lines connect.
    const next = curve.points[i + 1];
    const bridges = !live && next?.phase === "live";
    return {
      date: p.date,
      equity_replay: hasPhases ? (live ? null : p.equity) : null,
      equity_live: !hasPhases || live || bridges ? p.equity : null,
      benchmark: p.benchmark_equity,
      horizon: p.horizon_equity,
    };
  });
  return { rows, liveStart, hasReplay };
}

function LegendChip({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
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

export function BenchmarkEquityChart({ curve }: { curve: EquityCurve }) {
  if (curve.points.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm" style={{ color: "var(--text-muted)" }}>
        No portfolio history yet — the daily pipeline populates this after its first runs.
      </div>
    );
  }
  const { rows, liveStart, hasReplay } = toRows(curve);
  const hasBenchmark = rows.some((r) => r.benchmark !== null);
  const hasHorizon = rows.some((r) => r.horizon !== null);

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-4">
        {hasReplay ? (
          <LegendChip color="var(--series-1)" label="Strategy — replay (in-sample)" dashed />
        ) : null}
        {liveStart || !hasReplay ? (
          <LegendChip color="var(--series-1)" label={hasReplay ? "Strategy — live" : "Strategy"} />
        ) : null}
        {hasHorizon ? (
          <LegendChip color="var(--series-3)" label="Same signal, held 21 days" />
        ) : null}
        {hasBenchmark ? <LegendChip color="var(--series-2)" label="SPY buy & hold" /> : null}
      </div>
      <div
        className="h-64"
        role="img"
        aria-label="Daily-rebalanced strategy equity versus the 21-day book and SPY buy-and-hold"
      >
        <ResponsiveContainer>
          <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
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
              content={<ChartTooltip format={(v) => formatNumber(v, 4)} />}
              cursor={{ stroke: "var(--baseline)", strokeWidth: 1 }}
            />
            {liveStart ? (
              <ReferenceLine
                x={liveStart}
                stroke="var(--baseline)"
                strokeDasharray="3 3"
                label={{ value: "live →", position: "insideTopLeft", fill: "var(--text-muted)", fontSize: 11 }}
              />
            ) : null}
            <Line
              type="monotone"
              dataKey="equity_replay"
              stroke="var(--series-1)"
              strokeWidth={2}
              strokeDasharray="4 3"
              dot={false}
              activeDot={{ r: 4, strokeWidth: 0 }}
              isAnimationActive={false}
              connectNulls={false}
            />
            <Line
              type="monotone"
              dataKey="equity_live"
              stroke="var(--series-1)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 0 }}
              isAnimationActive={false}
              connectNulls={false}
            />
            {hasHorizon ? (
              <Line
                type="monotone"
                dataKey="horizon"
                stroke="var(--series-3)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 0 }}
                isAnimationActive={false}
                connectNulls={false}
              />
            ) : null}
            {hasBenchmark ? (
              <Line
                type="monotone"
                dataKey="benchmark"
                stroke="var(--series-2)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 0 }}
                isAnimationActive={false}
                connectNulls={false}
              />
            ) : null}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
