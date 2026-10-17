import type { ReactNode } from "react";

import type { PositioningOut, PositioningRow } from "../api/types";
import {
  formatDate,
  formatNumber,
  formatPercent,
  formatSignedPercent,
  formatUsdCompact,
} from "../lib/format";
import { Term } from "./Term";
import { WatchTag } from "./WatchTag";

/** Commonly cited bands for short interest as a share of float. They describe how much fuel a
 * short squeeze would have, not whether one is coming; the page says so beside them. */
export const SHORT_HIGH = 0.2;
export const SHORT_ELEVATED = 0.1;

export function shortBand(pct: number | null): "high" | "elevated" | null {
  if (pct === null) return null;
  if (pct >= SHORT_HIGH) return "high";
  if (pct >= SHORT_ELEVATED) return "elevated";
  return null;
}

function stocksOf(rows: PositioningRow[]): PositioningRow[] {
  return rows.filter((r) => r.asset_type === "stock");
}

/** The short-squeeze fuel across the stocks, against the bands and the one case everyone knows. */
export function shortInterestVerdict(rows: PositioningRow[]): string {
  const known = stocksOf(rows).filter((r) => r.short_pct_float !== null);
  if (known.length === 0) {
    return "Short interest has not been fetched yet; it arrives with the next weekday-morning run.";
  }
  const top = known.reduce((a, b) => ((b.short_pct_float ?? 0) > (a.short_pct_float ?? 0) ? b : a));
  const where = `${top.ticker}, at ${formatPercent(top.short_pct_float, 1)} of its float and ${formatNumber(top.days_to_cover, 1)} days to cover`;
  const high = known.filter((r) => (r.short_pct_float ?? 0) >= SHORT_HIGH);
  if (high.length === 0) {
    return (
      `The most-shorted of these ${known.length} stocks is ${where}. None reaches the 20% of ` +
      `float commonly called high, against more than 100% at GameStop in January 2021, so the ` +
      `short-squeeze fuel here is ordinary.`
    );
  }
  return (
    `${high.length} of these ${known.length} stocks have 20% or more of their float sold short: ` +
    `${high.map((r) => r.ticker).join(", ")}. The most-shorted is ${where}. That is fuel for a ` +
    `squeeze, not a sign that one is coming.`
  );
}

/** The largest call-hedging exposure among the stocks, stated with the assumption it rests on. */
export function gammaVerdict(rows: PositioningRow[]): string | null {
  const sized = stocksOf(rows).filter((r) => r.call_gamma_share_of_adv !== null);
  if (sized.length === 0) return null;
  const top = sized.reduce((a, b) =>
    (b.call_gamma_share_of_adv ?? 0) > (a.call_gamma_share_of_adv ?? 0) ? b : a,
  );
  return (
    `If dealers had sold every listed call on ${top.ticker}, a 1% rise would have them buy ` +
    `${formatUsdCompact(top.call_gamma_usd_1pct)} of stock to stay hedged, ` +
    `${formatPercent(top.call_gamma_share_of_adv, 0)} of a normal day's dollar volume: the most ` +
    `of these stocks. That is an upper bound. Many calls are sold by customers rather than ` +
    `dealers, and public data does not say which.`
  );
}

function byCallShare(a: PositioningRow, b: PositioningRow): number {
  return (b.call_gamma_share_of_adv ?? -1) - (a.call_gamma_share_of_adv ?? -1);
}

function Cell({ children, muted }: { children: ReactNode; muted?: boolean }) {
  return (
    <td
      className="px-3 py-1.5 text-right tabular"
      style={{ color: muted ? "var(--text-muted)" : "var(--text-primary)" }}
    >
      {children}
    </td>
  );
}

