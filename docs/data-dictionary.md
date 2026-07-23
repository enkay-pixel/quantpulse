# Data dictionary — `market` database

> **Three databases share this Postgres server.** Only `market` (schemas `public` +
> `analytics`) is ours — defined by Alembic migrations and `src/quantpulse/db/models.py`.
> The `mlflow` and `dagster` databases are owned by those tools and **must not be modified
> by us**. Their conventions differ on purpose and are not a defect: MLflow stores every
> timestamp as `bigint` epoch-milliseconds and IDs as `varchar` (backend-portable, UTC by
> construction); Dagster uses naive `timestamp without time zone`. If you inspect the server
> in DBeaver and see int/varchar where you expected a datetime, you're almost certainly
> looking at one of those two, not at `market`.

Populated from M1 onward; columns finalized alongside the Alembic migrations. Since M11
the platform is multi-market, so **`exchange` is a dimension** on the tables that need it.
Tickers are globally unique (JSE names carry a `.JO` suffix), so `prices`, `features` and
`predictions` reach their market by joining `universe` rather than carrying the column.

**Types are chosen deliberately:** dates are `date`, all `*_at` timestamps are
`timestamptz`, prices/greeks/IV are `double precision` (matches numpy and the ML stack —
`numeric` would be pedantic here), counts are `bigint`, feature vectors / positions /
metrics are `jsonb`. Categorical *domain* columns carry CHECK constraints that document and
enforce their vocabulary — `asset_type`, `option_type`, `source`, `run_type`, `decision`.
`exchange` and `variant` are intentionally **not** CHECK-constrained: they are config-driven
(markets from `data.calendar.EXCHANGES`, books from `ml.portfolio.BOOKS`) and validated in
Python, so a DB CHECK would duplicate that and force a migration on every new market or book.

| Table | Grain | Purpose |
|---|---|---|
| `universe` | ticker | Tradable universe with metadata (name, type stock/etf, active flag, **exchange** — the source of truth for which market a ticker belongs to) |
| `prices` | (ticker, date) | Daily OHLCV bars, adjusted; source column (yfinance/stooq). Vendor unit glitches repaired on write (see `data/cleaning.py`) |
| `features` | (ticker, date) | Engineered features; cross-sectional ranks are computed **within** each exchange |
| `predictions` | (ticker, date, model_version) | Champion-model forward-return scores, per market's own champion |

Every `ticker` column (`prices`, `features`, `predictions`, `option_quotes`) is a foreign
key to `universe.ticker` (`ON DELETE RESTRICT`), so no derived row can point at a ticker the
platform doesn't know.
| `model_runs` | run id | Training/evaluation/promotion audit log (metrics, decision, MLflow run id, **exchange**). Append-only: a `demotion` row supersedes an earlier `promoted` one |
| `drift_metrics` | (date, metric) | Evidently drift results per feature set |
| `portfolio_snapshots` | **(date, exchange, variant)** | Simulated paper-book equity, exposure, turnover. Several *books* (`daily` / `horizon` / `long_only`) run per market — see [architecture.md](architecture.md) |
| `option_quotes` | (snapshot_date, ticker, expiry, strike, option_type) | Daily live option-chain snapshots + Black-Scholes Greeks. NYSE only (no free JSE chain data). Accumulates forward — no free history exists to backfill |

## `analytics` schema (dbt-managed — see `transform/`)

Every mart below carries `exchange`, so the dashboard's market switcher scopes each one.
The two option marts are single-market by necessity. Ratios (Sharpe, information ratio,
win rate, beta) are **nulled below 20 days** (`min_days_for_ratios`): a handful of days
annualizes to a confident-looking number that is pure noise. Counts and totals survive at
any sample size.

| Relation | Grain | Purpose |
|---|---|---|
| `stg_*` (views) | 1:1 with raw | Typed, renamed staging; `stg_predictions` dedupes to newest model version; `stg_portfolio_snapshots` pins `variant = 'daily'` but keeps every market |
| `fct_daily_returns` | (ticker, exchange, date) | Simple returns + 21-day rolling volatility/mean |
| `fct_signal_performance` | (date, exchange, signal_quintile) | Next-day realized return per signal quintile (1 = strongest), ranked **within each market** — model-skill readout |
| `fct_portfolio_daily` | (date, exchange) | Portfolio with cumulative return, running drawdown, rolling 63d Sharpe, and evidence `phase` (replay/live), all partitioned per market |
| `fct_portfolio_vs_benchmark` | (date, exchange) | Strategy equity vs that market's benchmark (SPY / STX40.JO) indexed to the portfolio's first date |
| `fct_track_record` | (exchange, phase) | Per-phase performance summary — the `live` row is the honest out-of-sample record |
| `dim_universe` | ticker | Members with exchange and price-coverage metadata |
| `fct_alpha_beta` | (exchange, phase) | CAPM decomposition vs the market's benchmark: beta, annualized alpha, R², tracking error, information ratio (Postgres regression aggregates over excess returns) |
| `fct_option_summary` | (ticker, snapshot_date) | ATM implied volatility and put/call open-interest ratio (NYSE) |
| `fct_iv_surface` | (ticker, snapshot_date, expiry, option_type, moneyness_bucket) | Mean IV — the volatility smile/skew and term structure (NYSE) |
