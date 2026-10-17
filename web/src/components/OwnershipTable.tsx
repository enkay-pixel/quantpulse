import type { OwnershipOut, OwnershipRow } from "../api/types";
import { formatDate, formatPercent, formatUsdCompact, shareClass } from "../lib/format";
import { Term } from "./Term";
import { WatchTag } from "./WatchTag";

/** The page's reading of insider activity in one paragraph. Buying on the open market is the
 * rarer, more telling act; selling is mostly routine, and much of it planned months ahead. */
export function ownershipVerdict(rows: OwnershipRow[]): string {
  if (rows.length === 0) {
    return "No ownership filings yet. They appear after the first EDGAR fetch is built into the marts.";
  }
  const buying = rows.filter((r) => r.buyers_90d > 0);
  const selling = rows.filter((r) => r.sellers_90d > 0);
  const activists = rows.filter((r) => r.activist_holder);
  const buyText =
    buying.length === 0
      ? "No insider bought on the open market at any of these companies in the past 90 days, which is common: insiders mostly receive stock as pay rather than buy it."
      : `Insiders bought on the open market at ${buying.length} of these ${rows.length} companies in the past 90 days: ${buying
          .map((r) => r.ticker)
          .join(", ")}. Buying with one's own money is the rarer and more telling act.`;
  const sellText = `Insiders sold at ${selling.length}; most such selling is routine, and much of it is planned months in advance.`;
  const activistText = activists.length
    ? ` A holder that may seek to influence the company (a 13D filer) holds over 5% of ${activists
        .map((r) => r.ticker)
        .join(", ")}.`
    : "";
  return `${buyText} ${sellText}${activistText}`;
}

function byBuying(a: OwnershipRow, b: OwnershipRow): number {
  return b.bought_usd_90d - a.bought_usd_90d || b.sold_usd_90d - a.sold_usd_90d;
}

/** Insider trading and large holders per US stock, from SEC EDGAR filings (ADR 0007). */
export function OwnershipTable({
  data,
  selected,
  onSelect,
}: {
  data: OwnershipOut;
  selected: string | null;
  onSelect: (ticker: string) => void;
}) {
  if (data.rows.length === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        {ownershipVerdict(data.rows)}
      </p>
    );
  }
  const rows = [...data.rows].sort(byBuying);
  return (
    <div>
      <p className="mb-3 text-sm" style={{ color: "var(--text-secondary)" }}>
        {ownershipVerdict(data.rows)}
      </p>
      <p className="mb-2 text-xs" style={{ color: "var(--text-muted)" }}>
        SEC filings through {formatDate(data.as_of)} · open-market trades only, not grants or
        exercises · holders as of each one's latest filing
      </p>
      <div className="max-h-96 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0" style={{ background: "var(--surface-1)" }}>
            <tr className="text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
              <th className="px-3 py-2 text-left font-medium"><Term id="ticker" /></th>
              <th className="px-3 py-2 text-right font-medium"><Term id="bought_usd_90d" align="right" /></th>
              <th className="px-3 py-2 text-right font-medium"><Term id="sold_usd_90d" align="right" /></th>
              <th className="px-3 py-2 text-right font-medium"><Term id="planned_sold_share_90d" align="right" /></th>
              <th className="px-3 py-2 text-right font-medium"><Term id="holders_over_5pct" align="right" /></th>
              <th className="px-3 py-2 text-left font-medium"><Term id="top_holder" /></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const isSelected = row.ticker === selected;
              return (
                <tr
                  key={row.ticker}
                  className="border-t"
                  style={{ borderColor: "var(--grid)", background: isSelected ? "var(--page)" : undefined }}
                  aria-selected={isSelected}
                  data-testid={`ownership-${row.ticker}`}
                >
                  <td className="px-3 py-1.5">
                    <button
                      type="button"
                      onClick={() => onSelect(row.ticker)}
                      className="font-medium underline-offset-2 hover:underline"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {isSelected ? "▸ " : ""}
                      {row.ticker}
                    </button>
                    <WatchTag followedBy={row.followed_by} />
                  </td>
                  <td className="px-3 py-1.5 text-right tabular">
                    {row.bought_usd_90d > 0 ? `${formatUsdCompact(row.bought_usd_90d)} · ${row.buyers_90d}` : "—"}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular" style={{ color: "var(--text-secondary)" }}>
                    {row.sold_usd_90d > 0 ? `${formatUsdCompact(row.sold_usd_90d)} · ${row.sellers_90d}` : "—"}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular" style={{ color: "var(--text-muted)" }}>
                    {formatPercent(row.planned_sold_share_90d, 0)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular">{row.holders_over_5pct || "—"}</td>
                  <td className="px-3 py-1.5" style={{ color: "var(--text-secondary)" }}>
                    {row.top_holder ? (
                      <>
                        {row.top_holder}{" "}
                        <span className="tabular" style={{ color: "var(--text-muted)" }}>
                          {formatPercent((row.top_holder_percent ?? 0) / 100, 1)}
                          {shareClass(row.top_holder_class) ? ` of ${shareClass(row.top_holder_class)}` : ""}
                        </span>
                        {row.activist_holder ? (
                          <span className="ml-1 text-xs" style={{ color: "var(--text-muted)" }}>
                            · 13D
                          </span>
                        ) : null}
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
