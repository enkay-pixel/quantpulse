import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TooltipProps } from "recharts";

import type { GammaProfileOut } from "../api/types";
import { formatDate, formatNumber, formatUsdCompact } from "../lib/format";

const AXIS_STYLE = { fill: "var(--text-muted)", fontSize: 11 };

interface StrikeBar {
  strike: number;
  calls: number;
  puts: number; // negative: drawn below the axis
  callOi: number;
  putOi: number;
}

function Swatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text-secondary)" }}>
      <svg width="10" height="10" aria-hidden>
        <rect width="10" height="10" rx="2" fill={color} />
      </svg>
      {label}
    </span>
  );
}

function StrikeTooltip({ active, payload }: TooltipProps<number, string>) {
  const bar = payload?.[0]?.payload as StrikeBar | undefined;
  if (!active || !bar) return null;
  return (
    <div
      className="rounded-lg border px-3 py-2 text-xs shadow-sm"
      style={{ background: "var(--surface-1)", borderColor: "var(--border)", color: "var(--text-primary)" }}
    >
      <div className="font-medium">strike ${formatNumber(bar.strike)}</div>
      <div className="mt-0.5 tabular" style={{ color: "var(--text-secondary)" }}>
        calls {formatUsdCompact(bar.calls)} per 1% · {bar.callOi.toLocaleString()} open
      </div>
      <div className="tabular" style={{ color: "var(--text-secondary)" }}>
        puts {formatUsdCompact(-bar.puts)} per 1% · {bar.putOi.toLocaleString()} open
      </div>
    </div>
  );
}

/**
 * Where one ticker's hedging exposure sits, strike by strike: calls above the axis, puts below.
 *
 * Each bar is the stock a hedger would trade per 1% move if a dealer were on the other side of
 * every live contract at that strike, summed across expiries. Exposure piled just above the price
 * is the shape that fed GameStop's gamma squeeze — if dealers had sold those calls, a rise through
 * them makes them buy, and the buying lifts the price into the next strike. Calls and puts are
 * drawn apart and never netted, because who holds which side is not public.
 */
export function GammaProfileChart({ data }: { data: GammaProfileOut }) {
  if (data.strikes.length === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        No live contracts with open interest in {data.ticker}'s latest snapshot.
      </p>
    );
  }
  const bars: StrikeBar[] = data.strikes.map((s) => ({
    strike: s.strike,
    calls: s.call_gamma_usd_1pct,
    puts: -s.put_gamma_usd_1pct,
    callOi: s.call_oi,
    putOi: s.put_oi,
  }));
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-4">
        <Swatch color="var(--series-1)" label="Calls, above the axis" />
        <Swatch color="var(--series-2)" label="Puts, below the axis" />
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          {data.spot !== null ? `price $${formatNumber(data.spot)} · ` : ""}
          {formatDate(data.snapshot_date)} · $ a hedger trades per 1% move, all expiries
        </span>
      </div>
      <div className="h-64" role="img" aria-label={`Option hedging exposure by strike for ${data.ticker}`}>
        <ResponsiveContainer>
          <BarChart data={bars} stackOffset="sign" margin={{ top: 12, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" strokeWidth={1} vertical={false} />
            <XAxis
              dataKey="strike"
              type="number"
              domain={["dataMin", "dataMax"]}
              padding={{ left: 8, right: 8 }}
              tick={AXIS_STYLE}
              stroke="var(--baseline)"
              tickLine={false}
              tickFormatter={(v: number) => `$${formatNumber(v, 0)}`}
            />
            <YAxis
              tick={AXIS_STYLE}
              stroke="var(--baseline)"
              tickLine={false}
              width={56}
              tickFormatter={(v: number) => formatUsdCompact(Math.abs(v))}
            />
            <Tooltip content={<StrikeTooltip />} cursor={{ fill: "var(--grid)", opacity: 0.4 }} />
            <ReferenceLine y={0} stroke="var(--baseline)" />
            {data.spot !== null ? (
              <ReferenceLine
                x={data.spot}
                stroke="var(--text-muted)"
                strokeDasharray="3 3"
                label={{ value: "price", position: "top", fill: "var(--text-muted)", fontSize: 11 }}
              />
            ) : null}
            <Bar
              dataKey="calls"
              name="calls"
              stackId="strike"
              fill="var(--series-1)"
              radius={[4, 4, 0, 0]}
              maxBarSize={10}
              isAnimationActive={false}
            />
            <Bar
              dataKey="puts"
              name="puts"
              stackId="strike"
              fill="var(--series-2)"
              radius={[0, 0, 4, 4]}
              maxBarSize={10}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
