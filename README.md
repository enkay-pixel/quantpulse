# QuantPulse

[![CI](https://github.com/enkay-pixel/quantpulse/actions/workflows/ci.yml/badge.svg)](https://github.com/enkay-pixel/quantpulse/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![React 19](https://img.shields.io/badge/react-19-61DAFB?logo=react&logoColor=black)](web/package.json)

A local-first MLOps platform for a **self-adapting ML investing model**, running **two markets — NYSE and the JSE** side by side. Fully free, fully open-source, runs on one machine via Docker: automated per-market data pipelines, scheduled retraining with champion/challenger promotion, drift monitoring, a serving API, and a live dashboard with a market switcher.

> **Disclaimer**: educational engineering project. Nothing here is investment advice, and the model's signals are research output in a sandbox — not trade recommendations.

![QuantPulse dashboard](docs/assets/dashboard.png)

<details>
<summary><b>More screenshots</b> — Evidence, Options, and Model &amp; Book tabs</summary>

### Evidence — does the model actually have skill?

![Evidence tab](docs/assets/evidence-tab.png)

The CAPM decomposition is the headline: **beta −0.05 and R² 0.007 confirm the book is
genuinely market-neutral**, so comparing its raw return to SPY was never the right test.
Alpha is **+4.74% annualized** over the replay — but read that with two caveats the panel
states plainly: the window is in-sample, and the information ratio is still **negative
(−0.34)**. (Alpha was −0.56% until the paper book stopped double-charging its trading
costs — see [docs/roadmap.md](docs/roadmap.md); a measurement bug, not a strategy change.)

Below it, the two-book panel shows what rebalancing frequency actually costs, then signal
quintiles slope the right way (Q1 highest → Q5 lowest: real ranking skill, modest in size)
alongside drawdown and rolling Sharpe.

### Options — implied volatility, Greeks, and a hypothetical expression of the signal

![Options tab](docs/assets/options-tab.png)

The volatility smile is built from **out-of-the-money contracts with open interest only** —
deep in-the-money options barely trade, so their quoted IV is stale noise that would
otherwise spike both wings past 150%. The right-hand card translates the model's
directional view into a defined-risk spread, clearly labelled as illustration, never advice.

### Model &amp; Book — every champion/challenger decision, and the current paper positions

![Model and book tab](docs/assets/model-book-tab.png)

### The JSE — the same evidence layer, a different market

![JSE Evidence tab](docs/assets/jse-evidence.png)

Switching to XJSE re-scopes everything: **beta is measured against STX40.JO** (not SPY —
comparing a JSE book to the S&P would measure the rand, not the strategy), the Options tab
is gone (no free JSE chain data), and the numbers are the JSE champion's. Its in-sample
replay looks strong (alpha +16%, IR 0.42, all three books positive), but the panel says
plainly these are in-sample — the JSE champion's true holdout Sharpe is 1.32 on 29 names,
which only live days will confirm.

</details>

## What it does

```mermaid
flowchart LR
    subgraph Dagster["Dagster (daily & weekly schedules)"]
        A[Ingest daily bars\nyfinance + fallback] --> B[Feature\nengineering]
        B --> C[Score with\nchampion model]
        B --> T[Weekly retrain\nOptuna + purged CV]
        T --> E{Beats champion\non holdout backtest?}
        E -- yes --> P[Promote to\n'@champion']
        D[Drift monitor\nEvidently] -- drift detected --> T
    end
    A --> PG[(Postgres)]
    C --> PG
    P --> MLF[MLflow registry]
    PG --> API[FastAPI]
    MLF --> API
    API --> WEB[React dashboard]
```

- **Two markets, one platform** — NYSE and the JSE run side by side. `exchange` is a first-class dimension: per-market calendars and post-close schedules (in each market's timezone), cross-sectional features ranked *within* a market, one champion per market, and a dashboard switcher. Cross-sectional ranking that mixed Naspers with Apple would be noise, so it never does.
- **Ingestion** — daily OHLCV bars for a configurable multi-market universe ([configs/universe.yaml](configs/universe.yaml)), with retries, rate-limit respect, vendor unit-glitch repair (Yahoo occasionally reports JSE prices in Rand not cents), and data-quality checks as Dagster asset checks.
- **Self-adapting model** — LightGBM forward-return model per market, retrained weekly *and* whenever feature drift is detected; a challenger only replaces the champion if it wins on an out-of-sample backtest, and a first champion must clear a Sharpe floor (no champion beats a model that lost money out-of-sample).
- **Transforms** — a dbt project ([transform/](transform/)) builds staging views and analytics marts (daily returns, signal-quintile performance, portfolio drawdown, CAPM decomposition) per market with dbt tests, integrated into the Dagster asset graph via `dagster-dbt`. Small-sample ratios are nulled at source, so no consumer sees an annualized Sharpe off three days.
- **Options analytics** — daily live option-chain snapshots (free via yfinance) enriched with Black-Scholes Greeks, surfaced as an implied-volatility smile/skew, put/call ratio, and a chain browser. Because no free *historical* chain data exists, the pipeline **builds its own options history forward** from the first run. A clearly-disclaimered panel also illustrates how the model's directional view *would* translate into a defined-risk spread — an illustration, never advice.
- **Measured honestly** — a CAPM decomposition splits the return into the part that is just the market moving (beta) and the part that isn't (alpha), reported alongside the information ratio, because comparing raw return to SPY says nothing about a portfolio built to be market-neutral. The dashboard writes the verdict out in plain English — including when alpha and the information ratio point opposite ways, rather than quoting whichever one flatters, and it labels in-sample figures as a description of the fit rather than evidence of skill.
- **Fails loudly, catches up by itself** — a run-failure sensor logs every failure (served at `/alerts`, plus a desktop notification) and a catch-up sensor re-requests any trading day the schedule slept through, so a laptop that sleeps doesn't silently cost you irreplaceable history.
- **Honest cost modelling** — the backtest charges commission, slippage, and an annualized short-borrow fee against *measured* position churn, and `quantpulse sensitivity` sweeps both to report a *range* of outcomes plus the breakeven trading cost, rather than a single flattering number.
- **Three books, one variable each** — the same predictions run as three portfolios (*books*), each changing exactly one thing from a shared baseline so the difference is attributable: `daily` (baseline), `horizon` (held 21 days — isolates trading cost, and **85% of the 6.6-point gap on NYSE is cost, not better picks**), and `long_only` (no short leg — isolates what the short contributes, and is executable where scrip lending is thin). Compare each to the baseline, never to each other.
- **Evidence, not vibes** — the dashboard separates the in-sample replay from the **live out-of-sample track record**, benchmarks each market against its own index (SPY / STX40.JO), charts signal-quintile forward returns and rolling risk, and shows every champion/challenger decision — including reversals — the self-adapting loop ever made.
- **Serving** — FastAPI exposes predictions, portfolio equity curve, model metadata, and drift status.
- **Dashboard** — React app with templated charts that refresh from the API.

## Quickstart

```bash
cp .env.example .env          # adjust if you like
make up                       # start the Docker stack
make install                  # install package + dev tools into your venv
make test                     # run unit tests
```

### First run (seed the platform)

On a fresh database, one command migrates the schema, syncs the universe, backfills
history, computes features, trains + promotes the first champion, and scores the
signal trail for the dashboard:

```bash
make bootstrap
```

From then on the Dagster schedules keep everything current whenever the stack is up: each
market ingests after its own close in its own timezone, processing runs once after the
latest close, and retraining runs weekly plus on detected drift. The dashboard's
pre-champion equity history is an **in-sample replay** to seed the charts — the live track
record accrues from the first scheduled runs onward. Switch markets on the dashboard with
the XNYS / XJSE toggle (also in the URL: `?market=XJSE`).

| UI | URL |
|---|---|
| Dagster | http://localhost:3000 |
| MLflow | http://localhost:5001 (5000 is taken by macOS AirPlay) |
| API docs | http://localhost:8000/docs |
| Dashboard | http://localhost:8080 |

Postgres is exposed on `localhost:5432` (DBeaver-friendly; credentials in your `.env`).

## Project status

- [x] M0 — Project scaffold, tooling, CI
- [x] M1 — Data platform (schema, ingestion, quality checks)
- [x] M2 — ML core (features, purged CV, training, backtest, promotion)
- [x] M3 — Dagster orchestration + full Docker stack
- [x] M4 — Serving API
- [x] M5 — React dashboard
- [x] M6 — Docs polish & first release
- [x] M7 — dbt transform layer (staging + marts, tests in CI, dagster-dbt lineage)
- [x] M8 — Evidence dashboard (live vs replay track record, SPY benchmark, quintile & risk charts, model audit trail)
- [x] M9 — Options layer (chain snapshots + Greeks, IV surface & put/call marts, Options tab, hypothetical signal→spread translation)
- [x] M10 — Rigor & reliability (CAPM alpha/beta, failure alerts, missed-day catch-up)
- [x] M11 — Multi-market (exchange as a first-class dimension, JSE added, market switcher, three paper books, resource-headroom check)

## Development

```bash
make fmt        # format + autofix
make lint       # CI-style checks
make type       # mypy
make test-all   # includes integration tests (needs `make up`)
make hooks      # install pre-commit hooks
```

Current state, honest performance, and what's next: [docs/roadmap.md](docs/roadmap.md).
Design decisions are recorded in [docs/adr/](docs/adr/). Architecture details in [docs/architecture.md](docs/architecture.md); operational how-tos in [docs/runbook.md](docs/runbook.md); the full build narrative and incident log in [docs/development-history.md](docs/development-history.md).

## License

MIT
