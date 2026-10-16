import { useState } from "react";
import type { ReactNode } from "react";

import { AlphaBetaCard } from "./components/AlphaBetaCard";
import { AttentionChart } from "./components/AttentionChart";
import { AttentionTable } from "./components/AttentionTable";
import { ChampionRecordCard } from "./components/ChampionRecordCard";
import { DecisionsCard } from "./components/DecisionsCard";
import { BenchmarkEquityChart } from "./components/BenchmarkEquityChart";
import { BookComparisonCard } from "./components/BookComparisonCard";
import { DriftPanel } from "./components/DriftPanel";
import { FindingsList } from "./components/FindingsList";
import { ForwardVrpChart } from "./components/ForwardVrpChart";
import { FreshnessStrip } from "./components/FreshnessStrip";
import { GammaProfileChart } from "./components/GammaProfileChart";
import { IvSkewChart } from "./components/IvSkewChart";
import { IvSurfaceChart } from "./components/IvSurfaceChart";
import { ModelHistoryTable } from "./components/ModelHistoryTable";
import { OptionChainTable } from "./components/OptionChainTable";
import { OptionIdeaCard } from "./components/OptionIdeaCard";
import { PositioningTable } from "./components/PositioningTable";
import { PositionsTable } from "./components/PositionsTable";
import { PredictionsTable } from "./components/PredictionsTable";
import { PriceChart } from "./components/PriceChart";
import { QuintileChart } from "./components/QuintileChart";
import { RiskCharts } from "./components/RiskCharts";
import { LiveStats, emptyReason } from "./components/LiveStats";
import { StatCard } from "./components/StatCard";
import { Tabs } from "./components/Tabs";
import { TrackRecordCard } from "./components/TrackRecordCard";
import {
  useAlphaBeta,
  useAttention,
  useAttentionHistory,
  useChampions,
  useBooks,
  useCurrentModel,
  useDecisions,
  useDrift,
  useEquityCurve,
  useFindings,
  useForwardVrp,
  useFreshness,
  useExchanges,
  useGammaProfile,
  useHealth,
  useModelHistory,
  useOptionChain,
  useIvSurface,
  useOptionIdea,
  useOptionSummary,
  usePositioning,
  usePositions,
  usePredictions,
  useQuintiles,
  useRisk,
  useTrackRecord,
} from "./hooks/useApi";
import { ExchangePicker } from "./components/ExchangePicker";
import { useExchange } from "./hooks/useExchange";
import { useHashTab } from "./hooks/useHashTab";
import { useRotatingTicker } from "./hooks/useRotatingTicker";
import { formatDate, formatNumber, formatPercent } from "./lib/format";
import { TABS, visibleTabs } from "./lib/tabs";


function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card p-4">
      <h2
        className="mb-3 text-sm font-semibold"
        style={{ color: "var(--text-primary)" }}
      >
        {title}
      </h2>
      {children}
    </section>
  );
}

function Placeholder({ height = "h-64" }: { height?: string }) {
  return (
    <div
      className={`${height} animate-pulse rounded-lg`}
      style={{ background: "var(--grid)" }}
    />
  );
}

