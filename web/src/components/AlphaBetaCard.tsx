import type { AlphaBeta, AlphaBetaStats } from "../api/types";
import { deltaColor, formatNumber, formatPercent, formatSignedPercent } from "../lib/format";

function Metric({
  label,
  value,
  color,
  hint,
}: {
  label: string;
  value: string;
  color?: string;
  hint: string;
}) {
  return (
    <div>
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>
        {label}
      </div>
      <div
        className="tabular text-lg font-semibold"
        style={{ color: color ?? "var(--text-primary)" }}
      >
        {value}
      </div>
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>
        {hint}
      </div>
    </div>
  );
}

// Plain-English read of the decomposition, so the numbers can't be misread.
function verdict(s: AlphaBetaStats): string {
  const neutral = s.beta !== null && Math.abs(s.beta) < 0.2;
  const posAlpha = (s.alpha_annualized ?? 0) > 0;
  const exposure = neutral
    ? "Market-neutral as designed (beta ≈ 0), so comparing raw return to SPY is not the right test"
    : `Carries real market exposure (beta ${formatNumber(s.beta)}), so part of its return is simply the market`;
  const skill = posAlpha
    ? "and it earns positive alpha — return independent of the market."
    : "but it earns no positive alpha: after accounting for market exposure the signal adds nothing over this window.";
  return `${exposure}, ${skill}`;
}

export function AlphaBetaCard({ data }: { data: AlphaBeta }) {
  if (data.phases.length === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        Appears after the first dbt transform run.
      </p>
    );
  }
  // Prefer the live phase once it has enough days to regress; else show the replay.
  const live = data.phases.find((p) => p.phase === "live" && p.n_days >= 20);
  const shown = live ?? data.phases.find((p) => p.phase === "replay") ?? data.phases[0];

  return (
    <div>
      <p className="mb-3 text-xs" style={{ color: "var(--text-secondary)" }}>
        {shown.phase === "live"
          ? `Live out-of-sample, ${shown.n_days} days.`
          : `In-sample replay, ${shown.n_days} days — the live decomposition appears once it has ~20 days.`}
      </p>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Metric
          label="Beta vs SPY"
          value={formatNumber(shown.beta)}
          hint="market exposure (0 = neutral)"
        />
        <Metric
          label="Alpha (annualized)"
          value={formatSignedPercent(shown.alpha_annualized)}
          color={deltaColor(shown.alpha_annualized)}
          hint="return independent of market"
        />
        <Metric
          label="Information ratio"
          value={formatNumber(shown.information_ratio)}
          color={deltaColor(shown.information_ratio)}
          hint="active return per unit risk"
        />
        <Metric
          label="R²"
          value={formatNumber(shown.r_squared, 3)}
          hint="variance explained by market"
        />
      </div>

      <p
        className="mt-3 rounded-lg px-3 py-2 text-xs"
        style={{ background: "var(--grid)", color: "var(--text-secondary)" }}
      >
        {verdict(shown)} Tracking error {formatPercent(shown.tracking_error, 1)}.
      </p>
    </div>
  );
}
