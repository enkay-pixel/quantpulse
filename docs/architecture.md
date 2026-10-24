# Architecture

**In short:** How the pieces fit: the services that run in Docker, how data flows from prices to
forecasts to the dashboard, and the main design choice behind each layer.

## Services (docker compose)

| Service | Purpose | Port | Memory cap |
|---|---|---|---|
| `postgres` | 3 databases: `market` (app data), `dagster` (orchestrator storage), `mlflow` (tracking backend) | 5432 | 512M |
| `dagster-webserver` + `dagster-daemon` | Pipeline UI; schedules/sensors/run launcher. Both load the code location in-process from the shared image (one fewer container than a gRPC code server — deliberate on 16 GB) | 3000, published by `web` | 768M + 2G |
| `mlflow` | Experiment tracking + model registry (single worker) | 5001→5000 | 1G |
| `api` | FastAPI serving layer | 8000 | 384M |
| `web` *(M5)* | React dashboard behind nginx; also Dagster's UI, behind a host check | 8080, 3000 | 128M |

All host ports bind **127.0.0.1 only**. Dagster and MLflow ship without authentication, and
an exposed MLflow registry would let anyone on the LAN reassign the `@champion` alias to
their own artifact — which the scoring pipeline then deserializes. The laptop roams
networks, so nothing is published beyond loopback.

Loopback keeps the LAN out but not this machine's browser: any web page open in it can send
requests to 127.0.0.1, by cross-origin calls or by DNS rebinding (a hostile name re-pointed at
127.0.0.1). Three things close that, each found in the 2026-10-22 security review:

- **MLflow keeps its own host and origin checks**, with explicit lists (`docker/mlflow.Dockerfile`).
  They had been set to `*`, which let any website call the registry's write API.
- **Dagster is reached only through nginx**, which refuses any `Host` but `localhost` and
  `127.0.0.1` (`docker/nginx.conf`); its webserver has no host check of its own.
- **The pipeline loads only native LightGBM boosters** (`registry.load_booster`). MLflow's loader
  chooses how to read a model from the model's own metadata and unpickles anything that is not a
  booster, so a model planted in the registry could otherwise run code in the daemon.

Whether a browser lets a public page reach 127.0.0.1 at all varies by browser and version; these
controls do not depend on it.

