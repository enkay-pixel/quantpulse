import { useState } from "react";
import type { ReactNode } from "react";

import { AlphaBetaCard } from "./components/AlphaBetaCard";
import { AdvisorBrief } from "./components/AdvisorBrief";
import { AttentionChart } from "./components/AttentionChart";
import { AttentionTable } from "./components/AttentionTable";
import { ChampionRecordCard } from "./components/ChampionRecordCard";
import { DecisionsCard } from "./components/DecisionsCard";
import { BenchmarkEquityChart } from "./components/BenchmarkEquityChart";
import { BookComparisonCard } from "./components/BookComparisonCard";
import { DriftPanel } from "./components/DriftPanel";
import { FindingsList } from "./components/FindingsList";
import { ForwardVrpChart } from "./components/ForwardVrpChart";
import { FundamentalsTable } from "./components/FundamentalsTable";
import { FreshnessStrip } from "./components/FreshnessStrip";
import { GammaProfileChart } from "./components/GammaProfileChart";
import { IvSkewChart } from "./components/IvSkewChart";
import { IvSurfaceChart } from "./components/IvSurfaceChart";
import { ModelHistoryTable } from "./components/ModelHistoryTable";
import { OptionChainTable } from "./components/OptionChainTable";
import { OwnershipDetail } from "./components/OwnershipDetail";
import { OwnershipTable } from "./components/OwnershipTable";
import { OptionBookCard } from "./components/OptionBookCard";
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
import { WatchlistCard } from "./components/WatchlistCard";
import {
  useAlphaBeta,
  useAttention,
  useAttentionHistory,
  useBrief,
  useBriefIndex,
  useChampions,
  useBooks,
  useCurrentModel,
  useDecisions,
  useDrift,
  useEquityCurve,
  useFindings,
  useForwardVrp,
  useFreshness,
  useFundamentals,
  useExchanges,
  useGammaProfile,
  useHealth,
  useModelHistory,
  useOptionBook,
  useOptionChain,
  useIvSurface,
  useOptionIdea,
  useOptionSummary,
  useOwnership,
  useOwnershipDetail,
  usePositioning,
  usePositions,
  usePredictions,
  useQuintiles,
  useRisk,
  useTrackRecord,
  useWatchlist,
} from "./hooks/useApi";
import { ExchangePicker } from "./components/ExchangePicker";
import { useExchange } from "./hooks/useExchange";
import { useHashTab } from "./hooks/useHashTab";
import { useRotatingTicker } from "./hooks/useRotatingTicker";
import { formatDate, formatNumber, formatPercent } from "./lib/format";
import { TABS, visibleTabs } from "./lib/tabs";
import { Term } from "./components/Term";


/** A dashboard panel. Every panel says, in one plain sentence under its title, what it shows and
 * how to read it — so the page can be read without a guide. A test holds every panel to that. */
