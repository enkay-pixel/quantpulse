import type { WatchlistName } from "../api/types";
import { Term } from "./Term";

/** The research watchlist for one market: the names these pages follow beyond the model's
 * universe, each with the reason it is followed (ADR 0007). */
export function WatchlistCard({ names }: { names: WatchlistName[] }) {
  if (names.length === 0) {
    return (
      <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
        No names on the watchlist for this market. Add one to configs/watchlist.yaml, with a
        sentence on why it is followed; it shows here after the next evening run.
      </p>
    );
  }
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
          <th className="px-3 py-2 text-left font-medium">
            <Term id="ticker" />
          </th>
          <th className="px-3 py-2 text-left font-medium">
            <Term id="why" />
          </th>
        </tr>
      </thead>
      <tbody>
        {names.map((n) => (
          <tr
            key={n.ticker}
            className="border-t"
            style={{ borderColor: "var(--grid)" }}
            data-testid={`watch-${n.ticker}`}
          >
            <td className="px-3 py-1.5 font-medium">{n.ticker}</td>
            <td className="px-3 py-1.5" style={{ color: "var(--text-secondary)" }}>
              {n.why}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
