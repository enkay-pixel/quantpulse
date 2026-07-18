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

- Host `localhost`, port `5432`, database `market`
- User/password: whatever you set in `.env` (`POSTGRES_USER` / `POSTGRES_PASSWORD`)
- Databases `dagster` and `mlflow` exist on the same server (orchestrator/tracking internals).

## Resetting state

| What | How |
|---|---|
| Wipe all data (prices, runs, models) | `docker compose down -v` (deletes volumes) then `make up` |
| Re-run a slice of ingestion | Dagster UI → Assets → `raw_prices` → Materialize with a partition range (backfill) |
| Force a retrain | Dagster UI → Jobs → training job → Launch run |

## Troubleshooting

- **Containers won't start / Docker not found**: open Docker Desktop first (`open -a Docker`), wait for the whale icon, retry `make up`.
- **yfinance rate limiting**: ingestion retries with backoff and falls back to Stooq; a partition that still fails can be re-materialized later — the pipeline is idempotent (upserts).
- **Memory pressure**: `docker stats` to inspect; every service carries a compose memory limit. Cap Docker Desktop at ~6 GB (Settings → Resources).
