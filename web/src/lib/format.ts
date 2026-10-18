import type { Exchange } from "../api/types";

export function formatPercent(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatSignedPercent(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(digits)}%`;
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function deltaColor(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value) || value === 0) {
    return "var(--text-primary)";
  }
  return value > 0 ? "var(--delta-up)" : "var(--delta-down)";
}

/** A market's quote convention: how to turn a stored price into a displayed one. */
export interface MoneyFormat {
  symbol: string;
  divisor: number;
}

/** US dollars: for figures that are dollars whatever market is selected, such as SEC filings. */
export const USD: MoneyFormat = { symbol: "$", divisor: 1 };

/** A market's quote convention, from the backend's exchange registry; undefined until it loads. */
export function moneyOf(
  market: Pick<Exchange, "display_symbol" | "display_divisor"> | undefined,
): MoneyFormat | undefined {
  return market ? { symbol: market.display_symbol, divisor: market.display_divisor } : undefined;
}

/**
 * Format a price in its market's own units.
 *
 * The JSE quotes in cents (ZAc) and London in pence (GBp), so a stored 79787 is R797.87 and a
 * stored 1428 is £14.28 — showing either raw overstates it 100x. The convention is a required
 * argument, never a default: a default of dollars is how prices in rand and pounds came to be
 * drawn as dollars. Until the market's convention is known the price is a dash, since a number in
 * the wrong units reads as a fact.
 */
export function formatMoney(
  value: number | null | undefined,
  money: MoneyFormat | undefined,
  digits = 2,
): string {
  if (value === null || value === undefined || Number.isNaN(value) || !money) return "—";
  return `${money.symbol}${(value / money.divisor).toFixed(digits)}`;
}

/** Dollars at a glance: $2.2B, $600M, $45K. For sizes where the digits past the third carry no
 * information, such as a hedging exposure that rests on an assumption anyway. */
export function formatUsdCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(abs >= 1e8 ? 0 : 1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

/** "Class A" from a stake filing's class title, or null for a company with one class of stock.
 * Where a company has several, a stake is filed per class, and a percentage read against the
 * wrong class (Berkshire's A, not the B this page tracks) overstates it many times over. */
export function shareClass(title: string | null | undefined): string | null {
  const match = /\bclass\s+([A-Z])\b/i.exec(title ?? "");
  return match ? `Class ${match[1].toUpperCase()}` : null;
}
