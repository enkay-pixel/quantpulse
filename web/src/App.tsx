import { useState } from "react";

import { DriftPanel } from "./components/DriftPanel";
import { EquityCurveChart } from "./components/EquityCurveChart";
import { PredictionsTable } from "./components/PredictionsTable";
import { PriceChart } from "./components/PriceChart";
import { StatCard } from "./components/StatCard";
import {
  useCurrentModel,
  useDrift,
  useEquityCurve,
  useFreshness,
  useHealth,
  usePredictions,
} from "./hooks/useApi";
import { deltaColor, formatDate, formatNumber, formatPercent, formatSignedPercent } from "./lib/format";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card p-4">
      <h2 className="mb-3 text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
        {title}
      </h2>
      {children}
    </section>
  );
}

export default function App() {
  const health = useHealth();
  const model = useCurrentModel();
  const equity = useEquityCurve();
  const predictions = usePredictions();
  const drift = useDrift();
  const freshness = useFreshness();
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);

  const apiDown = health.isError;

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <header className="mb-6 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold">QuantPulse</h1>
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
            Self-adapting ML investing platform · educational project, not investment advice
          </p>
        </div>
        <div className="text-xs" style={{ color: "var(--text-muted)" }}>
          {apiDown ? (
            <span style={{ color: "var(--status-critical)" }}>⚠ API unreachable</span>
          ) : (
            <>data through {formatDate(freshness.data?.latest_price_date)}</>
          )}
        </div>
      </header>

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label="Total return (paper)"
          value={formatSignedPercent(equity.data?.total_return)}
          valueColor={deltaColor(equity.data?.total_return)}
          sub="simulated long/short book"
        />
        <StatCard
          label="Sharpe"
          value={formatNumber(equity.data?.sharpe)}
          sub="annualized, daily returns"
        />
        <StatCard
          label="Max drawdown"
          value={formatPercent(equity.data?.max_drawdown)}
          sub="paper equity curve"
        />
        <StatCard
          label="Champion model"
          value={model.data?.model_version ? `v${model.data.model_version}` : "—"}
          sub={
            model.data?.metrics?.holdout_ic !== undefined
              ? `holdout IC ${formatNumber(model.data.metrics.holdout_ic, 3)}`
              : "not trained yet"
          }
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4">
          <Section title="Paper portfolio equity">
            {equity.data ? (
              <EquityCurveChart curve={equity.data} />
            ) : (
              <div className="h-64 animate-pulse rounded-lg" style={{ background: "var(--grid)" }} />
            )}
          </Section>
          <Section title={selectedTicker ? `Price — ${selectedTicker}` : "Price"}>
            {selectedTicker ? (
              <PriceChart ticker={selectedTicker} />
            ) : (
              <div
                className="flex h-64 items-center justify-center text-sm"
                style={{ color: "var(--text-muted)" }}
              >
                Select a ticker from the signals table to inspect its price history.
              </div>
            )}
          </Section>
        </div>
        <div className="space-y-4">
          <Section
            title={`Latest signals${predictions.data?.date ? ` — ${formatDate(predictions.data.date)}` : ""}`}
          >
            {predictions.data ? (
              <PredictionsTable
                predictions={predictions.data}
                selectedTicker={selectedTicker}
                onSelect={setSelectedTicker}
              />
            ) : (
              <div className="h-40 animate-pulse rounded-lg" style={{ background: "var(--grid)" }} />
            )}
          </Section>
          <Section title="Feature drift">
            {drift.data ? (
              <DriftPanel drift={drift.data} />
            ) : (
              <div className="h-24 animate-pulse rounded-lg" style={{ background: "var(--grid)" }} />
            )}
          </Section>
        </div>
      </div>
    </div>
  );
}
