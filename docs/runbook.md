# Runbook

## Daily operation

```bash
make up      # start everything (idempotent); schedules run while the stack is up
make ps      # health overview
make logs    # tail logs
make down    # stop everything; data survives in Docker volumes
```

The stack is designed to be **spun up when you want it working in the background** and shut down
when you don't — schedules catch up via Dagster backfills/partitions when the stack was off.

## Connecting DBeaver

Create a **PostgreSQL** connection with exactly these settings (values come from your `.env`):

| Field | Value |
|---|---|
| Host | `localhost` |
| Port | `5432` |
| **Database** | `market` ← DBeaver defaults this field to `postgres`; change it or you'll see empty/unrelated schemas |
| Username | `POSTGRES_USER` from `.env` (default `quantpulse`) |
| Password | `POSTGRES_PASSWORD` from `.env` |

Tick **"Show all databases"** on the PostgreSQL tab of the connection dialog to browse all three
databases from one connection. Tables live under *database ▸ Schemas ▸ public ▸ Tables*.

### What lives where

| Database | Contents |
|---|---|
| `market` | The platform's data: `prices`, `features`, `predictions`, `portfolio_snapshots`, `model_runs`, `drift_metrics`, `universe` |
| `mlflow` | MLflow's backend store — model registry metadata is in `registered_models`, `model_versions`, `registered_model_aliases` (the `champion` alias lives here), run metrics in `metrics`/`params` |
| `dagster` | Dagster's run/event storage (internals; rarely useful to browse) |

The trained model **files** (pickled LightGBM boosters) are not in Postgres — they're artifacts in
the `mlflow-artifacts` Docker volume, browsable through the MLflow UI (<http://localhost:5001> →
Model training → Models) which links each version to its artifacts and metrics.

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

- **`pipeline_failure_alert`** — a Dagster run-failure sensor records every failure in the
  `pipeline_alerts` table (surfaced at `GET /alerts`, capped at the newest 200) and fires a
  macOS desktop notification when running outside a container. Without it a broken evening
  run is only noticed days later via stale dates on the dashboard. It records alerts from
  the daemon while the API serves them from another container, which is why the log lives
  in Postgres and not a file — see incident 25.
