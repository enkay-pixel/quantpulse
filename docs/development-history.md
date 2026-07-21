# Development history & decision log

The full record of how QuantPulse was built (a single intensive agent-assisted session,
2026-07-18 → 2026-07-19), kept so future work doesn't re-derive or re-debug any of it.
Skim the headers; read the section you need.

## Origin

Consolidated from two unplanned prototypes that lived in the `nathan_playground`
monorepo: `advanced_ml_investing` (519-line research monolith: features, purged CV,
LightGBM, torch stubs, Optuna, backtester) and `mlops_investing` (thin scaffold with
MLflow logging, broken docker-compose, AWS/Terraform deploy). Both used outdated APIs
(LightGBM 3.x callbacks, dead `empyrical`, deprecated Optuna). Their final state is
preserved at monorepo commit `3d7d33e`. QuantPulse replaced them as a standalone repo
(gitignored by the monorepo, which still hosts the shared `.venv`).

Stack decisions made with the owner (a data engineer who uses Airflow 3.2.2 at work):

| Decision | Choice | Why |
|---|---|---|
| Orchestrator | **Dagster** over Airflow/Prefect | Asset model fits ML lineage, daily partitions + backfills fit market data, asset checks give data quality, ~half Airflow's RAM; concepts still transfer to Airflow |
| Frontend | **React+FastAPI** over Streamlit | Full-stack portfolio value; serving layer stays reusable |
| Registry | MLflow aliases (`@champion`) | Champion/challenger with an audit trail |
| DB | One Postgres 17, three databases (`market`/`dagster`/`mlflow`) | One container, DBeaver-friendly |
| Dagster topology | webserver + daemon only (code loaded in-process) | One fewer container on 16 GB |
| Dropped in v1 | torch/Transformer/GNN, all cloud deploy | Dependency weight; zero-cost rule (see ADRs 0002/0003) |

## Milestones (each shipped green)

- **M0** scaffold: uv + ruff + mypy + pytest + pre-commit, compose skeleton, CI, docs/ADRs.
- **M1** data platform: Alembic schema (7 tables), yfinance ingestion with tenacity
  retries + Stooq CSV fallback, NYSE calendar (`exchange_calendars`), quality checks,
  CLI (`init-db/sync-universe/backfill/quality`). Verified with a real 2-week backfill;
  the quality gate caught a transient DIS failure, retry healed it.
- **M2** ML core: vectorized features (13 cols, `FEATURE_VERSION v1`), purged
  walk-forward CV (embargo ≥ horizon), metrics module replacing empyrical, LightGBM 4 +
  Optuna (budget 15 trials), quantile long/short backtester, MLflow registry helpers,
  promotion gate. Verified by training a real model end-to-end.
- **M3** orchestration: Dagster assets (daily partitions, `end_offset=1`, NY tz), asset
  checks, schedules, drift sensor; full compose stack (~1.1 GB idle measured);
  E2E in-container: backfill → train → promote v1 → score 50 tickers → 823 snapshots.
- **M4** API: read-only FastAPI, DI overridable for tests.
- **M5** dashboard: Vite/React 19/Tailwind 4/TanStack Query/Recharts, dataviz-method
  charts, nginx image. Verified in-browser.
- **M6** ship: README + screenshot, MIT, Dependabot, pushed to GitHub, CI green after
  three real fixes (see incidents).
- **M7** dbt: `transform/` project (staging + marts + 53 checks), dagster-dbt group
  `transform`, dbt build in CI against service Postgres, manifest baked into images.
- **M8** evidence dashboard: replay-vs-live phase split at first champion promotion,
  SPY benchmark mart, track-record mart, quintile/risk charts, model audit trail,
  positions table, three-tab UI; integration tests run a REAL `dbt build` inside the
  throwaway test DB.

- **M10** rigor & reliability: CAPM alpha/beta decomposition (`fct_alpha_beta`), pipeline
  failure alerts + missed-day catch-up sensors, hash-routed (deep-linkable) dashboard tabs.

## Options data-quality findings (M9/M10, learned the hard way)

Yahoo's option feed is only trustworthy where contracts actually trade, and it fails at
*both* extremes:

- **Near-zero IV** on same-day/untraded contracts made ATM IV read ≈0.00%. Fixed by
  following the ~30-day (VIX) convention with a ≥7-day and IV>0.01 filter.
- **Absurdly high IV** (120–160%) on deep in-the-money contracts with zero open interest
  turned the volatility "smile" into noise spikes at both wings. Fixed by building the
  smile from **out-of-the-money contracts with open interest only**, which is how real vol
  surfaces are constructed; the chain table likewise shows only contracts with OI, sorted
  by liquidity.
- **Timing matters more than anything**: the same universe averaged ≈33% ATM IV post-close
  and ≈36% during market hours, versus ≈2.1% pre-market. Snapshots must run when the
  market has been trading.

## Current model & data snapshot (as of 2026-07-19)

