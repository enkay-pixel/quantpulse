import type { Positions } from "../api/types";
import { formatDate, formatNumber, formatPercent, formatSignedPercent } from "../lib/format";

export function PositionsTable({ positions }: { positions: Positions }) {
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
              <th className="px-3 py-2 font-medium">Ticker</th>
              <th className="px-3 py-2 font-medium">Side</th>
              <th className="px-3 py-2 text-right font-medium">Weight</th>
              <th className="px-3 py-2 text-right font-medium">Signal</th>
              <th className="px-3 py-2 text-right font-medium">Close</th>
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
                  {row.latest_close !== null ? `$${formatNumber(row.latest_close)}` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
