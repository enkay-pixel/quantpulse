import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { usePrices } from "../hooks/useApi";
import { formatDate, formatNumber } from "../lib/format";
import { ChartTooltip } from "./ChartTooltip";

const AXIS_STYLE = { fill: "var(--text-muted)", fontSize: 11 };

export function PriceChart({ ticker }: { ticker: string }) {
  const { data, isLoading, isError } = usePrices(ticker);

  if (isLoading) {
    return <div className="h-64 animate-pulse rounded-lg" style={{ background: "var(--grid)" }} />;
  }
  if (isError || !data) {
    return (
      <div className="flex h-64 items-center justify-center text-sm" style={{ color: "var(--text-muted)" }}>
        Could not load prices for {ticker}.
      </div>
    );
  }
  return (
    <div className="h-64" role="img" aria-label={`Adjusted close price of ${ticker}`}>
      <ResponsiveContainer>
        <LineChart data={data.points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
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
            width={56}
            domain={["auto", "auto"]}
            tickFormatter={(v: number) => `$${formatNumber(v, 0)}`}
          />
          <Tooltip
            content={<ChartTooltip format={(v) => `close $${formatNumber(v, 2)}`} />}
            cursor={{ stroke: "var(--baseline)", strokeWidth: 1 }}
          />
          <Line
            type="monotone"
            dataKey="close"
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
