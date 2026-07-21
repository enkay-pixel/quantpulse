# Runbook

## Daily operation

```bash
make up      # start everything (idempotent); schedules run while the stack is up
make ps      # health overview
make logs    # tail logs
make down    # stop everything; data survives in Docker volumes
```

The stack is designed to be **spun up when you want it working in the background** and shut down when you don't — schedules catch up via Dagster backfills/partitions when the stack was off.

## Connecting DBeaver

Create a **PostgreSQL** connection with exactly these settings (values come from your `.env`):

| Field | Value |
|---|---|
| Host | `localhost` |
| Port | `5432` |
| **Database** | `market` ← DBeaver defaults this field to `postgres`; change it or you'll see empty/unrelated schemas |
| Username | `POSTGRES_USER` from `.env` (default `quantpulse`) |
| Password | `POSTGRES_PASSWORD` from `.env` |

Tick **"Show all databases"** on the PostgreSQL tab of the connection dialog to browse all three databases from one connection. Tables live under *database ▸ Schemas ▸ public ▸ Tables*.

### What lives where

| Database | Contents |
|---|---|
| `market` | The platform's data: `prices`, `features`, `predictions`, `portfolio_snapshots`, `model_runs`, `drift_metrics`, `universe` |
| `mlflow` | MLflow's backend store — model registry metadata is in `registered_models`, `model_versions`, `registered_model_aliases` (the `champion` alias lives here), run metrics in `metrics`/`params` |
| `dagster` | Dagster's run/event storage (internals; rarely useful to browse) |

The trained model **files** (pickled LightGBM boosters) are not in Postgres — they're artifacts in the `mlflow-artifacts` Docker volume, browsable through the MLflow UI (http://localhost:5001 → Model training → Models) which links each version to its artifacts and metrics.

## Resetting state

| What | How |
|---|---|
| Wipe all data (prices, runs, models) | `docker compose down -v` (deletes volumes) then `make up` |
| Re-run a slice of ingestion | Dagster UI → Assets → `raw_prices` → Materialize with a partition range (backfill) |
| Force a retrain | Dagster UI → Jobs → training job → Launch run |

## Options snapshots: run them after the close

Yahoo's implied-volatility field is only trustworthy when the market has been trading.
Measured on the same universe: a snapshot taken after the close averaged **33% ATM IV**
(range 11–52%, realistic), while one taken pre-market at ~3:30am ET averaged **2.1%**
(range 1.6–6.3%, junk — stale contracts with no recent trades). The scheduled pipeline
runs post-close, which is correct; avoid drawing conclusions from ad-hoc overnight runs.
Because the grain includes `snapshot_date`, a later same-day run simply overwrites the
bad rows.

A full 50-ticker snapshot takes ~10 minutes (500 network calls). It commits per ticker,
so interrupting it is safe and it can simply be re-run.

## Failure alerts & missed-day catch-up

Two sensors keep the pipeline honest without any paid service:

- **`pipeline_failure_alert`** — a Dagster run-failure sensor appends every failure to
  `$DAGSTER_HOME/alerts.jsonl` (surfaced at `GET /alerts`) and fires a macOS desktop
  notification when running outside a container. Without it a broken evening run is only
  noticed days later via stale dates on the dashboard.
- **`missed_partition_catchup_sensor`** — every 30 minutes it compares expected NYSE
  sessions over the last 30 days against actual price coverage and requests the missing
  daily partitions (max 3 per tick so a long sleep can't stampede the queue). A session
  counts as ingested only above 80% universe coverage, so a partially-written day is
  retried rather than treated as done.

Check both from the Dagster UI (Automation → Sensors) or `GET /alerts`.

Note: yfinance returns a *partial* bar for the current session during market hours, so an
intraday ingest stores a mid-session price. The scheduled post-close run upserts the true
close over it — self-healing, no action needed.

## Troubleshooting

- **Containers won't start / Docker not found**: open Docker Desktop first (`open -a Docker`), wait for the whale icon, retry `make up`.
- **yfinance rate limiting**: ingestion retries with backoff and falls back to Stooq; a partition that still fails can be re-materialized later — the pipeline is idempotent (upserts).
- **Memory pressure**: `docker stats` to inspect; every service carries a compose memory limit. Cap Docker Desktop at ~6 GB (Settings → Resources).
