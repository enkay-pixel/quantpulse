import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { usePrices, useSignalHistory } from "../hooks/useApi";
import { formatDate, formatMoney, formatSignedPercent, type MoneyFormat } from "../lib/format";
import { ChartTooltip } from "./ChartTooltip";

const AXIS_STYLE = { fill: "var(--text-muted)", fontSize: 11 };

// Price and signal are different scales — per the dataviz method we never share a
// y-axis. Instead we stack two panels on a common x-axis (small multiples).
/** Whole units on the axis, unless the prices are small enough that whole units would repeat
 * (a 105p share drawn as £1, £1, £1). */
export function priceAxisDigits(points: { close: number }[], money: MoneyFormat | undefined): number {
  const top = Math.max(0, ...points.map((p) => p.close)) / (money?.divisor ?? 1);
  return top < 10 ? 2 : 0;
}

/** Whole percents on the forecast axis, unless forecasts are small enough that whole percents
 * would repeat (ticks at 0.25% steps drawn as +0%, +0%, +1%, +1%). */
export function signalAxisDigits(points: { score: number }[]): number {
  const top = Math.max(0, ...points.map((p) => Math.abs(p.score)));
  return top < 0.05 ? 1 : 0;
}

export function PriceChart({ ticker, money }: { ticker: string; money: MoneyFormat | undefined }) {
  const prices = usePrices(ticker);
  const signals = useSignalHistory(ticker);

  if (prices.isLoading) {
    return <div className="h-64 animate-pulse rounded-lg" style={{ background: "var(--grid)" }} />;
  }
  if (prices.isError || !prices.data) {
    return (
      <div className="flex h-64 items-center justify-center text-sm" style={{ color: "var(--text-muted)" }}>
        Could not load prices for {ticker}.
      </div>
    );
  }

  const signalPoints = signals.data?.points ?? [];
  const axisDigits = priceAxisDigits(prices.data.points, money);
  const signalDigits = signalAxisDigits(signalPoints);
  const hasSignal = signalPoints.length > 0;

  return (
    <div>
      <div className="h-52" role="img" aria-label={`Adjusted close price of ${ticker}`}>
        <ResponsiveContainer>
          <LineChart data={prices.data.points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
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
              tickFormatter={(v: number) => formatMoney(v, money, axisDigits)}
            />
            <Tooltip
              content={<ChartTooltip format={(v) => `close ${formatMoney(v, money)}`} />}
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

      <p className="mt-2 mb-0.5 text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
        The model's forecast for the next month (21 trading days), day by day
      </p>
      {hasSignal ? (
        <div className="h-24" role="img" aria-label={`Model signal history for ${ticker}`}>
          <ResponsiveContainer>
            <BarChart data={signalPoints} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
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
                tickFormatter={(v: number) => formatSignedPercent(v, signalDigits)}
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
                labelFormatter={(d) => formatDate(String(d))}
                formatter={(value) => [formatSignedPercent(Number(value)), "forecast"]}
              />
              <ReferenceLine y={0} stroke="var(--baseline)" />
              <Bar dataKey="score" isAnimationActive={false}>
                {signalPoints.map((p) => (
                  <Cell
                    key={p.date}
                    fill={p.score >= 0 ? "var(--delta-up)" : "var(--delta-down)"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div
          className="flex h-24 items-center justify-center text-xs"
          style={{ color: "var(--text-muted)" }}
        >
          No scored history for {ticker} yet.
        </div>
      )}
    </div>
  );
}
