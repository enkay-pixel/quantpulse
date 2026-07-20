import type { Freshness } from "../api/types";
import { formatDate } from "../lib/format";

const STAGES: { key: keyof Freshness; label: string }[] = [
  { key: "latest_price_date", label: "Prices" },
  { key: "latest_feature_date", label: "Features" },
  { key: "latest_prediction_date", label: "Predictions" },
  { key: "latest_snapshot_date", label: "Portfolio" },
];

// A stage lagging the freshest stage by > 4 calendar days is flagged: the daily
// pipeline probably didn't complete (machine asleep, stack down).
const STALE_DAYS = 4;

function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(a) - Date.parse(b)) / 86_400_000);
}

export function FreshnessStrip({ freshness }: { freshness: Freshness }) {
  const dates = STAGES.map((s) => freshness[s.key]).filter((d): d is string => d !== null);
  if (dates.length === 0) return null;
  const newest = dates.reduce((a, b) => (a > b ? a : b));

  return (
    <div className="card flex flex-wrap gap-x-6 gap-y-2 px-4 py-2.5">
      {STAGES.map((stage) => {
        const value = freshness[stage.key];
        const stale = value !== null && daysBetween(newest, value) > STALE_DAYS;
        const dot = value === null ? "var(--text-muted)" : stale ? "var(--status-serious)" : "var(--status-good)";
        return (
          <div key={stage.key} className="flex items-center gap-2">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: dot }}
              aria-hidden
            />
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              {stage.label}
            </span>
            <span
              className="tabular text-xs font-medium"
              style={{ color: stale ? "var(--status-serious)" : "var(--text-secondary)" }}
              title={stale ? `Lagging by ${daysBetween(newest, value!)} days` : undefined}
            >
              {formatDate(value)}
              {stale ? " ⚠" : ""}
            </span>
          </div>
        );
      })}
    </div>
  );
}
