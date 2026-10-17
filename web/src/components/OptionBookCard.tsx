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

import type { OptionBookCohort, OptionBookOut, OptionBookPosition } from "../api/types";
import { formatDate, formatNumber, formatPercent, formatSignedPercent } from "../lib/format";
import { Term } from "./Term";

const AXIS_STYLE = { fill: "var(--text-muted)", fontSize: 11 };

function mean(values: number[]): number | null {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}

/** The book in one paragraph: how much evidence there is, what it shows, and why it is not
 * enough yet. Months, not days, are the unit — each cohort is one month. */
export function optionBookVerdict(data: OptionBookOut): string {
  const n = data.cohorts.length;
  if (n === 0) {
    return "The book has not opened a cohort yet. It opens on the monthly share book's next rebalance.";
  }
  const live = data.cohorts.filter((c) => c.phase === "live").length;
  const counts =
    `${n} ${n === 1 ? "cohort" : "cohorts"} so far — ${n - live} replayed from before ` +
    `${formatDate(data.live_since)}, ${live} live`;
  const closed = data.cohorts.filter((c) => c.exit_date !== null && c.options_return !== null);
  if (closed.length === 0) {
    return `${counts}. None has closed yet, so there is no result to compare.`;
  }
  const options = mean(closed.map((c) => c.options_return as number));
  const premium = mean(closed.map((c) => c.return_on_premium as number));
  const shares = mean(closed.flatMap((c) => (c.shares_return === null ? [] : [c.shares_return])));
  const sharesText =
    shares === null ? "" : `, against ${formatSignedPercent(shares, 1)} for the same names held as shares`;
  return (
    `${counts}. Over the ${closed.length} closed, the options book made ` +
    `${formatSignedPercent(options, 1)} a month on its value — ${formatSignedPercent(premium, 0)} on ` +
    `what it paid for its spreads${sharesText}. With ${closed.length} ${closed.length === 1 ? "month" : "months"} ` +
    `that difference says nothing yet: telling the two apart takes years of cohorts. Each cohort ` +
    `risks ${formatPercent(data.risk_budget, 0)} of the book.`
  );
}

function structure(p: OptionBookPosition): string {
  if (p.long_strike === null || p.short_strike === null) return "—";
  const kind = p.option_type === "call" ? "Bull call" : "Bear put";
  return `${kind} ${formatNumber(p.long_strike, 0)}/${formatNumber(p.short_strike, 0)}`;
}

const TH = "px-3 py-2 font-medium";

