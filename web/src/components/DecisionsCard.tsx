import type { Decision, DecisionsOut } from "../api/types";
import { formatDate } from "../lib/format";

const STATE_STYLE: Record<string, { label: string; color: string }> = {
  reopened: { label: "reopened", color: "var(--status-serious)" },
  unknown: { label: "can't check here", color: "var(--status-warning)" },
  standing: { label: "standing", color: "var(--status-good)" },
  manual: { label: "watched elsewhere", color: "var(--text-muted)" },
};

/**
 * Each standing decision, the conditions that would reopen it, and whether one has.
 *
 * A decision is only as good as the moment someone notices its premise has changed. The
 * roadmap names that moment for each one — so many live sessions, a Sharpe turning negative, a
 * promotion — and this shows them evaluated on the current record, by the same code the
 * weekday job runs, so the page and the notification agree.
 */
function summary(decisions: Decision[]): string {
  const reopened = decisions.filter((d) => d.state === "reopened").length;
  if (reopened > 0) {
    return (
      `${reopened} of ${decisions.length} standing decisions ${reopened === 1 ? "has" : "have"} ` +
      `reopened: a condition named in advance has been met, so the decision is due another look.`
    );
  }
  return (
    `${decisions.length} standing decisions, none reopened. Each stays until one of its ` +
    `conditions is met — not until a result looks good or bad on the day.`
  );
}

export function DecisionsCard({ data }: { data: DecisionsOut }) {
  const { decisions } = data;
  if (decisions.length === 0) {
    return (
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        No standing decisions recorded.
      </p>
    );
  }
  return (
    <div>
      <p className="mb-3 text-sm" style={{ color: "var(--text-secondary)" }}>
        {summary(decisions)}
      </p>
      <ul className="divide-y" style={{ borderColor: "var(--grid)" }}>
        {decisions.map((d) => {
          const style = STATE_STYLE[d.state] ?? STATE_STYLE.manual;
          return (
            <li key={d.id} className="py-3" data-testid={`decision-${d.id}`}>
              <div className="flex items-baseline justify-between gap-4">
                <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                  {d.title}
                </span>
                <span
                  className="shrink-0 rounded px-2 py-0.5 text-xs font-medium"
                  style={{ color: style.color, border: `1px solid ${style.color}` }}
                >
                  {style.label}
                </span>
              </div>
              <p className="mt-0.5 text-xs" style={{ color: "var(--text-muted)" }}>
                decided {formatDate(d.decided)}
                {d.note ? ` · ${d.note}` : ""}
              </p>
              <ul className="mt-1 space-y-0.5">
                {d.conditions.map((c, i) => (
                  <li
                    key={i}
                    className="text-xs"
                    style={{
                      color:
                        c.state === "fired" ? "var(--status-serious)" : "var(--text-secondary)",
                    }}
                  >
                    {c.state === "fired" ? "▲ " : "· "}
                    {c.detail}
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
