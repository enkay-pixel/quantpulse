import type { OptionChain } from "../api/types";
import { formatNumber, formatPercent } from "../lib/format";

export function OptionChainTable({ chain }: { chain: OptionChain }) {
  if (chain.contracts.length === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        No contracts captured yet.
      </p>
    );
  }
  return (
    <div className="max-h-96 overflow-y-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0" style={{ background: "var(--surface-1)" }}>
          <tr className="text-left text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
            <th className="px-2 py-2 font-medium">Type</th>
            <th className="px-2 py-2 text-right font-medium">Strike</th>
            <th className="px-2 py-2 text-right font-medium">Mid</th>
            <th className="px-2 py-2 text-right font-medium">IV</th>
            <th className="px-2 py-2 text-right font-medium">Δ</th>
            <th className="px-2 py-2 text-right font-medium">Γ</th>
            <th className="px-2 py-2 text-right font-medium">Θ</th>
            <th className="px-2 py-2 text-right font-medium">OI</th>
          </tr>
        </thead>
        <tbody>
          {chain.contracts.map((c) => {
            const mid = c.bid !== null && c.ask !== null ? (c.bid + c.ask) / 2 : c.last_price;
            return (
              <tr
                key={`${c.option_type}-${c.strike}`}
                className="border-t"
                style={{ borderColor: "var(--grid)" }}
              >
                <td
                  className="px-2 py-1.5 text-xs font-semibold uppercase"
                  style={{
                    color: c.option_type === "call" ? "var(--delta-up)" : "var(--delta-down)",
                  }}
                >
                  {c.option_type}
                </td>
                <td className="tabular px-2 py-1.5 text-right font-medium">
                  ${formatNumber(c.strike, 0)}
                </td>
                <td className="tabular px-2 py-1.5 text-right" style={{ color: "var(--text-secondary)" }}>
                  {mid !== null ? `$${formatNumber(mid)}` : "—"}
                </td>
                <td className="tabular px-2 py-1.5 text-right" style={{ color: "var(--text-secondary)" }}>
                  {formatPercent(c.implied_volatility, 0)}
                </td>
                <td className="tabular px-2 py-1.5 text-right" style={{ color: "var(--text-secondary)" }}>
                  {formatNumber(c.delta, 2)}
                </td>
                <td className="tabular px-2 py-1.5 text-right" style={{ color: "var(--text-secondary)" }}>
                  {formatNumber(c.gamma, 3)}
                </td>
                <td className="tabular px-2 py-1.5 text-right" style={{ color: "var(--text-secondary)" }}>
                  {formatNumber(c.theta, 3)}
                </td>
                <td className="tabular px-2 py-1.5 text-right" style={{ color: "var(--text-muted)" }}>
                  {c.open_interest.toLocaleString()}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
