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
incident log with root causes, milestone-by-milestone history, current model
and data metrics, dependency-policy decisions, testing architecture, and owner
preferences. This file stays lean on purpose; that one is the deep archive.

**Hard boundary**: this is decision-support tooling. Never generate personalized
buy/sell/allocation advice; keep the "not investment advice" framing intact.

## Map

- `src/quantpulse/`: `data/` (ingest, calendar, quality) · `features/` · `ml/`
  (cv, training, backtest, metrics, registry, promotion, portfolio, sensitivity,
  pipeline) ·
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
  IC ≥ 0, DD > −35%, and a **first** champion must clear `min_first_sharpe` (0.0) —
  without it a model that lost money out-of-sample becomes the dashboard's champion.
  Champions: XNYS v1 (IC 0.026 / Sharpe 0.21), XJSE v3 (IC 0.063 / Sharpe 1.51). Those are
  **what each was promoted on, not comparable across models** — both predate the gate fix,
  and on 2026-08-01 XNYS v1 re-scored 2.570 on that run's holdout against its stored 0.205.
  Never compare a stored Sharpe to a fresh one; the gate re-scores instead.
- Quantile width is per-market, set from breadth so books hold a comparable NUMBER of
  positions: 20% of 50 US names and 35% of 29 JSE names are both ~10 per side. The
  promotion gate backtests at the market's own width, or it judges a book nobody runs.
  The gate **re-scores the incumbent on the candidate's exact holdout** at decision time
  — never trust stored metrics across code/panel changes (incident 24: a backfill grew
  the panel, the fractional holdout slid into a momentum-rich stretch, and a no-better
  candidate auto-promoted at Sharpe 1.89). Final fits early-stop on an inner split, and
  each model_runs row records its holdout window.

## Environment & commands

- Python venv is SHARED at `../../.venv` (monorepo root). Never create a local one;
  `make install` syncs it via uv. Node from Homebrew.
- QA loop: `make fmt lint type test` · `make test-all` (integration; needs stack up) ·
  `cd web && npm run lint && npm run test && npm run build` · `make dbt-build`.
