import type { OptionIdea } from "../api/types";
import { formatDate, formatNumber, formatSignedPercent } from "../lib/format";

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>
        {label}
      </div>
      <div className="tabular text-sm font-semibold">{value}</div>
    </div>
  );
}

export function OptionIdeaCard({ idea }: { idea: OptionIdea }) {
  const disclaimer = (
    <p
      className="mt-3 rounded-lg px-3 py-2 text-xs"
      style={{ background: "var(--grid)", color: "var(--text-secondary)" }}
    >
      ⚠ Hypothetical illustration of the model's directional view — <strong>not advice</strong>,
      not a recommendation, and not a trade. Options are leveraged and can lose 100% of their
      value. Prices are stale snapshots and ignore commissions, spreads, and assignment risk.
    </p>
  );

  if (!idea.available) {
    return (
      <div>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          {idea.signal !== null
            ? `Signal ${formatSignedPercent(idea.signal)} is too weak to express — no structure shown.`
            : "No structure available yet (needs both a live signal and an option snapshot)."}
        </p>
        {disclaimer}
      </div>
    );
  }

  const bullish = idea.direction === "bullish";
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span
          className="text-sm font-semibold"
          style={{ color: bullish ? "var(--delta-up)" : "var(--delta-down)" }}
        >
          {idea.structure}
        </span>
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          expiry {formatDate(idea.expiry)}
        </span>
      </div>

      <p className="mt-1 text-xs" style={{ color: "var(--text-secondary)" }}>
        {idea.rationale}
      </p>

      <ul className="mt-3 space-y-1">
        {idea.legs.map((leg) => (
          <li key={`${leg.action}-${leg.strike}`} className="tabular text-sm">
            <span
              className="mr-2 text-xs font-semibold uppercase"
              style={{ color: leg.action === "buy" ? "var(--delta-up)" : "var(--delta-down)" }}
            >
              {leg.action}
            </span>
            ${formatNumber(leg.strike, 0)} {leg.option_type} @ ${formatNumber(leg.price)}
          </li>
        ))}
      </ul>

      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric label="Net debit" value={`$${formatNumber(idea.net_debit)}`} />
        <Metric label="Max profit" value={idea.max_profit !== null ? `$${formatNumber(idea.max_profit)}` : "—"} />
        <Metric label="Max loss" value={`$${formatNumber(idea.max_loss)}`} />
        <Metric label="Breakeven" value={`$${formatNumber(idea.breakeven)}`} />
      </div>

      {disclaimer}
    </div>
  );
}
