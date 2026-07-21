# Roadmap & project state

**Updated 2026-07-21.** What exists today, how it actually performs, and what comes next.
For *how* it was built and every bug paid for along the way, see
[development-history.md](development-history.md); for design rationale see [adr/](adr/).

## What this project is

A local-first, zero-cost MLOps platform for a self-adapting ML investing model. Dagster
orchestrates daily ingest → features → champion scoring → paper portfolio → drift checks;
weekly and drift-triggered retraining promotes challengers through the MLflow registry;
dbt builds analytics marts; FastAPI serves them; a React dashboard presents the evidence.
Everything runs free on one 16 GB machine via Docker.

**Hard boundary:** this is decision-support tooling. It presents evidence; it does not
give investment advice, and the disclaimer stays.

## Delivered

| # | Milestone | Substance |
|---|---|---|
| M0 | Scaffold | uv + ruff + mypy + pytest + pre-commit, compose, CI, ADRs |
| M1 | Data platform | Alembic schema, yfinance ingest (retries, Stooq fallback), NYSE calendar, quality checks, CLI |
| M2 | ML core | Features, purged walk-forward CV, LightGBM + Optuna, backtester, MLflow registry, promotion gate |
| M3 | Orchestration | Dagster assets/partitions/checks/schedules/drift sensor; full Docker stack (~1.1 GB idle) |
| M4 | API | Read-only FastAPI, DI-overridable for tests |
| M5 | Dashboard | React 19 + Vite + Tailwind 4 + TanStack Query + Recharts, nginx image |
| M6 | Ship | README + screenshot, MIT, Dependabot, public repo, CI green |
| M7 | dbt layer | `transform/` staging + marts, dbt tests in CI, dagster-dbt lineage (group `transform`) |
| M8 | Evidence dashboard | replay-vs-live track record split, SPY benchmark, quintile + risk charts, model audit trail |
| M9 | Options layer | Black-Scholes Greeks, daily chain snapshots, IV-surface/put-call marts, Options tab, hypothetical spread translation |
| M10 | Rigor & reliability | CAPM alpha/beta decomposition (the fair read on a market-neutral book), pipeline failure alerts, automatic missed-day catch-up |

**Quality gates:** 114 Python tests (unit + integration against a disposable database that
runs a real `dbt build`), 30 Vitest, 53 dbt data tests, plus mypy / ruff / eslint / tsc /
compose validation — all enforced in CI.

## Current state

- **Data:** 107,350 price bars (from 2018-01-02), 104,200 feature rows, 104,200
  predictions, 2,083 portfolio snapshots, 35,291 option quotes across all 50 tickers.
- **Champion:** `quantpulse-lgbm` v1, promoted 2026-07-18 (holdout IC 0.026, Sharpe 0.21).
- **Honest performance:** over the full 8.5-year replay the strategy returns **+20.5%
  (Sharpe 0.26) and underperforms SPY buy-and-hold.** The live out-of-sample record began
  2026-07-18 — that, not the replay, is the number worth judging.
- **Signal quality:** quintile forward returns are monotonic (Q1 ≈ 24.9bp → Q5 ≈ 0.4bp)
  across the replay window: real ranking skill, modest in magnitude.

## Open finding: horizon mismatch between the model and the paper book

`quantpulse sensitivity` sweeps the backtest across trading-cost and short-borrow
assumptions. Two things came out of the first run, and the second matters more:

- **Costs are not what's holding the strategy back.** On the monthly-rebalanced
  backtest the result degrades gracefully — 17.2% annualized at zero cost, still ~10%
  at a punitive 1% round trip plus 3% borrow. Breakeven round-trip cost is ~1%, far
  above realistic levels for liquid large caps.
- **But that backtest and the live paper book are not the same strategy.** The model
  forecasts **21-day** forward returns, and the backtest holds positions for roughly
  that long. The paper portfolio (`ml/portfolio.py`) rebalances **daily** and realizes
  the **next day's** return — using a 21-day signal to bet on tomorrow. That mismatch is
  the leading suspect for why the paper book shows ~0.26 Sharpe and negative alpha while
  the horizon-matched backtest looks far healthier.

**Caveat that keeps this honest:** the sensitivity run scores the champion over its own
training window, so those figures are largely *in-sample*. The champion's true holdout
Sharpe was 0.21. Do not read 1.33 as a real edge — read it as evidence that the two
constructions disagree, which is a question about design, not about alpha.

Next step when picking this up: decide deliberately whether the paper book should hold
positions for the model's horizon (or the model should forecast a 1-day target), then
re-measure. Do not tune anything until the horizons agree.

## Operating notes

- `make up` (fast, reuses images) · `make build` after code changes · `make down`.
- Ports: Dagster 3000 · MLflow **5001** (macOS AirPlay owns 5000) · API 8000 ·
  dashboard 8080 · Postgres 5432 (database `market`).
- Schedules run **only while the stack is up**: weekday 18:30 ET ingest, 19:00 ET
  processing, Saturday 09:00 ET retrain, plus a drift-triggered retrain sensor.
- **Options snapshots must run post-close.** Measured on the same universe: post-close
  averages ≈33% ATM IV (realistic) versus ≈2.1% pre-market (stale, untraded contracts).
  A full 50-ticker snapshot takes ~10 minutes and commits per ticker, so it is safe to
  interrupt and simply re-run.
- Missed days are safe: ingestion is idempotent and partitioned — re-materialize the
  affected partitions in the Dagster UI.

## Next

1. **Let it run.** The live track record and the options history only accrue with time;
   no code substitutes for weeks of scheduled runs. Highest value, zero effort.
2. **Refresh the README screenshot** after the next retrain, once the on-screen numbers move.
3. **Options history analytics** — once ~20+ snapshots exist: IV rank/percentile,
   realized-vs-implied volatility, IV-change signals. This is the payoff for the
   snapshot-forward design, and it needs no new data source.
4. **Model improvements** — only once live evidence justifies them: richer features
   (fundamentals, cross-asset), alternative targets, or an ensemble. Measure first.
5. **Deferred dependency majors** — typescript / eslint / recharts carry documented
   Dependabot ignore rules; Docker base-image majors are declined because CI does not
   build images; dbt `tests:` → `data_tests:` rename when the tooling requires it.
6. **Databricks Free Edition companion repo** — the same pipeline expressed in
   PySpark/Delta as a separate portfolio piece. Spark was deliberately *not* used here:
   the data is far too small to justify it, and being able to say so is the stronger
   engineering signal.

## Why options work the way they do

Free option data is **live-only** — yfinance gives full chains but no history, and real
historical chains cost thousands per year. So options are not a backtested strategy here;
they are an analytics layer that **builds its own history forward**, one daily snapshot at
a time. In a few weeks that becomes a dataset genuinely worth analysing, which is also why
keeping the scheduled runs alive is the single highest-value thing to do.
