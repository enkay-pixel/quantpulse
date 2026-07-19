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

## `analytics` schema (dbt-managed — see `transform/`)

| Relation | Grain | Purpose |
|---|---|---|
| `stg_*` (views) | 1:1 with raw | Typed, renamed staging over the raw tables; `stg_predictions` dedupes to newest model version |
| `fct_daily_returns` | (ticker, date) | Simple returns + 21-day rolling volatility/mean |
| `fct_signal_performance` | (date, signal_quintile) | Next-day realized return per signal quintile (1 = strongest) — model-skill readout |
| `fct_portfolio_daily` | date | Portfolio with cumulative return and running drawdown |
| `dim_universe` | ticker | Members with price-coverage metadata |
