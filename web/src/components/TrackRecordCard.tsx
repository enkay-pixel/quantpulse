import type { TrackRecord } from "../api/types";
import { deltaColor, formatDate, formatNumber, formatPercent, formatSignedPercent } from "../lib/format";

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>
        {label}
      </div>
      <div className="tabular text-sm font-semibold" style={{ color: color ?? "var(--text-primary)" }}>
        {value}
      </div>
    </div>
  );
}

export function TrackRecordCard({ record }: { record: TrackRecord }) {
  const live = record.phases.find((p) => p.phase === "live");
  const replay = record.phases.find((p) => p.phase === "replay");

  return (
    <div className="card p-4">
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold">Live track record (out-of-sample)</h2>
        {record.live_since ? (
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            since {formatDate(record.live_since)}
          </span>
        ) : null}
      </div>

      {live ? (
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-5">
          <Stat label="Days" value={String(live.n_days)} />
          <Stat
            label="Return"
            value={formatSignedPercent(live.total_return)}
            color={deltaColor(live.total_return)}
          />
          <Stat label="Sharpe" value={formatNumber(live.sharpe)} />
          <Stat label="Max DD" value={formatPercent(live.max_drawdown)} />
          <Stat label="Win rate" value={formatPercent(live.win_rate, 0)} />
        </div>
      ) : (
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Accumulating — the first live out-of-sample day lands with the next scheduled
          pipeline run. Judge the strategy here, not on the replay.
        </p>
      )}

      {replay ? (
        <p className="mt-3 border-t pt-2 text-xs" style={{ borderColor: "var(--grid)", color: "var(--text-muted)" }}>
          In-sample replay for context: {formatSignedPercent(replay.total_return)} over{" "}
          {replay.n_days} days · Sharpe {formatNumber(replay.sharpe)} · max DD{" "}
          {formatPercent(replay.max_drawdown)} — not evidence of skill.
        </p>
      ) : null}
    </div>
  );
}
