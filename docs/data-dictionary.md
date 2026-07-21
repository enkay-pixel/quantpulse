# Data dictionary — `market` database

Populated from M1 onward; columns finalized alongside the Alembic migrations.

| Table | Grain | Purpose |
|---|---|---|
| `universe` | ticker | Tradable universe with metadata (name, type stock/etf, active flag) |
| `prices` | (ticker, date) | Daily OHLCV bars, adjusted; source column (yfinance/stooq) |
| `features` | (ticker, date) | Engineered features used for training and scoring |
| `predictions` | (ticker, date, model_version) | Champion-model forward-return scores |
| `model_runs` | run id | Training/evaluation/promotion audit log (metrics, decision, MLflow run id) |
| `drift_metrics` | (date, metric) | Evidently drift results per feature set |
| `portfolio_snapshots` | date | Simulated long/short book equity, exposure, turnover |
| `option_quotes` | (snapshot_date, ticker, expiry, strike, option_type) | Daily live option-chain snapshots + Black-Scholes Greeks. Accumulates forward — no free history exists to backfill |

## `analytics` schema (dbt-managed — see `transform/`)

| Relation | Grain | Purpose |
|---|---|---|
| `stg_*` (views) | 1:1 with raw | Typed, renamed staging over the raw tables; `stg_predictions` dedupes to newest model version |
| `fct_daily_returns` | (ticker, date) | Simple returns + 21-day rolling volatility/mean |
| `fct_signal_performance` | (date, signal_quintile) | Next-day realized return per signal quintile (1 = strongest) — model-skill readout |
| `fct_portfolio_daily` | date | Portfolio with cumulative return, running drawdown, rolling 63d Sharpe, and evidence `phase` (replay/live) |
| `fct_portfolio_vs_benchmark` | date | Strategy equity vs SPY buy-and-hold indexed to the portfolio's first date |
| `fct_track_record` | phase | Per-phase performance summary — the `live` row is the honest out-of-sample record |
| `dim_universe` | ticker | Members with price-coverage metadata |
| `fct_option_summary` | (ticker, snapshot_date) | ATM implied volatility and put/call open-interest ratio |
| `fct_iv_surface` | (ticker, snapshot_date, expiry, option_type, moneyness_bucket) | Mean IV — the volatility smile/skew and term structure |
