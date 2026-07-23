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

/**
 * Plain-English read of the decomposition. Two rules keep it honest:
 *
 * 1. Alpha and the information ratio can disagree in sign — one is market-adjusted, the
 *    other benchmark-relative — so when they do, say so instead of quoting whichever
 *    flatters. Claiming "it earns positive alpha" next to a negative IR reads as a
 *    verdict the numbers haven't reached.
 * 2. An in-sample window describes a fit, never skill. Label it that way every time.
 */
function verdict(s: AlphaBetaStats, benchmark: string): string {
  const neutral = s.beta !== null && Math.abs(s.beta) < 0.2;
  const alpha = s.alpha_annualized ?? 0;
  const ir = s.information_ratio ?? 0;

  const exposure = neutral
    ? `Beta ${formatNumber(s.beta)} means this book barely moves with the market — which is the design, so comparing its raw return to ${benchmark} would tell you nothing.`
    : `Beta ${formatNumber(s.beta)} means a real share of this return is the market moving, not the signal working.`;

  const te = formatPercent(s.tracking_error, 1);
  let skill: string;
  if (alpha > 0 && ir < 0) {
    skill = `Strip the market out and ${formatSignedPercent(alpha)} a year is left — but against ${te} of tracking error the information ratio is negative (${formatNumber(ir)}), so it still trails the benchmark for the risk it takes. The two measure different things and here they point opposite ways, so neither one settles it.`;
  } else if (alpha > 0) {
    skill = `Strip the market out and ${formatSignedPercent(alpha)} a year is left, and against ${te} of tracking error the information ratio agrees at ${formatNumber(ir)}.`;
  } else {
    skill = `Strip the market out and ${formatSignedPercent(alpha)} a year is left — over this window the signal is not paying for itself (information ratio ${formatNumber(ir)} against ${te} tracking error).`;
  }

  const caveat =
    s.phase === "replay"
      ? " Remember these are in-sample: the model was fitted on this very window, so read them as a description of the fit, not as evidence of skill."
      : "";
  return `${exposure} ${skill}${caveat}`;
}

export function AlphaBetaCard({
  data,
  benchmark = "the index",
}: {
  data: AlphaBeta;
  benchmark?: string;
}) {
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
          label={`Beta vs ${benchmark}`}
          value={formatNumber(shown.beta)}
          hint="how much it moves with the market (0 = not at all)"
        />
        <Metric
          label="Alpha (annualized)"
          value={formatSignedPercent(shown.alpha_annualized)}
          color={deltaColor(shown.alpha_annualized)}
          hint="what's left once market moves are removed"
        />
        <Metric
          label="Information ratio"
          value={formatNumber(shown.information_ratio)}
          color={deltaColor(shown.information_ratio)}
          hint="return vs the benchmark, per unit of risk"
        />
        <Metric
          label="R²"
          value={formatNumber(shown.r_squared, 3)}
          hint="share of its ups and downs the market explains"
        />
      </div>

      <p
        className="mt-3 rounded-lg px-3 py-2 text-xs"
        style={{ background: "var(--grid)", color: "var(--text-secondary)" }}
      >
        {verdict(shown, benchmark)}
      </p>
    </div>
  );
}
