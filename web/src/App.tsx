import { useState } from "react";

import { BenchmarkEquityChart } from "./components/BenchmarkEquityChart";
import { DriftPanel } from "./components/DriftPanel";
import { FreshnessStrip } from "./components/FreshnessStrip";
import { IvSkewChart } from "./components/IvSkewChart";
import { ModelHistoryTable } from "./components/ModelHistoryTable";
import { OptionChainTable } from "./components/OptionChainTable";
import { OptionIdeaCard } from "./components/OptionIdeaCard";
import { PositionsTable } from "./components/PositionsTable";
import { PredictionsTable } from "./components/PredictionsTable";
import { PriceChart } from "./components/PriceChart";
import { QuintileChart } from "./components/QuintileChart";
import { RiskCharts } from "./components/RiskCharts";
import { StatCard } from "./components/StatCard";
import { Tabs } from "./components/Tabs";
import { TrackRecordCard } from "./components/TrackRecordCard";
import {
  useCurrentModel,
  useDrift,
  useEquityCurve,
  useFreshness,
  useHealth,
  useModelHistory,
  useOptionChain,
  useOptionIdea,
  useOptionSummary,
  usePositions,
  usePredictions,
  useQuintiles,
  useRisk,
  useTrackRecord,
} from "./hooks/useApi";
import { useRotatingTicker } from "./hooks/useRotatingTicker";
import { deltaColor, formatDate, formatNumber, formatPercent, formatSignedPercent } from "./lib/format";

const TABS = ["Overview", "Evidence", "Options", "Model & Book"];

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

function Placeholder({ height = "h-64" }: { height?: string }) {
  return <div className={`${height} animate-pulse rounded-lg`} style={{ background: "var(--grid)" }} />;
}

function OverviewTab() {
  const model = useCurrentModel();
  const equity = useEquityCurve();
  const predictions = usePredictions();
  const drift = useDrift();
  const trackRecord = useTrackRecord();

  const tickers = predictions.data?.rows.map((r) => r.ticker) ?? [];
  const rotation = useRotatingTicker(tickers);
  const activeTicker = rotation.ticker;

  return (
    <>
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label="Total return (paper)"
          value={formatSignedPercent(equity.data?.total_return)}
          valueColor={deltaColor(equity.data?.total_return)}
          sub="incl. in-sample replay"
        />
        <StatCard label="Sharpe" value={formatNumber(equity.data?.sharpe)} sub="annualized, daily returns" />
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

      <div className="mb-4">
        {trackRecord.data ? <TrackRecordCard record={trackRecord.data} /> : <Placeholder height="h-24" />}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Section title="Strategy vs SPY buy & hold">
            {equity.data ? <BenchmarkEquityChart curve={equity.data} /> : <Placeholder />}
          </Section>
          <Section title={activeTicker ? `Price — ${activeTicker}` : "Price"}>
            {activeTicker ? (
              <>
                <p className="mb-2 text-xs" style={{ color: "var(--text-muted)" }}>
                  {rotation.isPinned
                    ? "Pinned — rotation resumes in a few minutes."
                    : "Auto-rotating through today's signals · click a ticker to pin it."}
                </p>
                <PriceChart ticker={activeTicker} />
              </>
            ) : (
              <div
                className="flex h-64 items-center justify-center text-sm"
                style={{ color: "var(--text-muted)" }}
              >
                Signals load momentarily…
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
                selectedTicker={activeTicker}
                onSelect={rotation.pin}
              />
            ) : (
              <Placeholder height="h-40" />
            )}
          </Section>
          <Section title="Feature drift">
            {drift.data ? <DriftPanel drift={drift.data} /> : <Placeholder height="h-24" />}
          </Section>
        </div>
      </div>
    </>
  );
}