function Section({
  title,
  explain,
  children,
}: {
  title: string;
  explain: string;
  children: ReactNode;
}) {
  return (
    <section className="card p-4">
      <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
        {title}
      </h2>
      <p className="mb-3 mt-0.5 text-xs" style={{ color: "var(--text-muted)" }}>
        {explain}
      </p>
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

function OverviewTab({ exchange, benchmark }: { exchange: string; benchmark?: string }) {
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
          label={<Term id="model_version" label="Champion model" />}
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
          <Section
            title="How the paper book has done, against simply holding the index"
            explain="What 1.0 put into the model's paper book became over time, beside buying the market's index fund and holding it. The dashed stretch is a replay from before the model went live; judge only the live part."
          >
            {equity.data ? (
              <BenchmarkEquityChart curve={equity.data} benchmark={benchmark} />
            ) : (
              <Placeholder />
            )}
          </Section>
          <Section
            title={activeTicker ? `Price — ${activeTicker}` : "Price"}
            explain="The stock's closing price, with the model's daily forecast for it underneath."
          >
            {activeTicker ? (
              <>
                <p
                  className="mb-2 text-xs"
                  style={{ color: "var(--text-muted)" }}
                >
                  {rotation.isPinned
                    ? "Pinned — rotation resumes in a few minutes."
                    : "Cycling through today's strongest forecasts — select a stock in the list to keep it here."}
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
            title={`The model's forecasts${predictions.data?.date ? ` — ${formatDate(predictions.data.date)}` : ""}`}
            explain="Each stock's predicted return over the next 21 trading days (about a month), strongest first. The paper book buys the strongest group and sells the weakest short. Research output, not advice — select a row to see its price."
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
          <Section
            title="Has the market changed since the model was trained?"
            explain="Each input the model reads, by how far its recent values have shifted from the values it learned on."
          >
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
        <Section
          title="How much of this is the market, and how much is the signal?"
          explain="Splits the book's return into the part that came from the market moving and the part left over, which is what the model's forecasts earned."
        >
          {champions.data ? <ChampionRecordCard data={champions.data} /> : null}
          {alphaBeta.data ? (
            <AlphaBetaCard data={alphaBeta.data} benchmark={benchmark} />
          ) : (
            <Placeholder height="h-32" />
          )}
        </Section>
      </div>
      <div className="lg:col-span-2">
        <Section
          title="What does trading more often cost?"
          explain="The same forecasts traded several ways. Each version changes one thing from the daily book, so the gap between them is the cost or benefit of that one change."
        >
          {books.data ? (
            <BookComparisonCard data={books.data} />
          ) : (
            <Placeholder height="h-32" />
          )}
        </Section>
      </div>
      <Section
        title="Does the ranking work?"
        explain="Each day the stocks are split into five groups by forecast. If the ranking works, group 1 (the strongest forecasts) does best the next day and group 5 worst."
      >
        {quintiles.data ? (
          <QuintileChart quintiles={quintiles.data} />
        ) : (
          <Placeholder height="h-56" />
        )}
      </Section>
      <Section
        title="How bumpy has it been?"
        explain="How far the book fell from its highs, and its return per unit of risk over rolling three-month windows."
      >
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
  const optionBook = useOptionBook(exchange);
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
            "Forecasts load in a moment…"
          )}
        </p>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label={<Term id="atm_iv" />}
          value={formatPercent(summary.data?.atm_iv)}
          sub={
            summary.data?.atm_days !== null &&
            summary.data?.atm_days !== undefined
              ? `${summary.data.atm_days}d to expiry`
              : "awaiting snapshot"
          }
        />
        <StatCard
          label={<Term id="put_call_ratio" />}
          value={formatNumber(summary.data?.put_call_ratio)}
          sub=">1 = more put open interest"
        />
        <StatCard
          label={<Term id="n_contracts" />}
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
          label={<Term id="spot" />}
          value={
            summary.data?.underlying_close
              ? `$${formatNumber(summary.data.underlying_close)}`
              : "—"
          }
          sub={ticker ?? "—"}
        />
      </div>

      <Section
        title="How much movement do options expect?"
        explain="Implied volatility — the movement option prices assume — by how far away the expiry is, and how it has changed day to day."
      >
        {surface.data ? (
          <IvSurfaceChart data={surface.data} />
        ) : (
          <Placeholder height="h-56" />
        )}
      </Section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section
          title="Does the expected movement differ by strike?"
          explain="Implied volatility at each strike price for one expiry. A smile or a tilt shows where the market prices bigger moves — usually falls more than rises."
        >
          {chain.data ? (
            <IvSkewChart chain={chain.data} />
          ) : (
            <Placeholder height="h-56" />
          )}
        </Section>
        <Section
          title="If the model's view were expressed in options"
          explain="An illustration of how the model's forecast for this stock could be held as a limited-risk option spread. Not a recommendation."
        >
          {idea.data ? (
            <OptionIdeaCard idea={idea.data} />
          ) : (
            <Placeholder height="h-56" />
          )}
        </Section>
        <Section
          title={`The option contracts${chain.data?.expiry ? ` — expiring ${chain.data.expiry}` : ""}`}
          explain="Every captured contract for one expiry: its price, the movement it assumes, and how its price responds to the stock. Hover a column name for what it means."
        >
          {chain.data ? (
            <OptionChainTable chain={chain.data} />
          ) : (
            <Placeholder height="h-40" />
          )}
        </Section>
      </div>

      <div className="mt-4">
        <Section
          title="Did options price more movement than then arrived?"
          explain="What options assumed about the next month's movement, beside the movement that then happened. A day appears once its month has passed."
        >
          {forwardVrp.data ? (
            <ForwardVrpChart data={forwardVrp.data} />
          ) : (
            <Placeholder height="h-56" />
          )}
        </Section>
      </div>
      <Section
        title="What if the forecasts were held as options?"
        explain="The model's forecasts held through limited-risk option spreads instead of shares — bull call spreads on the stocks it favours, bear put spreads on the ones it doesn't — priced every evening at what trading would actually get. Paper only, not a recommendation."
      >
        {optionBook.data ? <OptionBookCard data={optionBook.data} /> : <Placeholder height="h-56" />}
      </Section>
    </>
  );
}

// The research branch's positioning page (ADR 0007). Squeeze fuel needs short interest and
// option chains, which only the NYSE has free; attention covers every market. It assesses; it
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
      <Section
        title="Where would a squeeze have fuel?"
        explain="Two things that can force buying when a price rises: short sellers buying back, and dealers hedging the calls they sold. Bigger numbers mean more fuel, not that a squeeze is coming."
      >
        {positioning.data ? (
          <PositioningTable data={positioning.data} selected={selected} onSelect={setPicked} />
        ) : (
          <Placeholder height="h-96" />
        )}
      </Section>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section
          title={selected ? `Where the hedging sits — ${selected}` : "Where the hedging sits"}
          explain="How much stock a dealer would trade per 1% move at each strike, calls above the axis and puts below. Exposure piled just above the price is the shape that fed GameStop's squeeze."
        >
          {profile.data ? <GammaProfileChart data={profile.data} /> : <Placeholder height="h-64" />}
        </Section>
        <Section
          title="How to read this"
          explain="What each measure on this page means, and what it cannot tell you."
        >
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
      <Section
        title="Who is drawing attention?"
        explain="How often each company's Wikipedia article was read this past week, against its usual level — a free measure of public attention."
      >
        {attention.data ? (
          <AttentionTable data={attention.data} selected={selected} onSelect={setPicked} />
        ) : (
          <Placeholder height="h-80" />
        )}
      </Section>
      <Section
        title={selected ? `Attention over the past year — ${selected}` : "Attention over the past year"}
        explain="Daily readers of the company's Wikipedia article, averaged over a week, against its usual level."
      >
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
        <Section
          title="Where would a squeeze have fuel?"
          explain="On the NYSE page this measures short sellers and option hedging; this market publishes neither free."
        >
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            Short interest and option chains are not published free for this market, so the
            squeeze measures the NYSE page shows cannot be computed here. Attention can, below. It
            is an assessment of the evidence, not a recommendation to buy or sell anything.
          </p>
        </Section>
      )}
      {hasOptions ? <OwnershipSections exchange={exchange} /> : null}
      <AttentionSections exchange={exchange} />
      <WatchlistSection exchange={exchange} />
    </div>
  );
}