function OverviewTab({ exchange }: { exchange: string }) {
  const model = useCurrentModel(exchange);
  const equity = useEquityCurve(exchange);
  const predictions = usePredictions(exchange);
  const drift = useDrift(exchange);
  const trackRecord = useTrackRecord(exchange);

  const tickers = predictions.data?.rows.map((r) => r.ticker) ?? [];
  const rotation = useRotatingTicker(tickers);
  const activeTicker = rotation.ticker;

  // The headline row reports the live phase, not the replay. A paper return that includes
  // the in-sample replay is the largest number on the page and the least meaningful one;
  // leading with it invites the reader to treat a fit as a result.
  const live = trackRecord.data?.phases.find((p) => p.phase === "live");

  return (
    <>
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <LiveStats
          live={live}
          state={trackRecord.isError ? "error" : trackRecord.data ? "ready" : "loading"}
        />
        <StatCard
          label="Champion model"
          value={
            model.data?.model_version ? `v${model.data.model_version}` : "—"
          }
          sub={
            model.data?.metrics?.holdout_ic !== undefined
              ? `holdout IC ${formatNumber(model.data.metrics.holdout_ic, 3)}`
              : emptyReason(
                  model.isError ? "error" : model.data ? "ready" : "loading",
                  "not trained yet",
                )
          }
        />
      </div>

      <div className="mb-4">
        {trackRecord.data ? (
          <TrackRecordCard record={trackRecord.data} />
        ) : (
          <Placeholder height="h-24" />
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Section title="Paper equity vs benchmark buy & hold">
            {equity.data ? (
              <BenchmarkEquityChart curve={equity.data} />
            ) : (
              <Placeholder />
            )}
          </Section>
          <Section title={activeTicker ? `Price — ${activeTicker}` : "Price"}>
            {activeTicker ? (
              <>
                <p
                  className="mb-2 text-xs"
                  style={{ color: "var(--text-muted)" }}
                >
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
            {drift.data ? (
              <DriftPanel drift={drift.data} />
            ) : (
              <Placeholder height="h-24" />
            )}
          </Section>
        </div>
      </div>
    </>
  );
}

function EvidenceTab({
  exchange,
  benchmark,
}: {
  exchange: string;
  benchmark?: string;
}) {
  const quintiles = useQuintiles(exchange);
  const risk = useRisk(exchange);
  const alphaBeta = useAlphaBeta(exchange);
  const champions = useChampions(exchange);
  const books = useBooks(exchange);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="lg:col-span-2">
        <Section title="How much of this is the market, and how much is the signal?">
          {champions.data ? <ChampionRecordCard data={champions.data} /> : null}
          {alphaBeta.data ? (
            <AlphaBetaCard data={alphaBeta.data} benchmark={benchmark} />
          ) : (
            <Placeholder height="h-32" />
          )}
        </Section>
      </div>
      <div className="lg:col-span-2">
        <Section title="What does trading more often cost?">
          {books.data ? (
            <BookComparisonCard data={books.data} />
          ) : (
            <Placeholder height="h-32" />
          )}
        </Section>
      </div>
      <Section title="Does the ranking work? Signal quintiles vs next-day returns">
        {quintiles.data ? (
          <QuintileChart quintiles={quintiles.data} />
        ) : (
          <Placeholder height="h-56" />
        )}
      </Section>
      <Section title="Risk">
        {risk.data ? (
          <RiskCharts risk={risk.data} />
        ) : (
          <Placeholder height="h-56" />
        )}
      </Section>
    </div>
  );
}

function OptionsTab({ exchange }: { exchange: string }) {
  const predictions = usePredictions(exchange);
  const tickers = predictions.data?.rows.map((r) => r.ticker) ?? [];
  const rotation = useRotatingTicker(tickers);
  const ticker = rotation.ticker;

  const summary = useOptionSummary(ticker);
  const chain = useOptionChain(ticker);
  const surface = useIvSurface(ticker);
  const idea = useOptionIdea(ticker);
  const forwardVrp = useForwardVrp(exchange);

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <label
          className="flex items-center gap-2 text-xs"
          style={{ color: "var(--text-muted)" }}
        >
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
              {rotation.isPinned
                ? "Pinned — rotation resumes shortly."
                : "Auto-rotating."}{" "}
              Chains are daily snapshots (no free history exists, so this
              dataset builds forward from the first run).
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
            summary.data?.atm_days !== null &&
            summary.data?.atm_days !== undefined
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
          value={
            summary.data?.n_contracts ? String(summary.data.n_contracts) : "—"
          }
          sub={
            summary.data?.snapshot_date
              ? `as of ${formatDate(summary.data.snapshot_date)}`
              : "—"
          }
        />
        <StatCard
          label="Underlying"
          value={
            summary.data?.underlying_close
              ? `$${formatNumber(summary.data.underlying_close)}`
              : "—"
          }
          sub={ticker ?? "—"}
        />
      </div>

      <Section title="Term structure and IV history">
        {surface.data ? (
          <IvSurfaceChart data={surface.data} />
        ) : (
          <Placeholder height="h-56" />
        )}
      </Section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Volatility smile / skew">
          {chain.data ? (
            <IvSkewChart chain={chain.data} />
          ) : (
            <Placeholder height="h-56" />
          )}
        </Section>
        <Section title="If the model's view were expressed in options">
          {idea.data ? (
            <OptionIdeaCard idea={idea.data} />
          ) : (
            <Placeholder height="h-56" />
          )}
        </Section>
        <Section
          title={`Chain with Greeks${chain.data?.expiry ? ` — ${chain.data.expiry}` : ""}`}
        >
          {chain.data ? (
            <OptionChainTable chain={chain.data} />
          ) : (
            <Placeholder height="h-40" />
          )}
        </Section>
      </div>

      <div className="mt-4">
        <Section title="Did options price more volatility than then arrived?">
          {forwardVrp.data ? (
            <ForwardVrpChart data={forwardVrp.data} />
          ) : (
            <Placeholder height="h-56" />
          )}
        </Section>
      </div>
    </>
  );
}

// The research branch's positioning page (ADR 0007). Squeeze fuel needs short interest and
// option chains, which only the NYSE has free; attention covers both markets. It assesses; it
// does not advise.
function SqueezeSections({ exchange }: { exchange: string }) {
  const positioning = usePositioning(exchange);
  const [picked, setPicked] = useState<string | null>(null);
  // Until a row is picked, show the stock with the largest call exposure against its volume.
  const top =
    positioning.data?.rows
      .filter((r) => r.asset_type === "stock" && r.call_gamma_share_of_adv !== null)
      .sort((a, b) => (b.call_gamma_share_of_adv ?? 0) - (a.call_gamma_share_of_adv ?? 0))[0]
      ?.ticker ?? null;
  const selected = picked ?? top;
  const profile = useGammaProfile(selected);
  return (
    <>
      <Section title="Where would a squeeze have fuel?">
        {positioning.data ? (
          <PositioningTable data={positioning.data} selected={selected} onSelect={setPicked} />
        ) : (
          <Placeholder height="h-96" />
        )}
      </Section>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title={selected ? `Where the hedging sits — ${selected}` : "Where the hedging sits"}>
          {profile.data ? <GammaProfileChart data={profile.data} /> : <Placeholder height="h-64" />}
        </Section>
        <Section title="How to read this">
          <div className="space-y-2 text-sm" style={{ color: "var(--text-secondary)" }}>
            <p>
              <strong>Short interest</strong> is shares sold short and not yet bought back. Short
              sellers lose as the price rises, and enough of them buying back at once pushes it
              higher. Days to cover is how many days of normal volume that buying would take.
              Exchanges publish it monthly, and it reaches this page a week or two after it
              settles.
            </p>
            <p>
              <strong>Option hedging.</strong> A dealer who sells a call buys some stock to
              stay neutral, and buys more as the price rises toward the strike. The dollar figures
              are what that would take per 1% move <em>if dealers had sold every listed contract</em>.
              They are an upper bound, because many calls are sold by customers rather than
              dealers, and public data does not show which side anyone holds. For puts, the same
              mechanics sell into a fall.
            </p>
            <p>
              This measures fuel, not timing: a loaded name can stay loaded for months. It is an
              assessment of the evidence, not a recommendation to buy or sell anything. Take
              anything you would act on to a licensed advisor who knows your circumstances.
            </p>
          </div>
        </Section>
      </div>
    </>
  );
}

function AttentionSections({ exchange }: { exchange: string }) {
  const attention = useAttention(exchange);
  const [picked, setPicked] = useState<string | null>(null);
  const top =
    attention.data?.rows
      .filter((r) => r.attention_ratio !== null)
      .sort((a, b) => (b.attention_ratio ?? 0) - (a.attention_ratio ?? 0))[0]?.ticker ?? null;
  const selected = picked ?? top;
  const history = useAttentionHistory(selected);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title="Who is drawing attention?">
        {attention.data ? (
          <AttentionTable data={attention.data} selected={selected} onSelect={setPicked} />
        ) : (
          <Placeholder height="h-80" />
        )}
      </Section>
      <Section title={selected ? `Attention over the past year — ${selected}` : "Attention over the past year"}>
        {history.data ? <AttentionChart data={history.data} /> : <Placeholder height="h-64" />}
      </Section>
    </div>
  );
}

function PositioningTab({ exchange, hasOptions }: { exchange: string; hasOptions: boolean }) {
  return (
    <div className="grid gap-4">
      {hasOptions ? (
        <SqueezeSections exchange={exchange} />
      ) : (
        <Section title="Where would a squeeze have fuel?">
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            Short interest and option chains are not published free for this market, so the
            squeeze measures the NYSE page shows cannot be computed here. Attention can, below. It
            is an assessment of the evidence, not a recommendation to buy or sell anything.
          </p>
        </Section>
      )}
      <AttentionSections exchange={exchange} />
    </div>
  );
}

// Project-wide rather than per market: the findings and decisions span both, so this tab
// ignores the market picker.
function ResearchTab() {
  const decisions = useDecisions();
  const findings = useFindings();
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title="What would change a standing decision?">
        {decisions.data ? (
          <DecisionsCard data={decisions.data} />
        ) : (
          <Placeholder height="h-56" />
        )}
      </Section>
      <Section title="What has been measured, and what came back">
        {findings.data ? (
          <FindingsList data={findings.data} />
        ) : (
          <Placeholder height="h-56" />
        )}
      </Section>
    </div>
  );
}

