import type { DriftStatus } from "../api/types";
import { formatDate, formatNumber, formatPercent } from "../lib/format";

export function DriftPanel({ drift }: { drift: DriftStatus }) {
  if (!drift.date) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        No drift checks recorded yet.
      </p>
    );
  }
  const maxPsi = Math.max(0.4, ...drift.features.map((f) => f.psi));
  return (
    <div>
      <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
        {formatDate(drift.date)} · {formatPercent(drift.share_drifted)} of features drifted
        {drift.drifted ? (
          <span className="ml-2 font-medium" style={{ color: "var(--status-serious)" }}>
            ⚠ retrain triggered
          </span>
        ) : (
          <span className="ml-2 font-medium" style={{ color: "var(--status-good)" }}>
            ✓ stable
          </span>
        )}
      </p>
      <ul className="mt-3 space-y-1.5">
        {drift.features.slice(0, 8).map((f) => (
          <li key={f.feature} className="flex items-center gap-2 text-xs">
            <span className="w-32 shrink-0 truncate" style={{ color: "var(--text-secondary)" }}>
              {f.feature}
            </span>
            <span
              className="h-2 rounded-sm"
              style={{
                width: `${Math.max(2, (f.psi / maxPsi) * 100)}%`,
                background: "var(--seq-450)",
              }}
              aria-hidden
            />
            <span className="tabular shrink-0" style={{ color: "var(--text-muted)" }}>
              {formatNumber(f.psi, 3)}
            </span>
            {f.drifted ? (
              <span className="shrink-0 font-medium" style={{ color: "var(--status-serious)" }}>
                ⚠ drifted
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
