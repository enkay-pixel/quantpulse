# CLAUDE.md — QuantPulse working context

Local-first MLOps platform for a self-adapting ML investing model. Dagster orchestrates
daily ingest (yfinance→Postgres) → features → champion scoring → paper portfolio → drift
checks, weekly + drift-triggered retraining with champion/challenger promotion via
MLflow registry aliases, dbt transforms into an `analytics` schema, FastAPI serving,
React dashboard (tabs: Overview / Evidence / Model & Book). Public repo:
github.com/enkay-pixel/quantpulse. Zero-cost constraint: everything runs free and
local; 16 GB MacBook — stack must idle ≤ ~2.5 GB.

**Start with [docs/roadmap.md](docs/roadmap.md)** for current state, honest performance
numbers, operating notes, and what's next.

**Read [docs/development-history.md](docs/development-history.md) before nontrivial
work** — it holds the full build narrative: why each stack choice was made, the
12-entry incident log with root causes, milestone-by-milestone history, current model
and data metrics, dependency-policy decisions, testing architecture, and owner
preferences. This file stays lean on purpose; that one is the deep archive.

**Hard boundary**: this is decision-support tooling. Never generate personalized
buy/sell/allocation advice; keep the "not investment advice" framing intact.

## Map

- `src/quantpulse/`: `data/` (ingest, calendar, quality) · `features/` · `ml/`
  (cv, training, backtest, metrics, registry, promotion, portfolio, pipeline) ·
  `monitoring/drift.py` · `orchestration/` (Dagster defs + dagster-dbt) · `api/` · `cli.py`
- `src/quantpulse/options/`: `pricing.py` (Black-Scholes + Greeks, market IV) ·
  `ingest.py` (daily live chain snapshots — no free history exists, so this table only
  grows forward) · `strategy.py` (Tier 2 hypothetical spread from the equity signal —
  illustration, never advice)
- `transform/`: dbt project → `analytics` schema (staging views + fct_/dim_ marts,
  incl. fct_track_record's replay-vs-live phase split at first champion promotion)
- `web/`: React dashboard · `docker/`: images · `alembic/`: migrations ·
  `tests/`: unit / integration (disposable market_test DB, real dbt build) / dagster
- Model: LightGBM on 13 technical+cross-sectional features, 21d horizon, purged
  walk-forward CV, Optuna(15), promotion gate = holdout Sharpe ≥ champion+0.05,
  IC ≥ 0, DD > −35%. Champion v1: holdout IC 0.026 / Sharpe 0.21.

## Environment & commands

- Python venv is SHARED at `../../.venv` (monorepo root). Never create a local one;
  `make install` syncs it via uv. Node from Homebrew.
- QA loop: `make fmt lint type test` · `make test-all` (integration; needs stack up) ·
  `cd web && npm run lint && npm run test && npm run build` · `make dbt-build`.
- Stack: `make up` / `make down` (docker compose; Docker Desktop must be running).
- First-run seed on empty DB: `make bootstrap`.
- Analysis: `quantpulse sensitivity` sweeps backtest cost x short-borrow and reports the
  breakeven round-trip cost. Note the open horizon-mismatch finding in docs/roadmap.md
  (21-day model signal vs daily paper-book rebalancing) — resolve before tuning anything.
- Options snapshots are guarded by the `option_snapshot_quality` asset check (coverage,
  plausible median IV among traded contracts, Greeks present).
- Ports: Dagster 3000 · MLflow **5001** (AirPlay owns 5000; in-network mlflow:5000) ·
  API 8000 · dashboard 8080 · Postgres 5432 (DB `market`, creds in `.env`).

## Conventions

- ruff is pinned EXACTLY in pyproject (CI lints from uv.lock — keep venv in sync after
  `uv lock`). mypy strict-ish; pytest markers: `integration` needs live Postgres.
- dbt: `transform/`, profiles via env vars, tests use the `arguments:` nesting,
  package pins in `transform/package-lock.yml` (committed). Marts join the Dagster
  graph via dagster-dbt (group `transform`); sources map with `meta.dagster.asset_key`.
- Frontend: palette/roles as CSS vars in `web/src/index.css` (dataviz method: legends
  for ≥2 series, status colors always icon+label, vendor chunks split).
- Commits: imperative subject, body explains why, trailer
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. Pre-commit hooks installed.
- CI (GitHub Actions): python (ruff/mypy/pytest + Postgres service) · dbt build ·
  web · compose validation. Keep it green; Dependabot weekly with documented major
  ignores (typescript/eslint/recharts) — don't take Docker base-image majors untested.

## Gotchas already paid for (don't rediscover)

- Unanchored `.gitignore` dirs (`data/`) silently exclude same-named src packages from
  git AND hatchling wheels — keep artifact ignores root-anchored (`/data/`).
- Dagster metadata rejects numpy types — cast to Python scalars.
- MLflow 3.x server: `MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false` or it OOMs small
  containers ~1 min after boot.
- Dagster schedules must declare `default_status=RUNNING` (test enforces it).
- SQLAlchemy `stmt.excluded.values` resolves to a method — index as `excluded["values"]`.
- Postgres caps 65,535 bind params/statement — bulk upserts go through
  `quantpulse.utils.chunked`.
- Shell working directory resets between tool calls — always `cd` explicitly.
- Docker CLI symlinks live in `/opt/homebrew/bin` (the `/usr/local/bin` ones point at a
  dead DMG mount).

## State & near-term ideas

- Live out-of-sample track record accrues weekdays ~18:30/19:00 ET since 2026-07-18
  (dashboard Evidence tab splits replay vs live; judge only the live row).
- Backlog: rename dbt `tests:`→`data_tests:` when tooling nags; Databricks Free Edition
  companion project (same pipeline as PySpark/Delta); richer features/models only after
  live evidence accumulates; screenshot refresh when the live curve exists.