function ModelTab({ exchange }: { exchange: string }) {
  const history = useModelHistory(exchange);
  const positions = usePositions(exchange);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title="Training history — every challenger, promoted or not">
        {history.data ? (
          <ModelHistoryTable runs={history.data} />
        ) : (
          <Placeholder height="h-40" />
        )}
      </Section>
      <Section title="Current paper book">
        {positions.data ? (
          <PositionsTable positions={positions.data} />
        ) : (
          <Placeholder height="h-40" />
        )}
      </Section>
    </div>
  );
}

export default function App() {
  const [exchange, setExchange] = useExchange();
  const exchanges = useExchanges();
  const health = useHealth();
  const freshness = useFreshness(exchange);
  const [tab, setTab] = useHashTab(TABS);

  const apiDown = health.isError;
  const market = exchanges.data?.find((e) => e.code === exchange);
  const tabs = visibleTabs(market?.has_options);

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold">QuantPulse</h1>
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
            Self-adapting ML investing platform · educational project, not
            investment advice
          </p>
        </div>
        <div
          className="flex items-center gap-3 text-xs"
          style={{ color: "var(--text-muted)" }}
        >
          <ExchangePicker
            exchanges={exchanges.data ?? []}
            selected={exchange}
            onSelect={setExchange}
          />
          {apiDown ? (
            <span style={{ color: "var(--status-critical)" }}>
              ⚠ API unreachable
            </span>
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
        <Tabs tabs={tabs} active={tab} onSelect={setTab} />
      </div>

      {tab === "Overview" ? <OverviewTab exchange={exchange} /> : null}
      {tab === "Evidence" ? (
        <EvidenceTab exchange={exchange} benchmark={market?.benchmark} />
      ) : null}
      {tab === "Options" && tabs.includes("Options") ? (
        <OptionsTab exchange={exchange} />
      ) : null}
      {tab === "Positioning" && tabs.includes("Positioning") ? (
        <PositioningTab exchange={exchange} hasOptions={market?.has_options ?? true} />
      ) : null}
      {tab === "Model & Book" ? <ModelTab exchange={exchange} /> : null}
      {tab === "Research" ? <ResearchTab /> : null}
    </div>
  );
}
