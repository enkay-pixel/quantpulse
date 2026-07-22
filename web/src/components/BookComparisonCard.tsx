import type { BookComparison, BookStats } from "../api/types";
import { formatNumber, formatPercent } from "../lib/format";

const LABELS: Record<string, { name: string; asks: string }> = {
  daily: { name: "Daily", asks: "trade the signal every day" },
  horizon: { name: "21-day", asks: "hold for the model's forecast horizon" },
};

function label(variant: string) {
  return LABELS[variant] ?? { name: variant, asks: "" };
}

/** Plain-English read, so the table can't be mistaken for a recommendation. */
function verdict(books: BookStats[]): string | null {
  const daily = books.find((b) => b.variant === "daily");
  const horizon = books.find((b) => b.variant === "horizon");
  if (!daily || !horizon) return null;
  const gap = horizon.annualized_return - daily.annualized_return;
  if (gap <= 0) {
    return `Trading every day costs ${formatPercent(daily.annualized_cost_drag, 1)} a year in commissions and slippage, yet the daily book is not behind the slower one here. That is unusual — worth re-checking once more live days have accumulated.`;
  }
  // Split the gap: what survives before costs is picks, the remainder is friction.
  const grossGap = horizon.annualized_gross_return - daily.annualized_gross_return;
  const share = Math.round(((gap - grossGap) / gap) * 100);
  return `Holding for the full 21 days earns ${formatPercent(gap, 1)} a year more. About ${share}% of that difference is trading cost rather than better stock picking — it is the same signal either way, just acted on less often.`;
}

export function BookComparisonCard({ data }: { data: BookComparison }) {
  if (data.books.length === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        Appears once the paper books have been built.
      </p>
    );
  }
  const summary = verdict(data.books);

  return (
    <div>
      <p className="mb-3 text-xs" style={{ color: "var(--text-secondary)" }}>
        A <strong>book</strong> is one way of turning the signal into a portfolio. These two run
        over the <strong>same predictions</strong> and differ only in how often they rebalance — so
        whatever separates them is the cost of trading more often, and nothing else.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr style={{ color: "var(--text-muted)" }}>
              <th className="py-1 pr-3 text-left font-normal">Book</th>
              <th className="py-1 pr-3 text-right font-normal">Ann. return</th>
              <th className="py-1 pr-3 text-right font-normal">Sharpe</th>
              <th className="py-1 pr-3 text-right font-normal">Max DD</th>
              <th className="py-1 pr-3 text-right font-normal">Turnover</th>
              <th className="py-1 text-right font-normal">Cost drag</th>
            </tr>
          </thead>
          <tbody>
            {data.books.map((b) => (
              <tr key={b.variant} style={{ borderTop: "1px solid var(--border)" }}>
                <td className="py-2 pr-3">
                  <div style={{ color: "var(--text-primary)" }}>
                    {label(b.variant).name}
                    <span className="ml-1.5 text-xs" style={{ color: "var(--text-muted)" }}>
                      every {b.rebalance_days}d
                    </span>
                  </div>
                  <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {label(b.variant).asks}
                  </div>
                </td>
                <td className="tabular py-2 pr-3 text-right">{formatPercent(b.annualized_return, 2)}</td>
                <td className="tabular py-2 pr-3 text-right">{formatNumber(b.sharpe)}</td>
                <td className="tabular py-2 pr-3 text-right">{formatPercent(b.max_drawdown, 1)}</td>
                <td className="tabular py-2 pr-3 text-right">{formatNumber(b.mean_turnover, 3)}</td>
                <td
                  className="tabular py-2 text-right"
                  style={{ color: "var(--delta-down)" }}
                  title="annualized commission + slippage paid to maintain this book"
                >
                  {formatPercent(b.annualized_cost_drag, 2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {summary ? (
        <p
          className="mt-3 rounded-lg px-3 py-2 text-xs"
          style={{ background: "var(--grid)", color: "var(--text-secondary)" }}
        >
          {summary} These are in-sample replay figures, so compare the two books against each
          other rather than reading either return as achievable.
        </p>
      ) : null}
    </div>
  );
}