- **`missed_partition_catchup_sensor`** — every 30 minutes it compares each market's
  expected sessions over the last 30 days against actual price coverage and requests the
  missing daily partitions (max 3 per tick so a long sleep can't stampede the queue). A
  session counts as ingested only above 80% universe coverage, so a partially-written day
  is retried rather than treated as done. Today only joins the expected window once its
  scheduled ingest time is past (the exchange date flips at midnight, hours before
  trading), and retries are budgeted from Dagster's run history with attempt-numbered
  run_keys — max 3 runs that actually reached the feed per session, never a reused key.

Check both from the Dagster UI (Automation → Sensors) or `GET /alerts`.

Note: yfinance returns a *partial* bar for the current session during market hours, so an
intraday ingest stores a mid-session price. The scheduled post-close run upserts the true
close over it — self-healing, no action needed.

## Backups

```bash
make backup                 # -> ~/quantpulse-backups/market-YYYY-MM-DD.sql.gz
```

Most of `market` is rebuildable — prices re-download, features recompute, models retrain.
Two things are not, and they are why backups exist: **`option_quotes`** (live-only chains;
a day not captured is gone permanently) and the **live record** in `portfolio_snapshots` /
`predictions` (recreating it would mean re-scoring history with today's champion — the
retroactive rewrite the promotion gate exists to prevent). The whole database is dumped
regardless: ~48 MB gzipped, and a single-file restore beats reasoning about foreign-key
order at the moment you need it.

Runs daily at 07:00 via launchd, after every overnight job — the option-capture window
runs until ~06:00, so an earlier backup would routinely miss the irreplaceable table.
Keeps 14 days. Dumps are written to `.partial` and verified with `gzip -t` before being
renamed, so an interrupted dump never sits there looking valid.

To restore into a running stack:

```bash
gzcat ~/quantpulse-backups/market-YYYY-MM-DD.sql.gz | docker exec -i quantpulse-postgres psql -U quantpulse -d market
```

## Host agents (launchd)

Six scheduled jobs on the dev machine. Each keeps only its *schedule* in
`~/Library/LaunchAgents/com.quantpulse.*.plist`; the logic lives in `scripts/` or the
Makefile, so changing behaviour is a code change with a diff. All log to
`~/Library/Logs/quantpulse-*.log`.

(Other `com.quantpulse.*` agents exist on this machine — `stack-check`, `secret-scan`,
`wake-digest` and friends — but their scripts live in `~/.claude/scripts/` and belong to the
separate agent fleet, not this repo. The ones below are the ones a fresh clone can restore.)

| Agent | When | Does |
|---|---|---|
| `backup` | 07:00 daily | Dumps `market`, keeps 14 |
| `jse-close` | 19:47 weekdays | Checks today's JSE session landed and no benchmark bar is missing, after the 19:30 ingest |
| `retrain-check` | Sat 17:37 | Reports the weekly retrain's outcome per market — decision, candidate IC, and the incumbent and baseline it had to beat |
| `readiness` | 21:45 weekdays | Warns if the stack is down or on battery, 15 min before the option window |
| `power` | every 2h | Warns only when sleep is disabled **and** on battery — the combination that runs the machine flat |
| `prune-cache` | Sun 03:00 | Reclaims Docker build cache, keeps the uv wheel cache |

`jse-close` exists for the failure the others cannot see. A session that never ingests is
loud; a session that ingests *almost* completely is silent — STX40.JO alone went missing on
2026-08-11, which is 1/29th of coverage and trips no threshold, while the CAPM marts
inner-join it and lost the whole day. Nobody noticed for two days. It reports rather than
repairs: the catch-up sensor already retries a missing benchmark on its own, and re-fetching
from a script is how a misdated bar gets written (see data-dictionary.md). It also stays
quiet before 19:30, since until the schedule has had its turn an absent session is not a
missed one — the same `ingest_overdue` distinction the sensor draws.

The checks notify but never act: bringing the stack up automatically would override a
deliberate `make down` before travel. Disable any of them with
`launchctl bootout gui/$(id -u)/com.quantpulse.<name>`.

## Rolling back a promotion

```bash
quantpulse demote --exchange XJSE --reason "loses to the momentum baseline" --dry-run
quantpulse demote --exchange XJSE --reason "loses to the momentum baseline"
```

Withdraws a version's promotion and moves `@champion` to the newest promotion with no later
demotion; if there is none, the alias is cleared and that market stands down rather than
serving a model judged unfit. `--reason` is required and lands in the audit row — a demotion
with no recorded cause makes the next incident harder to read. Always dry-run first: it
resolves the fallback and prints the plan without touching either record.

Two writable records are involved (MLflow's alias, Postgres' audit trail) and no transaction
spans them, so the order is deliberate: the audit row is written, the alias is moved, and only
then is the transaction committed. A registry failure rolls the row back and nothing moved.
The one unprotected window is a commit failing *after* the alias moved; that logs CRITICAL,
and `champion_registry_agrees` reports the disagreement until it is reconciled.

Demotion is manual on purpose. Deciding a champion should be withdrawn needs a judgement the
pipeline cannot make — the promotion gate prevents a bad model being *installed*, not a model
that has since been shown up.

## Reclaiming Docker build cache

```bash
make prune-cache
```

Repeated `make build` accumulates BuildKit layer cache without bound — 20 GB over ten days
of this project's rebuilds. This reclaims it while **keeping the uv wheel cache**
(`type=exec.cachemount`, ~1 GB): that cache is what lets a rebuild resume downloads instead
of restarting ~200 wheels, which is the difference between a 3-minute build and an
all-night one on a bad connection.

Scheduled weekly on the dev machine via a launchd agent
(`~/Library/LaunchAgents/com.quantpulse.prune-cache.plist`, Sundays 03:00, logging to
`~/Library/Logs/quantpulse-prune-cache.log`). Only the *schedule* lives there — it invokes
this make target, so what gets pruned stays a code change. Disable with
`launchctl bootout gui/$(id -u)/com.quantpulse.prune-cache`.

The in-container `resource_report` deliberately cannot see any of this: it has no Docker
socket by design, and monitors database growth instead.

## Checking whether costs would kill the strategy

```bash
quantpulse sensitivity
```

Sweeps the backtest across round-trip trading cost and annualized short-borrow rate,
printing annual return / Sharpe / max drawdown per combination plus the breakeven
round-trip cost. Shorting is charged a borrow fee (default 1%/yr on the short leg) —
it was previously modeled as free.

Read the output with the caveat in [roadmap.md](roadmap.md): replay scoring covers the
champion's own training window, so the figures are largely in-sample.

## Comparing the paper books

```bash
curl -s localhost:8000/portfolio/books | jq
```

Two books run over the same predictions and differ only in how often they rebalance
(`daily` vs `horizon`, every 21 trading days). The comparison shows annualized return,
Sharpe, drawdown, mean turnover and the annualized cost drag for each. Rebuilt whenever
`portfolio_equity` materializes; the dashboard continues to show the `daily` book.

If you add a book, change **only** `rebalance_days` in
`quantpulse.ml.portfolio.BOOKS` — a unit test fails if any other field diverges,
because a book that differs in two ways cannot attribute its own results.

## Dates are exchange dates, not container dates

Containers run UTC; the market runs on New York time. Anything stamping a row with "today"
must use `quantpulse.data.calendar.market_today()`, never `dt.date.today()`.

Why it matters, and why it hides: under **EDT** the 19:00 ET jobs land at 23:00 UTC and
both clocks give the same date, so a naive `date.today()` looks correct all summer. Under
**EST** the same job lands at **00:00 UTC** — and every row it writes would be stamped with
*tomorrow's* date. At the November DST change the entire options history would quietly
shift by a day, in the one dataset that cannot be rebuilt.

A related artefact already exists: on 2026-07-22 a run interrupted by a Docker restart
crossed UTC midnight mid-snapshot, so 25 tickers holding **07-22 post-close** marks are
stamped `2026-07-23`. Their IV is healthy (median 0.366 against 0.370 for 07-22) — real
data, wrong label. The upsert key includes `snapshot_date`, so the next full 07-23 snapshot
overwrites them contract-for-contract; only contracts that expired in between linger. Left
alone deliberately rather than deleted: it is real market data, and the retention rule for
`option_quotes` is that it is irreplaceable.

## Options snapshot quality

The `option_snapshot_quality` asset check runs with `option_chains` and fails the
snapshot when ticker coverage is thin, median IV among *traded* contracts is implausible
(the pre-market staleness signature), no contracts carry open interest, or Greeks are
missing. Non-blocking — it flags rather than halts, since a partial snapshot is still
worth keeping. See it in the Dagster UI under the asset's checks.

`option_snapshot_repair_sensor` then re-runs a thin snapshot automatically, up to 3
times a day. **It only repairs today.** Option chains are live-only, so a day that ended
under-covered is a permanent hole in the dataset — re-running tomorrow would just
snapshot tomorrow. (This is not hypothetical: 2026-07-20 captured 5 of 50 tickers before
being interrupted, and those 45 are gone.) If you see a thin day, fix it *that day*.

## Resource headroom

The `resource_report` asset runs with the daily processing job and reports **runway in
days**, not bytes — bytes mean nothing without a rate. Dagster charts its metadata over
time, so the trend is visible in the asset's page with no metrics stack involved. The
`resource_headroom` check (non-blocking) fails when runway drops below 90 days or any
container exceeds 85% of its cap, which it reads from its own cgroup rather than a
hardcoded number, so raising a limit in `docker-compose.yml` is picked up automatically.

Measured 2026-07-22: the market database is **180 MB** growing **~8 MB/day**, essentially
all of it `option_quotes`. Everything else adds ~50 rows/day per table. That is roughly
**2 GB/year against 277 GB free** — decades of runway. If the check ever fires, the fix is
almost always to raise a cap, not to delete data.

## Data retention

Only one thing here is on a rolling window, and it is deliberate.

| Data | Policy | Why |
|---|---|---|
| Dagster sensor / schedule ticks | **14 / 90 days** (`docker/dagster.yaml`) | Pure operational exhaust. Sensors tick every 30s–30min; after a fortnight they answer no question anyone asks. |
| `option_quotes` | **Never delete** | Irreplaceable. yfinance serves live chains only, and historical chains cost thousands a year. A day deleted is a day that cannot be bought back at any price. |
| `prices` | Never delete | Backfillable in principle, but it is the base every other table is derived from, and it grows ~50 rows/day. |
| `features`, `predictions`, `portfolio_snapshots` | Never delete | Recomputable from prices, but they are what the replay curve is built from, and together they grow under 30 KB/day. Deleting them costs the dashboard its history to reclaim nothing. |
| `model_runs`, MLflow registry | Never delete | The champion/challenger audit trail is the point of the self-adapting loop. Tiny. |

The instinct to age out old data is right for logs and wrong for this platform: **the
tables large enough to be worth deleting are exactly the ones that cannot be recreated,
and the tables that are safe to delete are too small to be worth it.** Revisit only if
`resource_headroom` actually fires — and even then, archive `option_quotes` to Parquet
before considering removal.

## After stopping Docker mid-run

Runs execute in-process under the daemon, so killing Docker while one is in flight leaves
its row `STARTED` forever — the process died before it could write a terminal status. With
`max_concurrent_runs: 1` that zombie holds the only slot and **the entire queue stalls
indefinitely**, and because `STARTED` is not `FAILURE` the failure sensor never fires: the
pipeline is dead and nothing says so.

`run_monitoring` (in `docker/dagster.yaml`) now reaps these automatically. To confirm after
an unclean shutdown:

```bash
docker compose exec -T postgres psql -U quantpulse -d dagster -c "select status, count(*) from runs group by 1;"
```

Anything `STARTED` with no matching process, or a `QUEUED` pile-up, means the queue is
blocked. Terminate the stuck run from the Dagster UI (Runs → Terminate) or via GraphQL with
`terminateRun(runId: "...", terminatePolicy: MARK_AS_CANCELED_IMMEDIATELY)`; the queue
drains on its own afterwards.

**Prefer `make down` to quitting Docker Desktop** — it stops runs cleanly and avoids the
whole situation.

## Troubleshooting

- **Containers won't start / Docker not found**: open Docker Desktop first (`open -a Docker`), wait
  for the whale icon, retry `make up`.
- **yfinance rate limiting**: ingestion retries with backoff and falls back to Stooq; a partition
  that still fails can be re-materialized later — the pipeline is idempotent (upserts).
- **Memory pressure**: `docker stats` to inspect; every service carries a compose memory limit. Cap
  Docker Desktop at ~6 GB (Settings → Resources).