// Ownership filings are a US requirement: a company listed elsewhere files with no US regulator,
// so the section shows only where the squeeze sections do.
function OwnershipSections({ exchange }: { exchange: string }) {
  const ownership = useOwnership(exchange);
  const [picked, setPicked] = useState<string | null>(null);
  const top =
    ownership.data?.rows.slice().sort((a, b) => b.bought_usd_90d - a.bought_usd_90d)[0]?.ticker ?? null;
  const selected = picked ?? top;
  const detail = useOwnershipDetail(selected);
  return (
    // One column: the table has six columns and a holder name in the last, which a half-width card
    // squeezed into wrapped fragments.
    <div className="grid gap-4">
      <Section
        title="Who inside the company is buying or selling?"
        explain="From the filings US law requires: insiders must report each trade within two business days, and anyone holding over 5% must say so. Open-market trades only, not shares received as pay."
      >
        {ownership.data ? (
          <OwnershipTable data={ownership.data} selected={selected} onSelect={setPicked} />
        ) : (
          <Placeholder height="h-96" />
        )}
      </Section>
      <Section
        title={selected ? `Large holders and insider trades — ${selected}` : "Large holders and insider trades"}
        explain="Holders over 5% as of each one's latest filing, then every open-market insider trade of the past year, newest first. Planned means the insider said the trade was scheduled in advance."
      >
        {detail.data ? <OwnershipDetail data={detail.data} /> : <Placeholder height="h-64" />}
      </Section>
    </div>
  );
}

function WatchlistSection({ exchange }: { exchange: string }) {
  const watchlist = useWatchlist();
  return (
    <Section
      title="Followed beyond the model"
      explain="Names these research pages follow that the model does not, and why each is followed. They appear in the tables above with a watchlist tag, and none of them feeds the model, its forecasts or its paper books."
    >
      {watchlist.data ? (
        <WatchlistCard names={watchlist.data.names.filter((n) => n.exchange === exchange)} />
      ) : (
        <Placeholder height="h-24" />
      )}
    </Section>
  );
}

// Company fundamentals from SEC filings (ADR 0007). US companies file with the SEC; others do
// not, so that market gets a plain statement instead of an empty table. The exchange registry
// marks the US by `has_options`, which stands in here because the US is the only market in it
// that both lists options and files with the SEC; a market that did one without the other would
// need its own flag.
function FundamentalsTab({ exchange, hasFilings }: { exchange: string; hasFilings: boolean }) {
  const fundamentals = useFundamentals(exchange);
  return (
    <div className="grid gap-4">
      <Section
        title="How are the businesses doing?"
        explain="Revenue, profit and cash over each company's last twelve reported months, from the figures it files with the SEC, and what its price pays for them. Each ratio compares figures over the same months."
      >
        {!hasFilings ? (
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            This market's companies do not file with the US regulator, so their figures are not
            in this free source. It is an assessment of the evidence, not a recommendation to buy or
            sell anything.
          </p>
        ) : fundamentals.data ? (
          <FundamentalsTable data={fundamentals.data} />
        ) : (
          <Placeholder height="h-96" />
        )}
      </Section>
    </div>
  );
}

