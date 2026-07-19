import type { ModelRunEntry } from "../api/types";
import { formatNumber, formatPercent } from "../lib/format";

export function ModelHistoryTable({ runs }: { runs: ModelRunEntry[] }) {
  if (runs.length === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        No training runs recorded yet.
      </p>
    );
  }
  return (
    <div className="max-h-96 overflow-y-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0" style={{ background: "var(--surface-1)" }}>
          <tr className="text-left text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
            <th className="px-3 py-2 font-medium">Version</th>
            <th className="px-3 py-2 font-medium">Trained</th>
            <th className="px-3 py-2 font-medium">Decision</th>
            <th className="px-3 py-2 text-right font-medium">Holdout IC</th>
            <th className="px-3 py-2 text-right font-medium">Sharpe</th>
            <th className="px-3 py-2 text-right font-medium">Max DD</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id} className="border-t" style={{ borderColor: "var(--grid)" }}>
              <td className="px-3 py-1.5 font-medium">
                {run.model_version ? `v${run.model_version}` : "—"}
              </td>
              <td className="tabular px-3 py-1.5 text-xs" style={{ color: "var(--text-secondary)" }}>
                {new Date(run.created_at).toLocaleString(undefined, {
                  dateStyle: "medium",
                  timeStyle: "short",
                })}
              </td>
              <td
                className="px-3 py-1.5 text-xs font-semibold"
                style={{
                  color: run.decision === "promoted" ? "var(--status-good)" : "var(--text-muted)",
                }}
              >
                {run.decision === "promoted" ? "✓ promoted" : `✗ ${run.decision ?? "unknown"}`}
              </td>
              <td className="tabular px-3 py-1.5 text-right" style={{ color: "var(--text-secondary)" }}>
                {formatNumber(run.metrics.holdout_ic, 3)}
              </td>
              <td className="tabular px-3 py-1.5 text-right" style={{ color: "var(--text-secondary)" }}>
                {formatNumber(run.metrics.holdout_sharpe)}
              </td>
              <td className="tabular px-3 py-1.5 text-right" style={{ color: "var(--text-secondary)" }}>
                {formatPercent(run.metrics.holdout_max_drawdown)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