function EvidenceTab() {
  const quintiles = useQuintiles();
  const risk = useRisk();

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title="Does the ranking work? Signal quintiles vs next-day returns">
        {quintiles.data ? <QuintileChart quintiles={quintiles.data} /> : <Placeholder height="h-56" />}
      </Section>
      <Section title="Risk">
        {risk.data ? <RiskCharts risk={risk.data} /> : <Placeholder height="h-56" />}
      </Section>
    </div>
  );
}

function OptionsTab() {
  const predictions = usePredictions();
  const tickers = predictions.data?.rows.map((r) => r.ticker) ?? [];
  const rotation = useRotatingTicker(tickers);
  const ticker = rotation.ticker;

  const summary = useOptionSummary(ticker);
  const chain = useOptionChain(ticker);
  const idea = useOptionIdea(ticker);

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
          Ticker
          <select
            value={ticker ?? ""}
            onChange={(e) => rotation.pin(e.target.value)}
            className="card px-2 py-1 text-sm"
            style={{ color: "var(--text-primary)" }}
          >
            {tickers.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          {ticker ? (
            <>
              {rotation.isPinned ? "Pinned — rotation resumes shortly." : "Auto-rotating."} Chains
              are daily snapshots (no free history exists, so this dataset builds forward from
              the first run).
            </>
          ) : (
            "Signals load momentarily…"
          )}
        </p>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label="ATM implied vol"
          value={formatPercent(summary.data?.atm_iv)}
          sub={
            summary.data?.atm_days !== null && summary.data?.atm_days !== undefined
              ? `${summary.data.atm_days}d to expiry`
              : "awaiting snapshot"
          }
        />
        <StatCard
          label="Put/call ratio"
          value={formatNumber(summary.data?.put_call_ratio)}
          sub=">1 = more put open interest"
        />
        <StatCard
          label="Contracts captured"
          value={summary.data?.n_contracts ? String(summary.data.n_contracts) : "—"}
          sub={summary.data?.snapshot_date ? `as of ${formatDate(summary.data.snapshot_date)}` : "—"}
        />
        <StatCard
          label="Underlying"
          value={
            summary.data?.underlying_close ? `$${formatNumber(summary.data.underlying_close)}` : "—"
          }
          sub={ticker ?? "—"}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Volatility smile / skew">
          {chain.data ? <IvSkewChart chain={chain.data} /> : <Placeholder height="h-56" />}
        </Section>
        <Section title="If the model's view were expressed in options">
          {idea.data ? <OptionIdeaCard idea={idea.data} /> : <Placeholder height="h-56" />}
        </Section>
        <Section title={`Chain with Greeks${chain.data?.expiry ? ` — ${chain.data.expiry}` : ""}`}>
          {chain.data ? <OptionChainTable chain={chain.data} /> : <Placeholder height="h-40" />}
        </Section>
      </div>
    </>
  );
}

function ModelTab() {
  const history = useModelHistory();
  const positions = usePositions();

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title="Training history — every challenger, promoted or not">
        {history.data ? <ModelHistoryTable runs={history.data} /> : <Placeholder height="h-40" />}
      </Section>
      <Section title="Current paper book">
        {positions.data ? <PositionsTable positions={positions.data} /> : <Placeholder height="h-40" />}
      </Section>
    </div>
  );
}

export default function App() {
  const health = useHealth();
  const freshness = useFreshness();
  const [tab, setTab] = useState(TABS[0]);

  const apiDown = health.isError;

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
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

      {freshness.data ? (
        <div className="mb-4">
          <FreshnessStrip freshness={freshness.data} />
        </div>
      ) : null}

      <div className="mb-4">
        <Tabs tabs={TABS} active={tab} onSelect={setTab} />
      </div>

      {tab === "Overview" ? <OverviewTab /> : null}
      {tab === "Evidence" ? <EvidenceTab /> : null}
      {tab === "Options" ? <OptionsTab /> : null}
      {tab === "Model & Book" ? <ModelTab /> : null}
    </div>
  );
}
