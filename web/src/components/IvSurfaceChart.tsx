import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { IvSurface } from "../api/types";
import { formatDate, formatPercent } from "../lib/format";

const AXIS_STYLE = { fill: "var(--text-muted)", fontSize: 11 };

/**
 * The two readings the chain endpoint cannot give.
 *
 * `/options/{ticker}/chain` returns one expiry of the latest snapshot, which is the smile —
 * already drawn by IvSkewChart. Reading the same surface *across expiries* is the term
 * structure, and reading it *across snapshots* is what the forward-only capture has been
 * accruing since 2026-07-20. Neither was surfaced anywhere, though the mart computed both.
 *
 * Contracts with under a week to run are excluded upstream, matching the ATM convention in
 * fct_option_summary: the feed's IV for those is unreliable and an opening junk point invites
 * reading a slope that is not there.
 */
export function IvSurfaceChart({ data }: { data: IvSurface }) {
  const { term_structure: term, history } = data;

  if (term.length === 0 && history.length === 0) {
    return (
      <p
        className="py-8 text-center text-sm"
        style={{ color: "var(--text-muted)" }}
      >
        No option snapshots for this ticker yet.
      </p>
    );
  }

  const slope =
    term.length >= 2 ? term[term.length - 1].avg_iv - term[0].avg_iv : null;
  const shape =
    slope === null
      ? null
      : slope > 0.01
        ? "upward — longer-dated options cost more, the usual shape"
        : slope < -0.01
          ? "inverted — near-dated options cost more, which usually means a known event"
          : "flat — no meaningful difference between near and far maturities";

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div>
        <h3
          className="mb-1 text-xs font-semibold"
          style={{ color: "var(--text-secondary)" }}
        >
          Term structure — at-the-money IV by maturity
        </h3>
        <p className="mb-2 text-xs" style={{ color: "var(--text-muted)" }}>
          {data.snapshot_date
            ? `Snapshot ${formatDate(data.snapshot_date)}. `
            : ""}
          {shape ?? "Not enough maturities to read a shape."}
        </p>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart
            data={term}
            margin={{ top: 4, right: 8, bottom: 4, left: 0 }}
          >
            <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" />
            <XAxis
              dataKey="days_to_expiry"
              tick={AXIS_STYLE}
              stroke="var(--grid)"
              label={{
                value: "days to expiry",
                position: "insideBottom",
                offset: -2,
                ...AXIS_STYLE,
              }}
            />
            <YAxis
              tick={AXIS_STYLE}
              stroke="var(--grid)"
              tickFormatter={(v) => formatPercent(v, 0)}
            />
            <Tooltip
              contentStyle={{
                background: "var(--surface)",
                border: "1px solid var(--grid)",
              }}
              formatter={(v: number) => [formatPercent(v, 1), "ATM IV"]}
              labelFormatter={(d) => `${d} days to expiry`}
            />
            <Line
              type="monotone"
              dataKey="avg_iv"
              stroke="var(--accent)"
              dot={false}
              strokeWidth={2}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div>
        <h3
          className="mb-1 text-xs font-semibold"
          style={{ color: "var(--text-secondary)" }}
        >
          ~30-day IV over time
        </h3>
        <p className="mb-2 text-xs" style={{ color: "var(--text-muted)" }}>
          {history.length} snapshot{history.length === 1 ? "" : "s"}. No vendor
          sells this history, so it only exists from the day capture started.
        </p>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart
            data={history}
            margin={{ top: 4, right: 8, bottom: 4, left: 0 }}
          >
            <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" />
            <XAxis
              dataKey="snapshot_date"
              tick={AXIS_STYLE}
              stroke="var(--grid)"
              tickFormatter={(d) => formatDate(d)}
              minTickGap={28}
            />
            <YAxis
              tick={AXIS_STYLE}
              stroke="var(--grid)"
              tickFormatter={(v) => formatPercent(v, 0)}
            />
            <Tooltip
              contentStyle={{
                background: "var(--surface)",
                border: "1px solid var(--grid)",
              }}
              formatter={(v: number) => [formatPercent(v, 1), "ATM IV"]}
              labelFormatter={(d) => formatDate(String(d))}
            />
            <Line
              type="monotone"
              dataKey="avg_iv"
              stroke="var(--accent)"
              dot={false}
              strokeWidth={2}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
