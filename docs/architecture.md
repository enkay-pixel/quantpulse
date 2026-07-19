# Architecture

## Services (docker compose)

| Service | Purpose | Port | Memory cap |
|---|---|---|---|
| `postgres` | 3 databases: `market` (app data), `dagster` (orchestrator storage), `mlflow` (tracking backend) | 5432 | 512M |
| `dagster-webserver` + `dagster-daemon` | Pipeline UI; schedules/sensors/run launcher. Both load the code location in-process from the shared image (one fewer container than a gRPC code server — deliberate on 16 GB) | 3000 | 768M + 1.5G |
| `mlflow` | Experiment tracking + model registry (single worker) | 5001→5000 | 768M |
| `api` | FastAPI serving layer | 8000 | 384M |
| `web` *(M5)* | React dashboard behind nginx | 8080 | 128M |

Total idle footprint target: **≤ 2.5 GB**, sized for a 16 GB MacBook with Docker Desktop capped at ~6 GB.

## Data flow

1. `raw_prices` (daily-partitioned Dagster asset) pulls OHLCV bars from yfinance (Stooq fallback) and upserts into `market.prices`.
2. `features` computes technical + cross-sectional features into `market.features`.
3. `predictions` loads the MLflow registry model aliased `@champion` and scores the latest features.
4. `portfolio_equity` maintains a simulated long/short book from predictions for the dashboard.
5. `drift_report` (Evidently) compares recent feature/prediction distributions against the champion's training reference.

## Transform layer (dbt)

SQL analytics live in a dbt project at `transform/`: staging views (1:1 over raw tables)
and marts in the `analytics` schema — `fct_daily_returns`, `fct_signal_performance`
(signal-quintile forward returns: the plainest read of model skill), `fct_portfolio_daily`
(cumulative return + drawdown), and `dim_universe`. dbt tests add a second data-quality
layer, and `dagster-dbt` mounts every model into the same asset graph (group `transform`),
scheduled with the daily processing job. Sources map to upstream Dagster assets via
`meta.dagster.asset_key`, so lineage runs unbroken from yfinance to the marts.
Run locally with `make dbt-build`; browse docs + lineage with `make dbt-docs`.

## Evidence layer

The dashboard's job is to make the strategy *auditable*, not to sell it. The dbt marts
split performance into an in-sample `replay` phase and the `live` out-of-sample record
that starts at the first champion promotion (`fct_portfolio_daily.phase`,
`fct_track_record`), benchmark it against SPY buy-and-hold
(`fct_portfolio_vs_benchmark`), and expose signal-quintile forward returns
(`fct_signal_performance`). The API serves these plus the current paper book and the
full `model_runs` audit trail; the React app renders them across three tabs
(Overview / Evidence / Model & Book). All endpoints degrade to empty payloads on a
fresh database before the first dbt build.

## The adaptation loop

- **Weekly schedule** (and a **drift sensor**) trigger the training job: purged/embargoed time-series CV, Optuna hyperparameter search (capped trial budget), final LightGBM fit, all logged to MLflow.
- The candidate is evaluated on a holdout backtest (Sharpe, max drawdown, information coefficient).
- Promotion logic assigns the `@champion` alias only if the candidate beats the incumbent by a configured margin — otherwise the champion stays. Every decision is recorded in `market.model_runs`.

## Package layout

Single installable package `quantpulse` (src layout). Dagster definitions live in `quantpulse.orchestration` and import the same modules the API uses — pipeline code is plain, testable Python; Dagster assets are thin wrappers.

## Why these tools

See [adr/](adr/) — notably [0002](adr/0002-consolidate-two-prototypes.md) (consolidation) and [0003](adr/0003-orchestrator-and-stack-choices.md) (Dagster, React+FastAPI, zero-cost constraints).
