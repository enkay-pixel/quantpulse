import type { AttentionOut, AttentionRow } from "../api/types";
import { formatDate, formatNumber } from "../lib/format";

/** This page's convention for "unusual": three times the usual level. A convention, not a
 * statistical test — the page states it as one. */
export const UNUSUAL = 3;

/** GameStop's ratio on this page's own definition, measured from Wikimedia on 2026-10-16
 * (ADR 0007): 2.1x on 22 January 2021, when its price had already more than tripled, and 42x
 * on the 28th, the day of the peak. Attention rose with the squeeze rather than ahead of it. */
const GME_BEFORE = 2.1;
const GME_PEAK = 42;

function ratio(r: number | null): string {
  return r === null ? "—" : `${formatNumber(r, 1)}×`;
}

function perDay(v: number | null): string {
  return v === null ? "—" : Math.round(v).toLocaleString();
}

export function attentionVerdict(rows: AttentionRow[]): string {
  const known = rows.filter((r) => r.attention_ratio !== null);
  if (known.length === 0) {
    return "Attention history is still building: a ratio needs 60 days of baseline.";
  }
  const top = known.reduce((a, b) => ((b.attention_ratio ?? 0) > (a.attention_ratio ?? 0) ? b : a));
  const lesson =
    `GameStop's reached ${GME_PEAK}× on 28 January 2021, but it was only ${GME_BEFORE}× on the ` +
    `22nd, when its price had already more than tripled: attention confirms a move more than it ` +
    `warns of one.`;
  const unusual = known.filter((r) => (r.attention_ratio ?? 0) >= UNUSUAL);
  if (unusual.length === 0) {
    return (
      `Nothing here is drawing unusual attention. The highest is ${top.ticker}, whose article ` +
      `drew ${perDay(top.views_7d)} views a day this past week, ${ratio(top.attention_ratio)} its ` +
      `usual level. ${lesson}`
    );
  }
  return (
    `${unusual.length} of these ${known.length} stocks are drawing ${UNUSUAL} times their usual ` +
    `attention or more: ${unusual.map((r) => r.ticker).join(", ")}. The most is ${top.ticker}, at ` +
    `${ratio(top.attention_ratio)}. Attention says a name is being talked about, not which way it ` +
    `will move. ${lesson}`
  );
}

function byRatio(a: AttentionRow, b: AttentionRow): number {
  return (b.attention_ratio ?? -1) - (a.attention_ratio ?? -1);
}

/**
 * Public attention per stock: the past week's daily Wikipedia views against the article's usual
 * level. The one research measure that covers the JSE as well as the NYSE.
 */
export function AttentionTable({
  data,
  selected,
  onSelect,
}: {
  data: AttentionOut;
  selected: string | null;
  onSelect: (ticker: string) => void;
}) {
  if (data.rows.length === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        No attention history yet. It appears after the first page-view fetch is built into the
        marts.
      </p>
    );
  }
  const rows = [...data.rows].sort(byRatio);
  return (
    <div>
      <p className="mb-3 text-sm" style={{ color: "var(--text-secondary)" }}>
        {attentionVerdict(data.rows)}
      </p>
      <p className="mb-2 text-xs" style={{ color: "var(--text-muted)" }}>
        Wikipedia views through {formatDate(data.as_of)} · usual = median of the 90 days before
        the week · {UNUSUAL}× or more is this page's mark for unusual
      </p>
      <div className="max-h-80 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0" style={{ background: "var(--surface-1)" }}>
            <tr className="text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
              <th className="px-3 py-2 text-left font-medium">Ticker</th>
              <th className="px-3 py-2 text-right font-medium">Views a day, past week</th>
              <th className="px-3 py-2 text-right font-medium">Usual</th>
              <th className="px-3 py-2 text-right font-medium">× usual</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const isSelected = row.ticker === selected;
              const unusual = (row.attention_ratio ?? 0) >= UNUSUAL;
              return (
                <tr
                  key={row.ticker}
                  className="border-t"
                  style={{ borderColor: "var(--grid)", background: isSelected ? "var(--page)" : undefined }}
                  aria-selected={isSelected}
                  data-testid={`attention-${row.ticker}`}
                >
                  <td className="px-3 py-1.5">
                    <button
                      type="button"
                      onClick={() => onSelect(row.ticker)}
                      className="font-medium underline-offset-2 hover:underline"
                      style={{ color: "var(--text-primary)" }}
                      title={row.article}
                    >
                      {isSelected ? "▸ " : ""}
                      {row.ticker}
                    </button>
                  </td>
                  <td className="px-3 py-1.5 text-right tabular">{perDay(row.views_7d)}</td>
                  <td className="px-3 py-1.5 text-right tabular" style={{ color: "var(--text-muted)" }}>
                    {perDay(row.baseline_90d)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular">
                    {ratio(row.attention_ratio)}
                    {unusual ? (
                      <span className="ml-1 text-xs" style={{ color: "var(--text-secondary)" }}>
                        unusual
                      </span>
                    ) : null}
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