- Stack: `make up` / `make down` (docker compose; Docker Desktop must be running).
- First-run seed on empty DB: `make bootstrap`.
- Analysis: `quantpulse sensitivity` sweeps backtest cost x short-borrow and reports the
  breakeven round-trip cost (`inf` = still profitable at the harshest cost tested, i.e.
  not measured — never quote the grid ceiling as a breakeven). Note the open
  horizon-mismatch finding in docs/roadmap.md (21-day model signal vs daily paper-book
  rebalancing) — resolve before tuning anything. Replay numbers carry survivorship bias
  (universe is today's 50 survivors back to 2018): treat them as an upper bound. Full
  caveat list: "Known biases in the replay" in docs/roadmap.md.
- Options snapshots are guarded by the `option_snapshot_quality` asset check (coverage,
  plausible median IV among traded contracts, Greeks present).
- Ports (**loopback-only** — Dagster/MLflow have no auth and the laptop roams networks;
  an exposed MLflow lets anyone swap the champion the pipeline deserializes):
  Dagster 3000 · MLflow **5001** (AirPlay owns 5000; in-network mlflow:5000) ·
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
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. Pre-commit hooks installed —
  incl. gitleaks (222 rules) over every staged diff, since this repo is public and a
  leaked token must be *rotated*, not force-pushed away. False positives go in
  `.gitleaks.toml` narrowly scoped to rule + path + line pattern, never as a blanket skip.
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
- Killing Docker mid-run leaves a zombie `STARTED` run; with `max_concurrent_runs: 1` it
  blocks the queue forever AND is invisible to the failure sensor (STARTED ≠ FAILURE).
  `run_monitoring` in docker/dagster.yaml reaps it; prefer `make down` over quitting Docker.
- Option chains are gated on `is_post_close()` **inside `snapshot_option_chains()`**, so
  every caller inherits it — pre-market IV is ~2.1% vs ~33% post-close, and because the
  upsert is keyed on `(snapshot_date, ticker, …)` an off-hours run OVERWRITES good rows
  with junk. It raises `OffHoursSnapshotError`; `--force` is for off-hours testing against
  a throwaway date only. The gate used to live only in the repair sensor, which left the
  CLI and manual Dagster materializes free to corrupt a day. Don't push it back up into
  the callers: a rule each scheduling path must remember is one a new path won't.
- Scoring fills **every unscored feature date** in a 30-day window, not just the newest —
  a late/rescued ingest is never the max again, so it would go unscored forever (incident
  26). Never re-score a date an earlier champion already scored: the marts take the newest
  model version per date, so it silently rewrites the live record. Freshness checks that
  compare *maxima* answer "has it stopped?", never "did it skip?" — count gaps too.
- Cross-container state goes in **Postgres**, never a file under `DAGSTER_HOME`: that path
  is per-container and not a volume, so the API cannot read what the daemon writes and
  `compose up` erases it (incident 25 — failure alerts were invisible for weeks). Verify
  observability from the *consumer's* process, not the producer's.
- Sensor `run_key`s are deduplicated by Dagster **forever** — never give a retryable
  rescue a fixed key (one premature/failed attempt strands it for good). Budget from run
  history and suffix the attempt number; only runs with a `start_time` spend budget
  (`catchup.next_ingest_attempt` / `summarize_capture_runs`). Also: the exchange date
  flips at midnight, so "today" is not a *missed* session until `catchup.ingest_overdue`.
- **Never `dt.date.today()`** — containers run UTC. Use `calendar.market_today()` (exchange
  time). Under EDT the 19:00 ET jobs are 23:00 UTC and the two agree; under EST they are
  00:00 UTC and naive UTC stamps rows with *tomorrow*, shifting options history by a day at
  the November DST change. Latent all summer, so tests pin both sides.
- Docker CLI lives in `/opt/homebrew/bin`, symlinked into `/Applications/Docker.app`, so
  anything running without a login shell — launchd jobs above all — must put that on PATH
  or `docker` is simply not found. The duplicate `/usr/local/bin` copies pointing at an
  unmounted `/Volumes/Docker` DMG were deleted 2026-07-31: dead since the app moved out of
  its installer image, and unnoticed for months precisely because `/opt/homebrew/bin`
  precedes them on PATH and a dangling symlink is not executable, so `which` skips it.
- `pre-commit run gitleaks --all-files` is a **no-op that always passes** — the hook's entry
  is `gitleaks git --staged` with `pass_filenames: false`, so pre-commit's file list is
  discarded and an empty index scans nothing. Verify it with a real scan
  (`gitleaks dir . --redact`) or by staging a probe; a green `--all-files` proves nothing.
  Note gitleaks allowlists documentation keys by default, so `AKIAIOSFODNN7EXAMPLE` is
  *also* a false negative — probe with a correctly-shaped random token (AWS access key IDs
  are base32, `[A-Z2-7]`, so a probe containing 0/1/8/9 silently won't match either).

## Standing preference: build both, then measure

When a **feature or strategy** decision has several defensible answers, implement each in
its own context and compare on evidence — do not pick one upfront. (Does NOT apply to
infrastructure or design choices, where one option is simply right; carrying both there is
just debt.) Vary **exactly one dimension** from a shared baseline so the difference is
attributable, give each a first-class identity in the schema, and guard the invariant with
a test. This is why the two-book comparison exists, and it is what showed 85% of the
daily-vs-horizon gap to be trading cost rather than signal decay.

## Paper books (don't collapse them)

`ml/portfolio.py` runs TWO books over the same predictions, stored in
`portfolio_snapshots` keyed by `variant`: `daily` (rebalances daily) and `horizon`
(every 21 days, matching the model's forecast horizon). They must differ in
**rebalance_days only** — a unit test enforces it, because a book differing in two ways
can't attribute its own results. Measured: daily 7.8%/0.73 Sharpe vs horizon
14.4%/1.31, and 85% of that gap is trading cost, not signal decay. dbt + dashboard pin
`variant = 'daily'` (in `stg_portfolio_snapshots`); compare at `GET /portfolio/books`.

## State & near-term ideas

- Live out-of-sample track record accrues weekdays ~18:30/19:00 ET since 2026-07-18
  (dashboard Evidence tab splits replay vs live; judge only the live row).
- Backlog: rename dbt `tests:`→`data_tests:` when tooling nags; Databricks Free Edition
  companion project (same pipeline as PySpark/Delta); richer features/models only after
  live evidence accumulates; options history analytics once ~20+ snapshots exist.
  Screenshots are current as of 2026-07-22 — regenerate via headless Chrome, recipe in
  docs/roadmap.md "Next".
- **Declined, don't re-propose**: a local LLM Q&A layer over the data
  ([ADR 0004](docs/adr/0004-no-llm-question-answering-layer.md)). The `verdict()` functions
  in the React cards ARE the summarization layer — deterministic, unit-tested, cannot
  fabricate a statistic; any safe LLM design just restates them. Ad-hoc questions go to
  DBeaver. Write new explanations as verdict functions, not model calls. Same call as
  declining Spark.
