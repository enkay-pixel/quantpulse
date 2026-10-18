import type { Positions } from "../api/types";
import {
  formatDate,
  formatMoney,
  formatPercent,
  formatSignedPercent,
  type MoneyFormat,
} from "../lib/format";
import { Term } from "./Term";

export function PositionsTable({
  positions,
  money,
}: {
  positions: Positions;
  money: MoneyFormat | undefined;
}) {
  if (positions.rows.length === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        No positions yet — the paper book fills after the first scored days.
      </p>
    );
  }
  return (
    <div>
      <p className="mb-2 text-xs" style={{ color: "var(--text-secondary)" }}>
        Paper book as of {formatDate(positions.date)} · model v{positions.model_version}
      </p>
      <div className="max-h-96 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0" style={{ background: "var(--surface-1)" }}>
            <tr className="text-left text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
              <th className="px-3 py-2 font-medium"><Term id="ticker" /></th>
              <th className="px-3 py-2 font-medium"><Term id="side" /></th>
              <th className="px-3 py-2 text-right font-medium"><Term id="weight" align="right" /></th>
              <th className="px-3 py-2 text-right font-medium"><Term id="score" align="right" /></th>
              <th className="px-3 py-2 text-right font-medium"><Term id="close" align="right" /></th>
            </tr>
          </thead>
          <tbody>
            {positions.rows.map((row) => (
              <tr key={row.ticker} className="border-t" style={{ borderColor: "var(--grid)" }}>
                <td className="px-3 py-1.5 font-medium">{row.ticker}</td>
                <td
                  className="px-3 py-1.5 text-xs font-semibold uppercase"
                  style={{ color: row.side === "long" ? "var(--delta-up)" : "var(--delta-down)" }}
                >
                  {row.side}
                </td>
                <td className="tabular px-3 py-1.5 text-right" style={{ color: "var(--text-secondary)" }}>
                  {formatPercent(Math.abs(row.weight), 1)}
                </td>
                <td className="tabular px-3 py-1.5 text-right" style={{ color: "var(--text-secondary)" }}>
                  {row.latest_score !== null ? formatSignedPercent(row.latest_score) : "—"}
                </td>
                <td className="tabular px-3 py-1.5 text-right" style={{ color: "var(--text-secondary)" }}>
                  {formatMoney(row.latest_close, money)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