function Row({
  row,
  selected,
  onSelect,
}: {
  row: PositioningRow;
  selected: boolean;
  onSelect: (ticker: string) => void;
}) {
  const band = shortBand(row.short_pct_float);
  return (
    <tr
      className="border-t"
      style={{ borderColor: "var(--grid)", background: selected ? "var(--page)" : undefined }}
      aria-selected={selected}
      data-testid={`positioning-${row.ticker}`}
    >
      <td className="px-3 py-1.5">
        <button
          type="button"
          onClick={() => onSelect(row.ticker)}
          className="font-medium underline-offset-2 hover:underline"
          style={{ color: "var(--text-primary)" }}
        >
          {selected ? "▸ " : ""}
          {row.ticker}
        </button>
        <WatchTag followedBy={row.followed_by} />
      </td>
      <Cell>
        {formatPercent(row.short_pct_float, 1)}
        {band ? (
          <span className="ml-1 text-xs" style={{ color: "var(--text-secondary)" }}>
            {band}
          </span>
        ) : null}
      </Cell>
      <Cell>{formatNumber(row.days_to_cover, 1)}</Cell>
      <Cell muted>{formatSignedPercent(row.short_change, 0)}</Cell>
      <Cell>{formatUsdCompact(row.call_gamma_usd_1pct)}</Cell>
      <Cell muted>{formatPercent(row.call_gamma_share_of_adv, 0)}</Cell>
      <Cell>{formatUsdCompact(row.put_gamma_usd_1pct)}</Cell>
      <Cell muted>{formatPercent(row.put_gamma_share_of_adv, 0)}</Cell>
      <Cell muted>{formatPercent(row.call_gamma_near_share, 0)}</Cell>
    </tr>
  );
}

/**
 * Where the GameStop mechanics would be loaded, across the names with option chains.
 *
 * Two kinds of fuel, side by side: short interest (short sellers who would have to buy back) and
 * the hedging exposure from listed options (dealers who would have to buy as the price rose, if
 * they had sold the calls). Stocks are ranked by the second; ETFs are listed apart, because new
 * units can be created on demand and the squeeze mechanics do not apply to them the same way.
 */
export function PositioningTable({
  data,
  selected,
  onSelect,
}: {
  data: PositioningOut;
  selected: string | null;
  onSelect: (ticker: string) => void;
}) {
  if (data.rows.length === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        No positioning yet. It appears after the first option snapshot is built into the marts.
      </p>
    );
  }
  const stocks = stocksOf(data.rows).sort(byCallShare);
  const etfs = data.rows.filter((r) => r.asset_type !== "stock").sort(byCallShare);
  const settled = data.rows.find((r) => r.short_settlement_date)?.short_settlement_date ?? null;
  const gamma = gammaVerdict(data.rows);
  return (
    <div>
      <div className="mb-3 space-y-2 text-sm" style={{ color: "var(--text-secondary)" }}>
        <p>{shortInterestVerdict(data.rows)}</p>
        {gamma ? <p>{gamma}</p> : null}
      </div>
      <p className="mb-2 text-xs" style={{ color: "var(--text-muted)" }}>
        Options as of {formatDate(data.snapshot_date)}
        {settled ? ` · short interest settled ${formatDate(settled)}` : ""} · select a ticker
        to see its strikes
      </p>
      <div className="max-h-[32rem] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0" style={{ background: "var(--surface-1)" }}>
            <tr className="text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
              <th className="px-3 py-2 text-left font-medium"><Term id="ticker" /></th>
              <th className="px-3 py-2 text-right font-medium"><Term id="short_pct_float" align="right" /></th>
              <th className="px-3 py-2 text-right font-medium"><Term id="days_to_cover" align="right" /></th>
              <th className="px-3 py-2 text-right font-medium"><Term id="short_change" align="right" /></th>
              <th className="px-3 py-2 text-right font-medium"><Term id="call_gamma_usd_1pct" align="right" /></th>
              <th className="px-3 py-2 text-right font-medium"><Term id="call_gamma_share_of_adv" align="right" /></th>
              <th className="px-3 py-2 text-right font-medium"><Term id="put_gamma_usd_1pct" align="right" /></th>
              <th className="px-3 py-2 text-right font-medium"><Term id="put_gamma_share_of_adv" align="right" /></th>
              <th className="px-3 py-2 text-right font-medium"><Term id="call_gamma_near_share" align="right" /></th>
            </tr>
          </thead>
          <tbody>
            {stocks.map((row) => (
              <Row key={row.ticker} row={row} selected={row.ticker === selected} onSelect={onSelect} />
            ))}
            {etfs.length > 0 ? (
              <tr>
                <td
                  colSpan={9}
                  className="px-3 pb-1 pt-4 text-xs"
                  style={{ color: "var(--text-muted)" }}
                >
                  ETFs, listed apart: new units can be created on demand, so a squeeze does not
                  work on them the way it does on a stock.
                </td>
              </tr>
            ) : null}
            {etfs.map((row) => (
              <Row key={row.ticker} row={row} selected={row.ticker === selected} onSelect={onSelect} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