function CohortTable({ cohorts }: { cohorts: OptionBookCohort[] }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
          <th className={`${TH} text-left`}><Term id="opened" /></th>
          <th className={`${TH} text-left`}><Term id="exit_date" /></th>
          <th className={`${TH} text-right`}><Term id="spreads" align="right" /></th>
          <th className={`${TH} text-right`}><Term id="skipped" align="right" /></th>
          <th className={`${TH} text-right`}><Term id="options_return" align="right" /></th>
          <th className={`${TH} text-right`}><Term id="return_on_premium" align="right" /></th>
          <th className={`${TH} text-right`}><Term id="shares_return" align="right" /></th>
        </tr>
      </thead>
      <tbody>
        {[...cohorts].reverse().map((c) => (
          <tr key={c.opened} className="border-t" style={{ borderColor: "var(--grid)" }}>
            <td className="px-3 py-1.5">
              {formatDate(c.opened)}
              <span className="ml-1 text-xs" style={{ color: "var(--text-muted)" }}>
                {c.phase}
              </span>
            </td>
            <td className="px-3 py-1.5">{c.exit_date ? formatDate(c.exit_date) : "open"}</td>
            <td className="px-3 py-1.5 text-right tabular">{c.spreads}</td>
            <td className="px-3 py-1.5 text-right tabular" style={{ color: "var(--text-muted)" }}>
              {c.skipped}
            </td>
            <td className="px-3 py-1.5 text-right tabular">{formatSignedPercent(c.options_return, 1)}</td>
            <td className="px-3 py-1.5 text-right tabular">{formatSignedPercent(c.return_on_premium, 0)}</td>
            <td className="px-3 py-1.5 text-right tabular" style={{ color: "var(--text-muted)" }}>
              {formatSignedPercent(c.shares_return, 1)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PositionTable({ positions }: { positions: OptionBookPosition[] }) {
  const traded = positions.filter((p) => p.status !== "skipped");
  const skipped = positions.filter((p) => p.status === "skipped");
  return (
    <div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
            <th className={`${TH} text-left`}><Term id="ticker" /></th>
            <th className={`${TH} text-left`}><Term id="structure" /></th>
            <th className={`${TH} text-left`}><Term id="expiry" /></th>
            <th className={`${TH} text-right`}><Term id="entry_debit" align="right" /></th>
            <th className={`${TH} text-right`}><Term id="mark_value" align="right" /></th>
            <th className={`${TH} text-right`}><Term id="return_on_premium" align="right" /></th>
            <th className={`${TH} text-left`}><Term id="mark_basis" /></th>
          </tr>
        </thead>
        <tbody>
          {traded.map((p) => (
            <tr key={p.ticker} className="border-t" style={{ borderColor: "var(--grid)" }} data-testid={`spread-${p.ticker}`}>
              <td className="px-3 py-1.5 font-medium">{p.ticker}</td>
              <td className="px-3 py-1.5">{structure(p)}</td>
              <td className="px-3 py-1.5">{p.expiry ? formatDate(p.expiry) : "—"}</td>
              <td className="px-3 py-1.5 text-right tabular">${formatNumber(p.entry_debit)}</td>
              <td className="px-3 py-1.5 text-right tabular">${formatNumber(p.mark_value)}</td>
              <td className="px-3 py-1.5 text-right tabular">{formatSignedPercent(p.return_on_premium, 0)}</td>
              <td className="px-3 py-1.5 text-xs" style={{ color: "var(--text-muted)" }}>
                {p.mark_basis}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {skipped.length ? (
        <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
          Could not trade:{" "}
          {skipped.map((p) => `${p.ticker} (${p.note ?? "no reason recorded"})`).join("; ")}.
        </p>
      ) : null}
    </div>
  );
}

/**
 * The paper options book (ADR 0008): the model's forecasts held through limited-risk spreads
 * instead of shares, beside the monthly share book holding the same names over the same windows.
 */
export function OptionBookCard({ data }: { data: OptionBookOut }) {
  if (data.days.length === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        {optionBookVerdict(data)}
      </p>
    );
  }
  const liveStart = data.days.find((d) => d.phase === "live")?.date;
  return (
    <div className="space-y-4">
      <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
        {optionBookVerdict(data)}
      </p>
      <div>
        <div className="mb-2 flex flex-wrap items-center gap-4 text-xs" style={{ color: "var(--text-secondary)" }}>
          <span className="flex items-center gap-1.5">
            <svg width="18" height="6" aria-hidden>
              <line x1="0" y1="3" x2="18" y2="3" stroke="var(--series-1)" strokeWidth="2" />
            </svg>
            Options book
          </span>
          <span className="flex items-center gap-1.5">
            <svg width="18" height="6" aria-hidden>
              <line x1="0" y1="3" x2="18" y2="3" stroke="var(--series-3)" strokeWidth="2" />
            </svg>
            Same forecasts as shares, traded monthly
          </span>
        </div>
        <div className="h-56" role="img" aria-label="Options book value against the monthly share book">
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
                width={44}
                domain={["auto", "auto"]}
                tickFormatter={(v: number) => formatNumber(v, 2)}
              />
              <Tooltip
                contentStyle={{ background: "var(--surface-1)", border: "1px solid var(--border)", fontSize: 12 }}
                labelFormatter={(d) => formatDate(String(d))}
                formatter={(v, name) => [formatNumber(Number(v), 3), String(name)]}
              />
              {liveStart ? (
                <ReferenceLine
                  x={liveStart}
                  stroke="var(--text-muted)"
                  strokeDasharray="3 3"
                  label={{ value: "live", position: "top", fill: "var(--text-muted)", fontSize: 11 }}
                />
              ) : null}
              <Line
                type="monotone"
                dataKey="equity"
                name="options book"
                stroke="var(--series-1)"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="share_equity"
                name="as shares, monthly"
                stroke="var(--series-3)"
                strokeWidth={2}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
      <CohortTable cohorts={data.cohorts} />
      {data.positions.length ? (
        <div>
          <p className="mb-1 text-xs" style={{ color: "var(--text-muted)" }}>
            The newest cohort, opened {formatDate(data.cohorts[data.cohorts.length - 1]?.opened)}
          </p>
          <PositionTable positions={data.positions} />
        </div>
      ) : null}
    </div>
  );
}
