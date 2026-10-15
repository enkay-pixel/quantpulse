import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ForwardVrpOut } from "../api/types";
import { formatDate, formatPercent } from "../lib/format";

const AXIS_STYLE = { fill: "var(--text-muted)", fontSize: 11 };

/** A difference between two volatilities, in percentage points — "+4.9%" would read as relative. */
function points(diff: number): string {
  const v = (diff * 100).toFixed(1);
  return `${diff > 0 ? "+" : ""}${v} points`;
}

const FINDING =
  "https://github.com/enkay-pixel/quantpulse/blob/main/docs/findings/forward-variance-risk-premium.md";

/**
 * What the option market charged for volatility, against what then arrived.
 *
 * Each point is one snapshot day, averaged over its tickers: at-the-money implied volatility
 * for about a month out, beside the realized volatility of the 21 sessions that followed. The
 * gap between them is the forward variance risk premium. A day appears only once its window has
 * closed, so the line always ends about a month before today — that lag is the measurement,
 * not a delay in the data.
 */
export function ForwardVrpChart({ data }: { data: ForwardVrpOut }) {
  const { days } = data;
  if (days.length === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        Appears once a snapshot's 21-session realization window has closed.
      </p>
    );
  }
  const mean = days.reduce((a, d) => a + d.premium, 0) / days.length;
  const above = days.filter((d) => d.premium > 0).length;
  return (
    <div>
      <p className="mb-2 text-sm" style={{ color: "var(--text-secondary)" }}>
        Over {days.length} snapshot days ({formatDate(days[0].snapshot_date)} to{" "}
        {formatDate(days[days.length - 1].snapshot_date)}), options were priced{" "}
        <strong>{points(mean)}</strong> of volatility above what then arrived, on average, and
        above it on {above} of {days.length} days. One stretch of one market, so
        it cannot yet tell a standing premium from volatility that simply fell —{" "}
        <a
          href={FINDING}
          target="_blank"
          rel="noopener noreferrer"
          className="underline"
          style={{ color: "var(--text-secondary)" }}
        >
          the finding
        </a>{" "}
        has the error bars.
      </p>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={days} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" />
          <XAxis
            dataKey="snapshot_date"
            tick={AXIS_STYLE}
            stroke="var(--grid)"
            tickFormatter={(d: string) => d.slice(5)}
          />
          <YAxis
            tick={AXIS_STYLE}
            stroke="var(--grid)"
            tickFormatter={(v: number) => formatPercent(v, 0)}
            domain={["auto", "auto"]}
          />
          <Tooltip
            contentStyle={{ background: "var(--surface-1)", border: "1px solid var(--grid)" }}
            formatter={(v: number, name: string) => [formatPercent(v, 1), name]}
            labelFormatter={(d: string) => formatDate(d)}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Line
            type="monotone"
            dataKey="implied"
            name="implied (priced)"
            stroke="var(--series-1)"
            dot={false}
            strokeWidth={2}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="realized"
            name="realized over the next 21 sessions"
            stroke="var(--series-2)"
            dot={false}
            strokeWidth={2}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