- Universe: 50 tickers (40 stocks + 10 ETFs) in `configs/universe.yaml`; history from
  2018-01-02 → ~107k bars, ~104k feature/prediction rows, ~2,083 portfolio snapshots
  (deepened from 2023+ on 2026-07-20 for multi-regime training). Over the full 8.5-year
  window the replay strategy returns +20.5% (Sharpe 0.26) and clearly *underperforms*
  SPY buy-and-hold — a more honest read than the shorter 2023+ window's +85%. Champion
  v1 was trained on the earlier slice; the next weekly retrain picks up full history.
- Champion: `quantpulse-lgbm` v1. Holdout (out-of-sample): IC 0.026, Sharpe 0.21,
  max DD −5.0%. Replay (in-sample, 823d): +85.63%, Sharpe 1.85, max DD −9.18%,
  win rate 55%. Signal quintiles (replay): avg next-day 24.9 / 8.3 / 6.3 / 5.3 / 0.4 bps
  for Q1→Q5 — perfectly monotonic. Live record accrues from 2026-07-18.
- Promotion policy (`ml/promotion.py`): candidate needs holdout Sharpe ≥ champion+0.05,
  IC ≥ 0, drawdown better than −35%; NaN never promotes; first viable model promotes.
- Training (`TrainConfig`): horizon 21d, 4 splits, embargo 21d, 15 Optuna trials,
  15% holdout, LightGBM early stopping 50.
- Features v1: ret_1/5/21, mom_63, vol_21/63, ma_ratio_21/63, volume_z_21 + cross-
  sectional pct-ranks of ret_5/ret_21/mom_63/ma_ratio_21.
- Drift: scipy KS + PSI per feature (PSI>0.2 = drifted; share≥0.3 triggers the retrain
  sensor); Evidently kept only as best-effort HTML diagnostics.

## Incident log (root causes worth remembering)

1. **Wheel missing a subpackage**: unanchored `.gitignore` entry `data/` matched
   `src/quantpulse/data/` — excluded from every commit AND from the hatchling wheel
   (it honors gitignore). Local editable installs + Docker `COPY src` masked it; GitHub
   was missing 5 files. Fix: root-anchor artifact ignores; files committed.
2. **CI/local lint disagreement**: CI runs ruff from `uv.lock`, the venv had resolved a
   different version. Fix: pin `ruff==` exactly; declare `known-first-party` so import
   sorting never depends on environment inference.
3. **MLflow crash-loop (36 restarts)**: MLflow 3.x job-execution subsystem spawns a
   worker pool ~1 min after boot → OOM at 768M. Fix:
   `MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false`, 1G cap, real healthcheck so
   `restart: unless-stopped` can't hide loops.
4. **Schedules never armed**: Dagster ships schedules STOPPED. Fix:
   `default_status=RUNNING` on all three + a test that forbids stopped schedules.
5. **Postgres bind-param cap**: 22k-row single INSERT blew the 65,535-param limit →
   `utils.chunked` (4k rows) for all bulk upserts.
6. **SQLAlchemy name collision**: `stmt.excluded.values` is the *method*; use
   `excluded["values"]`.
7. **Dagster metadata + numpy**: `numpy.bool_` isn't JSON-serializable — cast scalars.
8. **macOS port 5000**: AirPlay Receiver owns it → MLflow published on 5001.
9. **Docker Desktop resets**: an update switched the image store (containerd) —
   containers/images vanished, *named volumes survived*; `make up` rebuilds. Broken
   `/usr/local/bin/docker` symlinks (dead DMG mount) were replaced in `/opt/homebrew/bin`.
10. **uv-managed lint of new files**: pre-commit's ruff fixed files on first commit —
    normal; re-stage and re-commit.
11. **jsdom lacks ResizeObserver** (recharts) — stubbed in `web/src/test/setup.ts`.
12. **dbt cold-start in CI**: manifest bootstrap must run `dbt deps` before `parse` and
    fail loudly (`orchestration/transform_assets.py`).

## Dependency policy history

Dependabot PR dispositions: action bumps applied directly on main (superseded PRs
auto-closed); python-deps groups merged when green; the 8-major js-deps group was
closed as unresolvable (typescript 7 vs typescript-eslint 8 peer conflict) and replaced
with a curated bump (vite 8, vitest 4, plugin-react 6, jsdom 29) plus documented
`ignore` rules for typescript/eslint/@eslint-js/recharts majors; Docker base-image
majors (node 26, python 3.14) declined because CI doesn't build images — revisit only
as deliberate, tested upgrades.

## Testing architecture

~120 checks total: 87 pytest (unit on synthetic data; integration against a disposable
`market_test` DB created/migrated/dropped per session, truncated per test; evidence
tests seed raw data then run a real `dbt build` in that DB; MLflow registry tests use a
throwaway sqlite backend), 20 Vitest (components + formatters, empty states), 53 dbt
data tests, plus mypy/ruff/eslint/tsc and compose validation — all enforced in CI.

## Owner preferences (established in-session)

Portfolio value matters (clean history, badges, README-first); honesty over flash —
in-sample results must be labeled as such; zero cost is a hard rule; DBeaver is the DB
UI (connect to `market`, not `postgres`); VS Code with ruff as formatter; mssql &
kubernetes extensions are workspace-disabled (project uses neither); Claude must never
give personalized investment advice — the platform presents evidence, the owner decides.
