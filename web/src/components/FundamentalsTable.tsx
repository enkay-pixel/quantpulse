import type { FundamentalsOut, FundamentalsRow } from "../api/types";
import { formatDate, formatNumber, formatPercent, formatSignedPercent, formatUsdCompact } from "../lib/format";
import { Term } from "./Term";
import { WatchTag } from "./WatchTag";

/** This page's mark for strong growth, the same threshold the advisor brief uses. */
export const STRONG_GROWTH = 0.1;

/** The page in one paragraph: how many companies are growing or shrinking, and how fresh the
 * figures are. Each company files on its own calendar, so the oldest figures are named. */
export function fundamentalsVerdict(rows: FundamentalsRow[]): string {
  if (rows.length === 0) {
    return "No company figures yet. They appear after the first SEC fetch is built into the marts.";
  }
  const known = rows.filter((r) => r.revenue_growth !== null);
  const growing = known.filter((r) => (r.revenue_growth ?? 0) >= STRONG_GROWTH);
  const shrinking = known.filter((r) => (r.revenue_growth ?? 0) < 0);
  const oldest = rows.reduce((a, b) => (b.through < a.through ? b : a));
  const shrinkText = shrinking.length
    ? `${shrinking.length} sold less: ${shrinking.map((r) => r.ticker).join(", ")}.`
    : "None sold less.";
  return (
    `Of these ${rows.length} companies, ${growing.length} grew revenue by ` +
    `${formatPercent(STRONG_GROWTH, 0)} or more on a year earlier. ${shrinkText} Each reports on its ` +
    `own calendar: the oldest figures here, ${oldest.ticker}'s, run through ` +
    `${formatDate(oldest.through)}. Net profit can swing on one-off gains, so the operating margin ` +
    `is the steadier read.`
  );
}

const TH = "px-3 py-2 font-medium";

/** Revenue, margins, cash and price ratios per US company, from its 10-K and 10-Q filings. */
export function FundamentalsTable({ data }: { data: FundamentalsOut }) {
  if (data.rows.length === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        {fundamentalsVerdict(data.rows)}
      </p>
    );
  }
  const rows = [...data.rows].sort((a, b) => (b.revenue_ttm ?? 0) - (a.revenue_ttm ?? 0));
  return (
    <div>
      <p className="mb-3 text-sm" style={{ color: "var(--text-secondary)" }}>
        {fundamentalsVerdict(data.rows)}
      </p>
      <div className="max-h-[32rem] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0" style={{ background: "var(--surface-1)" }}>
            <tr className="text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
              <th className={`${TH} text-left`}><Term id="ticker" /></th>
              <th className={`${TH} text-right`}><Term id="revenue_ttm" align="right" /></th>
              <th className={`${TH} text-right`}><Term id="revenue_growth" align="right" /></th>
              <th className={`${TH} text-right`}><Term id="operating_margin" align="right" /></th>
              <th className={`${TH} text-right`}><Term id="fcf_margin" align="right" /></th>
              <th className={`${TH} text-right`}><Term id="pe_ratio" align="right" /></th>
              <th className={`${TH} text-right`}><Term id="debt_to_equity" align="right" /></th>
              <th className={`${TH} text-left`}><Term id="through" /></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.ticker} className="border-t" style={{ borderColor: "var(--grid)" }} data-testid={`fundamentals-${r.ticker}`}>
                <td className="px-3 py-1.5 font-medium">
                  {r.ticker}
                  <WatchTag followedBy={r.followed_by} />
                </td>
                <td className="px-3 py-1.5 text-right tabular">{formatUsdCompact(r.revenue_ttm)}</td>
                <td className="px-3 py-1.5 text-right tabular">{formatSignedPercent(r.revenue_growth, 0)}</td>
                <td className="px-3 py-1.5 text-right tabular">{formatPercent(r.operating_margin, 0)}</td>
                <td className="px-3 py-1.5 text-right tabular">{formatPercent(r.fcf_margin, 0)}</td>
                <td className="px-3 py-1.5 text-right tabular">{r.pe_ratio === null ? "—" : formatNumber(r.pe_ratio, 0)}</td>
                <td className="px-3 py-1.5 text-right tabular" style={{ color: "var(--text-secondary)" }}>
                  {r.debt_to_equity === null ? "—" : formatNumber(r.debt_to_equity, 2)}
                </td>
                <td className="px-3 py-1.5 text-xs" style={{ color: "var(--text-muted)" }}>
                  {formatDate(r.through)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