// The advisor brief (ADR 0007): one stock at a time, printable, for a conversation with a licensed
// advisor. Covers the model's universe and the watchlist for the chosen market.
function BriefTab({ exchange }: { exchange: string }) {
  const index = useBriefIndex(exchange);
  // `?brief=GME` opens that stock's brief, so a brief can be linked to and shot for the README.
  const [picked, setPicked] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get("brief")?.toUpperCase() ?? null,
  );
  const names = index.data?.names ?? [];
  const selected = picked && names.some((n) => n.ticker === picked) ? picked : (names[0]?.ticker ?? null);
  const brief = useBrief(selected);
  return (
    <div className="grid gap-4">
      <section className="card no-print p-4">
        <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
          A brief to take to your advisor
        </h2>
        <p className="mb-3 mt-0.5 text-xs" style={{ color: "var(--text-muted)" }}>
          One page per stock: what the public evidence on these pages shows, the points that lean
          each way, the risks and the questions to ask. It assesses; it never says what to do. Pick
          a stock, then print it or save it as a PDF.
        </p>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <select
            aria-label="Stock"
            value={selected ?? ""}
            onChange={(ev) => setPicked(ev.target.value)}
            className="rounded border px-2 py-1"
            style={{ borderColor: "var(--border)", background: "var(--surface-1)", color: "var(--text-primary)" }}
          >
            {names.map((n) => (
              <option key={n.ticker} value={n.ticker}>
                {n.ticker}
                {n.name ? ` — ${n.name}` : ""}
                {n.followed_by === "watchlist" ? " (watchlist)" : ""}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => window.print()}
            className="rounded border px-3 py-1"
            style={{ borderColor: "var(--border)", color: "var(--text-primary)" }}
          >
            Print or save as PDF
          </button>
        </div>
      </section>
      {brief.data ? <AdvisorBrief data={brief.data} /> : <Placeholder height="h-96" />}
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
      <Section
        title="What would change a standing decision?"
        explain="Decisions already taken about the model, each with the conditions named in advance that would reopen it, checked against the current record."
      >
        {decisions.data ? (
          <DecisionsCard data={decisions.data} />
        ) : (
          <Placeholder height="h-56" />
        )}
      </Section>
      <Section
        title="What has been measured, and what came back"
        explain="Every investigation this project has run: the question it asked and what the evidence showed, including results later withdrawn."
      >
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
      <Section
        title="Every model trained, promoted or not"
        explain="Each weekly retraining produces a candidate. A gate compares it with the current champion on recent data neither was trained on, and promotes it only if it is clearly better."
      >
        {history.data ? (
          <ModelHistoryTable runs={history.data} />
        ) : (
          <Placeholder height="h-40" />
        )}
      </Section>
      <Section
        title="What the paper book holds now"
        explain="Today's positions: the stocks bought (long) and sold short, each one's share of the book, and the forecast behind it."
      >
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
      <header className="no-print mb-4 flex flex-wrap items-baseline justify-between gap-2">
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
        <div className="no-print mb-4">
          <FreshnessStrip freshness={freshness.data} />
        </div>
      ) : null}

      <div className="no-print mb-4">
        <Tabs tabs={tabs} active={tab} onSelect={setTab} />
      </div>

      {tab === "Overview" ? (
        <OverviewTab exchange={exchange} benchmark={market?.benchmark} />
      ) : null}
      {tab === "Evidence" ? (
        <EvidenceTab exchange={exchange} benchmark={market?.benchmark} />
      ) : null}
      {tab === "Options" && tabs.includes("Options") ? (
        <OptionsTab exchange={exchange} />
      ) : null}
      {tab === "Positioning" && tabs.includes("Positioning") ? (
        <PositioningTab exchange={exchange} hasOptions={market?.has_options ?? true} />
      ) : null}
      {tab === "Fundamentals" ? (
        <FundamentalsTab exchange={exchange} hasFilings={market?.has_options ?? true} />
      ) : null}
      {tab === "Brief" ? <BriefTab exchange={exchange} /> : null}
      {tab === "Model & Book" ? <ModelTab exchange={exchange} /> : null}
      {tab === "Research" ? <ResearchTab /> : null}
    </div>
  );
}
