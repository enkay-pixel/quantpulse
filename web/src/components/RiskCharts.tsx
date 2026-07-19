import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Risk } from "../api/types";
import { formatDate, formatNumber, formatPercent } from "../lib/format";
import { ChartTooltip } from "./ChartTooltip";

const AXIS_STYLE = { fill: "var(--text-muted)", fontSize: 11 };

export function RiskCharts({ risk }: { risk: Risk }) {
  if (risk.points.length === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        Appears after the first dbt transform run.
      </p>
    );
  }
  const sharpe = risk.points.filter((p) => p.rolling_sharpe_63d !== null);

  return (
    <div className="space-y-5">
      <div>
        <p className="mb-1 text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
          Drawdown from running peak
        </p>
        <div className="h-40" role="img" aria-label="Portfolio drawdown over time">
          <ResponsiveContainer>
            <AreaChart data={risk.points} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
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
                tickFormatter={(v: number) => formatPercent(v, 0)}
              />
              <Tooltip
                content={<ChartTooltip format={(v) => `drawdown ${formatPercent(v)}`} />}
                cursor={{ stroke: "var(--baseline)", strokeWidth: 1 }}
              />
              <Area
                type="monotone"
                dataKey="drawdown"
                stroke="var(--series-1)"
                strokeWidth={2}
                fill="var(--series-1)"
                fillOpacity={0.15}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div>
        <p className="mb-1 text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
          Rolling 63-day Sharpe (annualized)
        </p>
        <div className="h-40" role="img" aria-label="Rolling 63 day Sharpe ratio">
          <ResponsiveContainer>
            <LineChart data={sharpe} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
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
                tickFormatter={(v: number) => formatNumber(v, 1)}
              />
              <Tooltip
                content={<ChartTooltip format={(v) => `Sharpe ${formatNumber(v, 2)}`} />}
                cursor={{ stroke: "var(--baseline)", strokeWidth: 1 }}
              />
              <ReferenceLine y={0} stroke="var(--baseline)" />
              <Line
                type="monotone"
                dataKey="rolling_sharpe_63d"
                stroke="var(--series-1)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 0 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