Total idle footprint target: **≤ 2.5 GB**, sized for a 16 GB MacBook. Docker Desktop's VM has
7.75 GiB (`docker info`, 2026-10-22). The caps above sum to about 4.8 GB, which leaves room for
one 2.5 GB experiment container at a time beside the stack. The daemon's cap rose from 1.5 GiB on
2026-10-24 ([M13 plan](plans/m13-europe-wave.md#headroom-and-why-it-comes-first)).

## Data flow

1. `raw_prices` (partitioned by **`(date, exchange)`**) pulls OHLCV bars from yfinance (its only
   source), repairs vendor unit glitches, and upserts into `market.prices`. A
   `MultiPartitionsDefinition` because a JSE holiday is not an NYSE holiday and each market has its
   own post-close schedule.
2. `features` computes technical + cross-sectional features into `market.features`, ranking
   cross-sectionally **within each exchange**. It works one market at a time, so its memory
   follows the largest market rather than the sum, and writes only rows whose values changed
   (`refresh_features`, since 2026-10-22).
3. `predictions` loads each market's champion (`quantpulse-lgbm-<exchange>@champion`) and scores its
   latest features.
4. `portfolio_equity` rebuilds the three paper books **per market** from predictions.
5. `drift_report` (Evidently) compares recent feature/prediction distributions against the
   champion's training reference.

`market_today()` / `is_post_close()` / the calendars are all exchange-aware; nothing uses the
container's UTC clock (`data/calendar.py`).

Dagster runs one job at a time (`max_concurrent_runs: 1` in `docker/dagster.yaml`), so runs that
fire together queue. Within a run, each step is its own process, starting at about 285 MiB because
it loads the whole stack, and at most two run at once (`MAX_CONCURRENT_STEPS` in
`orchestration/definitions.py`). How close that comes to the daemon's cap is in the
[runbook](runbook.md#resource-headroom).

## Transform layer (dbt)

SQL analytics live in a dbt project at `transform/`: staging views (1:1 over raw tables)
and marts in the `analytics` schema — `fct_daily_returns`, `fct_signal_performance`
(signal-quintile forward returns: the plainest read of model skill), `fct_portfolio_daily`
(cumulative return + drawdown), `fct_alpha_beta`, `fct_track_record`, and `dim_universe`.
Every mart carries `exchange`, and all window functions partition by it so one market's
history never leaks into another's drawdown peak or rolling Sharpe. Per-market benchmark
tickers come from a `benchmarks` var mirrored to `data/calendar` (a unit test asserts they
agree). dbt tests add a second data-quality layer, and `dagster-dbt` mounts every model
into the same asset graph (group `transform`), scheduled with the daily processing job.
Sources map to upstream Dagster assets via `meta.dagster.asset_key`, so lineage runs
unbroken from yfinance to the marts. Run locally with `make dbt-build`; browse docs +
lineage with `make dbt-docs`.

## Options layer

yfinance provides free **live** option chains but **no history** — you cannot backfill
past chains at any price short of a paid vendor. So options are not a backtested
strategy here; they are a live analytics layer that *builds its own history forward*:
the daily `option_chains` asset snapshots the nearest ~10 expiries within ±20% moneyness
per ticker into `option_quotes`, enriching each contract with Black-Scholes Greeks
(`options/pricing.py`, market IV so nothing is solved for). dbt turns those snapshots
into `fct_option_summary` (ATM IV, put/call ratio) and `fct_iv_surface` (mean IV by
expiry and moneyness bucket — the smile/skew and term structure).

Snapshots are guarded by the `option_snapshot_quality` asset check (`options/quality.py`):
ticker coverage, plausible median IV among *traded* contracts — the signature that
catches stale/pre-market feeds — traded contracts present, and Greeks non-null.

**Tier 2** (`options/strategy.py`) translates the equity model's 21-day forecast into a
*hypothetical* defined-risk structure (bull call / bear put spread) with cost, max
profit/loss and breakeven. It is an illustration of the model's directional view — never
a recommendation, and the UI says so prominently.

## Research branch

A second use of the same data, kept apart from the model
([ADR 0007](adr/0007-research-branch-evidence-not-instructions.md)): evidence for forming a view
of an investment, never an instruction to act on one. It lives in `quantpulse.research`, has its
own tables and its own Dagster job (`research_job`, weekday mornings New York time), and nothing
in it is a model input — it cannot change the live record, the books or the shadow run.

The first page is **Positioning**: where the mechanics of a short squeeze or a gamma squeeze
would have fuel across the names with option chains. `short_interest` stores the vendor's
monthly short-interest figures insert-only; `fct_gamma_by_strike` computes the stock a hedger
would trade per 1% move from the captured chains; `fct_positioning` sets both against average
dollar volume. Calls and puts are never netted, because who holds which side is not public, and
short interest is dated by when it became known rather than when it settled.

The second measure, **attention**, covers both markets: the JSE publishes neither short interest
nor option chains free, but each company has a Wikipedia article. `page_views` stores daily views
per stock (titles in `configs/attention.yaml`, checked canonical on every run, because the API
does not count redirects), and `fct_attention` sets the past week against the usual level. The
Positioning tab shows on both markets, with the squeeze sections only where their data exists.

The **research watchlist** extends both measures beyond the model's universe. `configs/watchlist.yaml`
lists names to follow, each with a sentence on why; `watchlist_job` (weekday evenings, 17:30 New
York time) syncs them into `watchlist`, refetches their bars into `watchlist_prices` and captures
their chains, in the universe's band, into `watchlist_option_quotes`. The morning `research_job`
adds their short interest and page views to the existing tables. The marts read both sources
through `stg_research_names`, and every row says who follows it (`followed_by`: `model` or
`watchlist`). A universe ticker is refused, and none of these tables has a path to a feature, a
prediction or a paper book.

**Ownership** comes from SEC EDGAR, for US stocks only: insider trades from Form 4 into
`insider_transactions`, and stakes over 5% from structured Schedules 13D and 13G into
`holder_filings`, fetched by `research_job` each weekday morning. Every filing read is logged in
`edgar_filings` with its outcome, so none is fetched twice, and a filing is kept only when the
issuer it names is the company whose list it came from: a company's list also holds its own stakes
in other companies. `fct_insider_trades` keeps open-market trades only, `fct_large_holders` each
filer's latest stake still at 5% or more, and `fct_ownership` sums both per stock. EDGAR needs a
contact in each request, set as `QUANTPULSE_SEC_CONTACT` in the local `.env` only.

**Fundamentals** come from EDGAR's XBRL facts, for the same US stocks: `financial_facts` keeps each
tagged figure as reported, one row per filing, and `fct_financial_lines` picks one value per line
and period (the tag in use now, ties to the broadest). `fct_fundamentals` computes the last twelve
months as the fiscal year plus this year so far less the same months before, divides only figures
over the same months, and leaves price ratios empty without a current whole-company share count.
`research_job` fetches a company again only when it files a new 10-K or 10-Q, and retries weekly a
statement EDGAR's document has not caught up with (`fundamentals_fetches`).

The **advisor brief** draws all of it together for one stock at a time (`research/brief.py`,
`GET /research/brief/{ticker}`, the Brief tab). `gather` reads every source the pages use: price
history, the model's rank and its live record, short interest, option hedging, attention,
ownership and the paper options book. `compose` turns those numbers into facts, points that lean
each way, risks, questions for an advisor and the page's limits, by fixed thresholds named in the
module. No language model writes any of it (ADR 0004), so the same evidence always reads the same
way, and a unit test fails if any sentence it can produce tells the reader to buy, sell or hold.
The tab prints on its own, without the dashboard around it.

## Paper options book

The model's forecasts held through options instead of shares
([ADR 0008](adr/0008-options-book-the-signal-as-spreads.md)). It varies one thing from the
21-session share book, the instrument. Each cohort opens on that book's rebalance dates, on the
same names, read from its stored positions: a bull call spread for each long, a bear put spread for
each short, using the strike rule of the Options tab's illustration (`options/strategy.py`). The
expiry is the first after the next rebalance, and the cohort closes at that rebalance.

Fills are pessimistic — buy at the ask, sell at the bid, commission per leg — but only on *sound*
quotes: a real bid, a gap within 25% of the midpoint or $0.25, and at least ten contracts open. A
leg whose quote is missing or unsound on a later day is valued at its last sound quote. Each cohort
risks 10% of the book. `options_book_job` rebuilds both tables in full each weekday evening, after
the share books, in its own job; nothing reads the options book back.

The nightly chain capture also keeps both legs of every open spread at any distance from spot, in
`held_option_quotes`, from the same download. A held strike the stock moved away from therefore
stays priced, instead of dropping out of the ±20% band and falling back to its last quote. The
held quotes have their own table so the band in `option_quotes`, which the IV surface, the
positioning marts and the completeness checks read, stays exactly as it was.

## Paper books: variations from a baseline

A *book* is one way of turning the signal into a portfolio. `ml/portfolio.py` runs **three**
of them over the same predictions, per market, stored in `portfolio_snapshots` keyed by
`(exchange, variant)`. Each is a variation from the `daily` baseline that changes **exactly
one** field:

| variant | varies | isolates |
|---|---|---|
| `daily` (baseline) | — | trade the signal every day |
| `horizon` | rebalance frequency (1d → 21d) | what trading more often costs |
| `long_only` | short leg (on → off) | what the short contributes; executable where scrip lending is thin |

Because each variation differs from the baseline in one dimension only, the gap between a
variation and the baseline is attributable to that dimension. Two *variations* are **not**
comparable to each other (they differ in two things) — compare each to the baseline. A unit
test (`test_each_book_varies_exactly_one_field_from_the_baseline`, run per market) fails if
any book diverges in more than its declared field.

Quantile width is shared across a market's books but differs *between* markets, set from
breadth so each holds a comparable **number** of positions (~10/side): 20% of 50 US names,
35% of 29 JSE names. `books_for(exchange)` derives the set at the market's width.

Compared at `GET /portfolio/books`. The dashboard and every dbt mart describe the `daily`
book — `stg_portfolio_snapshots` pins the variant (but keeps every market) so additional
books cannot double-count downstream. The horizon-cost finding is in [roadmap.md](roadmap.md).

## Measuring skill vs market exposure

`fct_alpha_beta` regresses strategy excess returns on **that market's** benchmark excess
returns (Postgres `regr_slope` / `regr_intercept` / `regr_r2`) per `(exchange, phase)`,
yielding beta, annualized alpha, R², tracking error and information ratio. This exists
because raw return vs the index is the wrong test for a market-neutral long/short book: it
gives up market beta by construction, so trailing the index in a bull run says nothing
about skill. Beta answers "how much of this is just the market?" and alpha answers "what
does the signal actually add?". Benchmark is per market (SPY / STX40.JO) — comparing a JSE
book to SPY would measure the rand and the S&P, not the strategy. Served at
`/portfolio/alpha-beta?exchange=…`; the Evidence tab renders it with a plain-English
verdict, and switches from replay to live once ~20 live days exist. Below 20 days every
ratio is nulled at source (`min_days_for_ratios`) so no consumer sees noise as a number.

## Cost realism

`ml/backtest.py` charges commission, slippage, *and* an annualized borrow fee on the
short leg (shorting is not free). Costs scale with **measured** turnover — half the
summed absolute change in capital weights between rebalances, so holding the same names
is free and rotating into a disjoint book costs a full unit. (It previously charged a
flat rate equal to the quantile width, which made costs blind to churn and understated
them by ~33%.) `ml/sensitivity.py` sweeps cost against borrow so results are reported as
a range rather than one optimistic number, and `breakeven_cost` returns `inf` — rather
than the grid ceiling — when the strategy survives the harshest cost tested, so a sweep
that never found the breakeven cannot be misread as having measured one. Exposed via
`quantpulse sensitivity`. Costs are not the binding constraint here; see the
horizon-mismatch finding and the bias list in [roadmap.md](roadmap.md).

## Reliability: alerts and catch-up

Two Dagster sensors (`orchestration/definitions.py`) close the two failure modes a
local-first platform actually hits:

- `pipeline_failure_alert` — a run-failure sensor writing to the `pipeline_alerts` table in
  Postgres (`monitoring/alerts.py`, served at `/alerts`) plus a best-effort macOS
  notification. Postgres rather than a file, because the daemon records alerts while the API
  serves them from another container. Silent failure is the worst outcome for a system whose value is
  accumulating daily history that cannot be backfilled.
- `missed_partition_catchup_sensor` — per market, compares expected sessions on that
  market's calendar against actual price coverage (`orchestration/catchup.py`) and
  re-requests any day below 80% coverage, bounded per tick per market. Schedules only fire
  while the stack is up, and this runs on a laptop that sleeps. A session that landed but is
  **missing particular tickers** is re-requested too, which coverage cannot detect (a few
  tickers barely move the ratio) — for the benchmark that deletes the whole day from the CAPM
  marts, and for any ticker it stretches its features across the gap. That retry is
  fill-only (just the missing tickers, never overwriting a stored bar), expires after five
  sessions, and stops once a training run has used the session, per
  [ADR 0006](adr/0006-price-data-is-filled-not-rewritten.md). Each session gets three attempts
  per day and the budget resets daily, so an outage that exhausts it recovers on its own; and
  nothing is requested for yesterday while today's session is trading.
- `benchmark_freshness` (asset check) — reports any session a market ingested whose
  benchmark lacks a bar, over a 30-session window. Separate from `recent_prices_quality`
  because that judges every ticker against one completeness ratio, where a single absent
  day scores 0.967 against a 0.95 threshold. Correct for an ordinary ticker; wrong for the
  one `fct_alpha_beta` and `fct_portfolio_vs_benchmark` inner-join, where each gap silently
  costs a day of the out-of-sample record. Non-blocking — a stale benchmark thins the alpha
  numbers rather than corrupting them.
- `predictions_are_current` (asset check) — fails when a configured market's predictions
  fall > 4 days behind its features, i.e. scoring is silently writing nothing (no champion,
  or a renamed registry). Nothing else surfaces "the numbers just stopped moving".
- `option_snapshot_repair_sensor` — re-runs **today's** option snapshot when it landed
  below 80% ticker coverage, capped at 3 attempts a day. Scoped to today on purpose:
  chains are live-only, so an incomplete past day is a permanent hole and re-running
  would just snapshot the present. Prices, by contrast, are always backfillable — which
  is why they get a 30-day lookback and options get one day.

## Evidence layer

The dashboard's job is to make the strategy *auditable*, not to sell it. The dbt marts
split performance into an in-sample `replay` phase and the `live` out-of-sample record
that starts at each market's first champion promotion (`fct_portfolio_daily.phase`,
`fct_track_record`), benchmark it against that market's index buy-and-hold
(`fct_portfolio_vs_benchmark`), and expose signal-quintile forward returns
(`fct_signal_performance`). Every endpoint takes `?exchange=` (defaulting to XNYS) and
404s on an unknown code rather than returning an empty result that reads as "no data yet".
The API serves these plus the current paper book and the full `model_runs` audit trail;
the React app renders them across six tabs
(Overview / Evidence / Options / Positioning / Model & Book / Research); the two that read
option chains are hidden on markets without them. All endpoints degrade to empty payloads on a
fresh database before the first dbt build.

## The adaptation loop

- **Weekly schedule** (and a **drift sensor**) trigger the training job: purged/embargoed
  time-series CV, Optuna hyperparameter search (capped trial budget), final LightGBM fit, all logged
  to MLflow.
- The candidate is evaluated on a holdout backtest (Sharpe, max drawdown, information coefficient).
- Promotion logic assigns the `@champion` alias only if the candidate beats the incumbent by a
  configured margin — otherwise the champion stays. Every decision is recorded in
  `market.model_runs`.

## Package layout

Single installable package `quantpulse` (src layout). Dagster definitions live in
`quantpulse.orchestration` and import the same modules the API uses — pipeline code is plain,
testable Python; Dagster assets are thin wrappers.

## Why these tools

See [adr/](adr/) — notably [0002](adr/0002-consolidate-two-prototypes.md) (consolidation),
[0003](adr/0003-orchestrator-and-stack-choices.md) (Dagster, React+FastAPI, zero-cost
constraints), [0004](adr/0004-no-llm-question-answering-layer.md) (why there is no LLM
question-answering layer — the deterministic verdict functions already do that job, and
cannot fabricate a number), and
[0005](adr/0005-exchange-as-a-first-class-dimension.md) (exchange as a first-class
dimension — the multi-market architecture), and
[0006](adr/0006-price-data-is-filled-not-rewritten.md) (price data is filled, never rewritten,
and fixed once a model has trained on it).
