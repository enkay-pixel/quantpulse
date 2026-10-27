import type { Predictions } from "../api/types";
import { formatSignedPercent } from "../lib/format";
import { Term } from "./Term";

interface Props {
  predictions: Predictions;
  selectedTicker: string | null;
  onSelect: (ticker: string) => void;
}

export function PredictionsTable({ predictions, selectedTicker, onSelect }: Props) {
  if (predictions.rows.length === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        No predictions yet — they appear once a model clears the promotion gate. The Model &amp;
        Book tab shows each training decision.
      </p>
    );
  }
  return (
    <div className="max-h-96 overflow-y-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0" style={{ background: "var(--surface-1)" }}>
          <tr className="text-left text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
            <th className="px-3 py-2 font-medium"><Term id="rank" /></th>
            <th className="px-3 py-2 font-medium"><Term id="ticker" /></th>
            <th className="px-3 py-2 text-right font-medium"><Term id="score" align="right" /></th>
          </tr>
        </thead>
        <tbody>
          {predictions.rows.map((row) => (
            <tr
              key={row.ticker}
              onClick={() => onSelect(row.ticker)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(row.ticker);
                }
              }}
              role="button"
              tabIndex={0}
              aria-pressed={row.ticker === selectedTicker}
              aria-label={`Show price chart for ${row.ticker}`}
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
