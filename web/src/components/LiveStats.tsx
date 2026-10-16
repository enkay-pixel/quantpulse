import type { PhaseStats } from "../api/types";
import { deltaColor, formatNumber, formatPercent, formatSignedPercent } from "../lib/format";
import { MIN_DAYS_FOR_RATIOS } from "../lib/thresholds";
import { StatCard } from "./StatCard";

/**
 * The overview's headline row, reporting the live phase only.
 *
 * A paper return that includes the in-sample replay is the largest number on the page and
 * the least meaningful one, so it is deliberately absent here: leading with it invites a fit
 * to be read as a result. When no live phase exists the cards stay blank rather than falling
 * back to the replay, because a blank says "not yet" and a replay figure says "this is how
 * it performs".
 *
 * "Not yet" is only said when the record loaded and has no live phase. A request that failed or
 * is still in flight says so instead: reporting an unreachable API as an empty record is a
 * failure dressed as a fact.
 */
export type LoadState = "loading" | "error" | "ready";

export function emptyReason(state: LoadState, ready: string): string {
  if (state === "error") return "couldn't load: API unreachable";
  if (state === "loading") return "loading…";
  return ready;
}

export function LiveStats({ live, state = "ready" }: { live?: PhaseStats; state?: LoadState }) {
  const ratiosPublished = (live?.n_days ?? 0) >= MIN_DAYS_FOR_RATIOS;
  const none = emptyReason(state, "no live record yet");
  return (
    <>
      <StatCard
        label="Live return"
        value={live ? formatSignedPercent(live.total_return) : "—"}
        valueColor={live ? deltaColor(live.total_return) : undefined}
        sub={live ? `out-of-sample · ${live.n_days} sessions` : none}
      />
      <StatCard
        label="Live Sharpe"
        value={live && ratiosPublished ? formatNumber(live.sharpe) : "—"}
        sub={
          !live
            ? none
            : ratiosPublished
              ? "annualized, out-of-sample"
              : `withheld under ${MIN_DAYS_FOR_RATIOS} sessions`
        }
      />
      <StatCard
        label="Live max drawdown"
        value={live ? formatPercent(live.max_drawdown) : "—"}
        sub={live ? "out-of-sample" : none}
      />
    </>
  );
}
