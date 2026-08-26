import type { ChampionRecord, ChampionRecordOut } from "../api/types";
import {
  deltaColor,
  formatDate,
  formatNumber,
  formatSignedPercent,
} from "../lib/format";
import { MIN_DAYS_FOR_RATIOS } from "../lib/thresholds";

/**
 * What each deployed model earned, apart from what the market earned.
 *
 * The live track record pools every champion that has held the alias. That is the right
 * question for the market and the wrong one for a model: after a demotion the headline
 * belongs to the model that was withdrawn, and stays that way for months — 25 of the NYSE's
 * first 26 live sessions were a champion demoted three days before this card existed.
 *
 * A row below MIN_DAYS_FOR_RATIOS shows its return and its day count and nothing else. A
 * champion with one live day has a 100% win rate and no Sharpe at all, and printing either
 * would say something the sample cannot.
 */
function verdict(rows: ChampionRecord[]): string {
  const current = rows.find((r) => r.is_current);
  if (!current) return "No model has scored a live session yet.";
  if (current.n_days < MIN_DAYS_FOR_RATIOS) {
    const prior = rows
      .filter((r) => !r.is_current)
      .reduce((a, r) => a + r.n_days, 0);
    const carried =
      prior > 0
        ? ` The headline live figures are still ${prior} session${prior === 1 ? "" : "s"} of earlier champions.`
        : "";
    return (
      `v${current.model_version} has ${current.n_days} live session` +
      `${current.n_days === 1 ? "" : "s"} — too few to read as performance.${carried}`
    );
  }
  return (
    `v${current.model_version} has ${current.n_days} live sessions, enough for ratios but not ` +
    `for confidence: a month of daily returns still leaves a wide error on anything annualized.`
  );
}

export function ChampionRecordCard({ data }: { data: ChampionRecordOut }) {
  const rows = data.champions;
  if (rows.length === 0) {
    return (
      <div className="card p-4">
        <h2 className="mb-2 text-sm font-semibold">Live record by champion</h2>
        <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
          Appears once a champion has scored a live session.
        </p>
      </div>
    );
  }

  return (
    <div className="card p-4">
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold">Live record by champion</h2>
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          out-of-sample only
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs" style={{ color: "var(--text-muted)" }}>
              <th className="py-1 text-left font-normal">Model</th>
              <th className="py-1 text-left font-normal">Window</th>
              <th className="py-1 text-right font-normal">Days</th>
              <th className="py-1 text-right font-normal">Return</th>
              <th className="py-1 text-right font-normal">Sharpe</th>
              <th className="py-1 text-right font-normal">Win rate</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const enough = r.n_days >= MIN_DAYS_FOR_RATIOS;
              return (
                <tr
                  key={r.model_version}
                  style={{ borderTop: "1px solid var(--grid)" }}
                >
                  <td className="py-1.5">
                    <span className="font-semibold">v{r.model_version}</span>
                    {r.is_current ? (
                      <span
                        className="ml-1.5 text-xs"
                        style={{ color: "var(--text-muted)" }}
                      >
                        current
                      </span>
                    ) : (
                      <span
                        className="ml-1.5 text-xs"
                        style={{ color: "var(--text-muted)" }}
                      >
                        withdrawn
                      </span>
                    )}
                  </td>
                  <td
                    className="py-1.5 text-xs"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    {formatDate(r.start_date)} – {formatDate(r.end_date)}
                  </td>
                  <td className="tabular py-1.5 text-right">{r.n_days}</td>
                  {/* Return and day count are honest at any sample size; the ratios are not,
                      so they are withheld rather than shown small and precise-looking. */}
                  <td
                    className="tabular py-1.5 text-right"
                    style={{
                      color: enough ? deltaColor(r.total_return) : undefined,
                    }}
                  >
                    {formatSignedPercent(r.total_return)}
                  </td>
                  <td className="tabular py-1.5 text-right">
                    {enough ? formatNumber(r.sharpe) : "—"}
                  </td>
                  <td className="tabular py-1.5 text-right">
                    {enough && r.win_rate !== null
                      ? `${(r.win_rate * 100).toFixed(1)}%`
                      : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p
        className="mt-3 rounded-lg px-3 py-2 text-xs"
        style={{ background: "var(--grid)", color: "var(--text-secondary)" }}
      >
        {verdict(rows)}
      </p>
    </div>
  );
}
