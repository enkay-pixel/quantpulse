import type { DriftFeature, DriftStatus } from "../api/types";
import { formatDate, formatNumber } from "../lib/format";
import { GLOSSARY } from "../lib/glossary";
import { Term } from "./Term";

/** An input's plain name: "Price vs its 3-month average" rather than ma_ratio_63. */
function inputName(feature: string): string {
  return GLOSSARY[feature]?.label ?? feature;
}

/**
 * The panel's answer, in one sentence: has the market moved away from what the model learned?
 * Names the input nearest the alarm, because "0.191" means nothing until you know the line is 0.20.
 */
export function driftVerdict(drift: DriftStatus): string {
  const total = drift.features.length;
  const over = drift.features.filter((f) => f.drifted).length;
  const closest = drift.features.reduce<DriftFeature | null>(
    (a, b) => (a === null || b.psi > a.psi ? b : a),
    null,
  );
  const line = formatNumber(drift.psi_threshold, 2);
  if (drift.drifted) {
    return (
      `Yes. ${over} of the model's ${total} inputs have moved past the alarm level (${line}) ` +
      `since it was trained, enough to retrain it early.`
    );
  }
  const near =
    closest === null
      ? ""
      : ` The closest is ${inputName(closest.feature).toLowerCase()}, at ${formatNumber(closest.psi, 2)}` +
        (closest.psi >= drift.psi_threshold * 0.75 ? " — near the line, worth watching." : ".");
  return (
    `No. ${over === 0 ? "None" : over} of the model's ${total} inputs ` +
    `${over === 1 ? "has" : "have"} moved past the alarm level (${line}) since it was trained.${near}`
  );
}

/**
 * Has the market changed since the model was trained? Each of the model's inputs, by how far its
 * recent values have shifted from the ones it learned on, with the alarm level marked on every bar.
 */
export function DriftPanel({ drift }: { drift: DriftStatus }) {
  if (!drift.date) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        No drift checks recorded yet.
      </p>
    );
  }
  const scale = Math.max(drift.psi_threshold * 2, ...drift.features.map((f) => f.psi));
  const alarmAt = (drift.psi_threshold / scale) * 100;
  return (
    <div>
      <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
        {driftVerdict(drift)}
      </p>
      <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
        Checked {formatDate(drift.date)}
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
      <div className="mt-3 flex items-end justify-between text-xs" style={{ color: "var(--text-muted)" }}>
        <Term id="feature" />
        <Term id="psi" align="right" />
      </div>
      <ul className="mt-2 space-y-2">
        {drift.features.slice(0, 8).map((f) => (
          <li key={f.feature} className="text-xs" data-testid={`drift-${f.feature}`}>
            <div className="flex items-baseline justify-between gap-2">
              <span style={{ color: "var(--text-secondary)" }} title={GLOSSARY[f.feature]?.meaning}>
                {inputName(f.feature)}
                <span className="ml-1 text-[10px]" style={{ color: "var(--text-muted)" }}>
                  {f.feature}
                </span>
              </span>
              <span className="tabular shrink-0" style={{ color: "var(--text-muted)" }}>
                {formatNumber(f.psi, 2)}
                {f.drifted ? (
                  <span className="ml-1 font-medium" style={{ color: "var(--status-serious)" }}>
                    ⚠ drifted
                  </span>
                ) : null}
              </span>
            </div>
            <div className="relative mt-1 h-2" aria-hidden>
              <span
                className="absolute left-0 top-0 block h-2 rounded-sm"
                style={{ width: `${Math.max(2, (f.psi / scale) * 100)}%`, background: "var(--seq-450)" }}
              />
              <span
                className="absolute top-[-2px] block h-3 w-px"
                style={{ left: `${alarmAt}%`, background: "var(--text-muted)" }}
              />
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
        The thin line on each bar is the alarm level, {formatNumber(drift.psi_threshold, 2)}. The model
        is retrained early when {Math.round(drift.share_threshold * 100)}% of its inputs pass it.
        Showing the {Math.min(8, drift.features.length)} inputs that moved most.
      </p>
    </div>
  );
}
