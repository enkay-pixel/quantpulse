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

export const USD: MoneyFormat = { symbol: "$", divisor: 1 };

/**
 * Format a price in its market's own units.
 *
 * The JSE quotes in cents (ZAc), so a stored 79787 is R797.87 — showing it raw would
 * overstate every price by 100x. The divisor comes from the backend's exchange registry
 * rather than being hardcoded here, so adding a market is a config change.
 */
export function formatMoney(
  value: number | null | undefined,
  money: MoneyFormat = USD,
  digits = 2,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
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
