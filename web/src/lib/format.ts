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
