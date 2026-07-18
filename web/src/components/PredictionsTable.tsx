import type { Predictions } from "../api/types";
import { formatSignedPercent } from "../lib/format";

interface Props {
  predictions: Predictions;
  selectedTicker: string | null;
  onSelect: (ticker: string) => void;
}

export function PredictionsTable({ predictions, selectedTicker, onSelect }: Props) {
  if (predictions.rows.length === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        No predictions yet — they appear after the first training and scoring runs.
      </p>
    );
  }
  return (
    <div className="max-h-96 overflow-y-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0" style={{ background: "var(--surface-1)" }}>
          <tr className="text-left text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
            <th className="px-3 py-2 font-medium">#</th>
            <th className="px-3 py-2 font-medium">Ticker</th>
            <th className="px-3 py-2 text-right font-medium">21d signal</th>
          </tr>
        </thead>
        <tbody>
          {predictions.rows.map((row) => (
            <tr
              key={row.ticker}
              onClick={() => onSelect(row.ticker)}
              className="cursor-pointer border-t"
              style={{
                borderColor: "var(--grid)",
                background: row.ticker === selectedTicker ? "var(--grid)" : undefined,
              }}
            >
              <td className="tabular px-3 py-1.5" style={{ color: "var(--text-muted)" }}>
                {row.rank}
              </td>
              <td className="px-3 py-1.5 font-medium">{row.ticker}</td>
              <td className="tabular px-3 py-1.5 text-right" style={{ color: "var(--text-secondary)" }}>
                {formatSignedPercent(row.score)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
