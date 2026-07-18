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

## The adaptation loop

- **Weekly schedule** (and a **drift sensor**) trigger the training job: purged/embargoed time-series CV, Optuna hyperparameter search (capped trial budget), final LightGBM fit, all logged to MLflow.
- The candidate is evaluated on a holdout backtest (Sharpe, max drawdown, information coefficient).
- Promotion logic assigns the `@champion` alias only if the candidate beats the incumbent by a configured margin — otherwise the champion stays. Every decision is recorded in `market.model_runs`.

## Package layout

Single installable package `quantpulse` (src layout). Dagster definitions live in `quantpulse.orchestration` and import the same modules the API uses — pipeline code is plain, testable Python; Dagster assets are thin wrappers.

## Why these tools

See [adr/](adr/) — notably [0002](adr/0002-consolidate-two-prototypes.md) (consolidation) and [0003](adr/0003-orchestrator-and-stack-choices.md) (Dagster, React+FastAPI, zero-cost constraints).
