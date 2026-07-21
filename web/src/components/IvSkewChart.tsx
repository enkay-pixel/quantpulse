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

import type { OptionChain } from "../api/types";
import { formatNumber, formatPercent } from "../lib/format";

const AXIS_STYLE = { fill: "var(--text-muted)", fontSize: 11 };

function LegendChip({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text-secondary)" }}>
      <svg width="18" height="6" aria-hidden>
        <line x1="0" y1="3" x2="18" y2="3" stroke={color} strokeWidth="2" />
      </svg>
      {label}
    </span>
  );
}

// Implied volatility across strikes = the smile/skew. Calls and puts are two series
// on one shared scale (both are volatility), so a single y-axis is correct here.
export function IvSkewChart({ chain }: { chain: OptionChain }) {
  if (chain.contracts.length === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        No option snapshot yet — the daily pipeline captures chains going forward.
      </p>
    );
  }

  const byStrike = new Map<number, { strike: number; call?: number; put?: number }>();
  for (const c of chain.contracts) {
    const row = byStrike.get(c.strike) ?? { strike: c.strike };
    if (c.option_type === "call") row.call = c.implied_volatility;
    else row.put = c.implied_volatility;
    byStrike.set(c.strike, row);
  }
  const data = [...byStrike.values()].sort((a, b) => a.strike - b.strike);

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-4">
        <LegendChip color="var(--series-1)" label="Call IV" />
        <LegendChip color="var(--series-2)" label="Put IV" />
        {chain.underlying_close !== null ? (
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            spot ${formatNumber(chain.underlying_close)} · expiry {chain.expiry}
          </span>
        ) : null}
      </div>
      <div className="h-56" role="img" aria-label={`Implied volatility by strike for ${chain.ticker}`}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" strokeWidth={1} vertical={false} />
            <XAxis
              dataKey="strike"
              type="number"
              domain={["dataMin", "dataMax"]}
              tick={AXIS_STYLE}
              stroke="var(--baseline)"
              tickLine={false}
              tickFormatter={(v: number) => `$${formatNumber(v, 0)}`}
            />
            <YAxis
              tick={AXIS_STYLE}
              stroke="var(--baseline)"
              tickLine={false}
              width={48}
              tickFormatter={(v: number) => formatPercent(v, 0)}
            />
            <Tooltip
              cursor={{ stroke: "var(--baseline)", strokeWidth: 1 }}
              contentStyle={{
                background: "var(--surface-1)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                fontSize: 12,
                color: "var(--text-primary)",
              }}
              labelFormatter={(v) => `strike $${formatNumber(Number(v))}`}
              formatter={(value, name) => [formatPercent(Number(value)), String(name)]}
            />
            {chain.underlying_close !== null ? (
              <ReferenceLine
                x={chain.underlying_close}
                stroke="var(--baseline)"
                strokeDasharray="3 3"
                label={{ value: "spot", position: "top", fill: "var(--text-muted)", fontSize: 11 }}
              />
            ) : null}
            <Line
              type="monotone"
              dataKey="call"
              name="call IV"
              stroke="var(--series-1)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="put"
              name="put IV"
              stroke="var(--series-2)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
