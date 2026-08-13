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
- **M9** options layer: daily live chain snapshots + Black-Scholes Greeks, IV-surface /
  put-call marts, Options tab, and a hypothetical signal→spread translation (never advice).
  No free option *history* exists, so the table builds forward from the first run.
- **M10** rigor & reliability: CAPM alpha/beta decomposition (`fct_alpha_beta`), pipeline
  failure alerts + missed-day catch-up sensors, hash-routed (deep-linkable) dashboard tabs.
- **M11** multi-market: `exchange` as a first-class dimension across schema, calendar
  registry, per-`(date,exchange)` partitions, per-market timezone schedules, one champion
  per market, per-market dbt marts, and a dashboard market switcher. JSE added (29 Top-40
  names). Three paper books (`daily`/`horizon`/`long_only`) as variations from a shared
  baseline. Resource-headroom asset check. Delivered in two phases — NYSE-only refactor
  proven behaviour-preserving (`max |Δ daily_return| = 0` over 2085 days) before the JSE
  was added, so "nothing regressed" stayed a checkable claim.

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

## Current model & data snapshot (as of 2026-08-11)

- **Two markets.** NYSE: 50 tickers, 108,091 bars, 104,941 feature/prediction rows, 6,294
  book snapshots (3 books), 470,046 option quotes over 16 snapshot days. JSE: 29 Top-40
  tickers, 60,248 bars, 58,421 feature/prediction rows, 6,258 book snapshots, no options
  (no free chain data). Both from 2018-01-02. Live track record: XNYS 16 days, XJSE 12 —
  both under the 20-day floor, so ratios stay withheld.
- **Champions** (registered `quantpulse-lgbm-<exchange>`):
  - XNYS v1 — promoted at holdout IC 0.026, Sharpe 0.21, max DD −5.0%. (v2, from the
    first scheduled retrain, was auto-promoted on a mismatched exam and demoted the same
    day — incident 24.)
  - XJSE v3 — promoted at holdout IC 0.063, Sharpe 1.51, max DD −7.5%, on 2026-07-25 in a
    like-for-like comparison against v2's 1.32.
  - Those figures are **historical records of what each model was promoted on, not
    comparable across models**. Both predate the fix, and the 2026-08-01 retrain showed
    how far apart stored and current can drift: XNYS v1 re-scored **2.570** on that run's
    311-day holdout against its stored 0.205. The gate no longer reads stored numbers.
  - (JSE v1 was auto-promoted at Sharpe −0.069 under a gate with no first-champion floor,
    then demoted; see below.)
- **Retrains.** 2026-07-25: XJSE v3 promoted, XNYS candidate promoted-then-demoted
  (incident 24). 2026-08-01, first under the corrected gate: **both challengers rejected**
  — XNYS 1.595 vs incumbent re-scored at 2.570, XJSE 1.326 vs 1.786. The old gate would
  have promoted the XNYS challenger against the stored 0.205, repeating the previous
  week's error; instead it was rejected silently and correctly.
- **Books** (in-sample replay, daily/horizon/long-only): XNYS 7.7%·0.73 / 14.3%·1.30 /
  34.6%·1.16; XJSE 21.8%·1.94 / 34.8%·2.94 / 41.9%·1.41. All carry survivorship + in-sample
  bias; the live phase is the number to judge.
- Promotion policy (`ml/promotion.py`): the comparison runs on **IC**, not Sharpe.
  Candidate needs holdout IC ≥ champion + a per-market margin (2 sd of the measured seed
  re-roll: 0.006 XNYS, 0.008 XJSE), IC ≥ 0, drawdown better than −35%; Sharpe survives
  only as a wide veto (`max_sharpe_regression` 0.50) checked **after** IC decides, so it
  can overrule a promotion but never make one. A **first** champion must also clear
  `min_first_sharpe` (0.0); NaN never promotes. The gate backtests at the market's own
  quantile width, and **re-scores the incumbent on the candidate's exact holdout** at
  decision time — stored metrics are never consulted (incident 24).
- Quantile width per market, set from breadth: 20% of 50 US names and 35% of 29 JSE names
  both ≈10 positions per side.
- Training (`TrainConfig`): horizon 21d, 4 splits, embargo 21d, 15 Optuna trials,
  15% holdout, LightGBM early stopping 50 — on an **inner validation split**, never the
  promotion holdout; each `model_runs` row records its holdout window.
- Features v1: ret_1/5/21, mom_63, vol_21/63, ma_ratio_21/63, volume_z_21 + cross-
  sectional pct-ranks of ret_5/ret_21/mom_63/ma_ratio_21 — ranked **within each exchange**.
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
13. **Zombie run after unclean Docker stop**: an in-process run left `STARTED` with no
    process; `max_concurrent_runs: 1` meant it blocked the queue *forever*, and being
    `STARTED` (not `FAILURE`) it was invisible to the failure sensor. Fix: `run_monitoring`
    reaps it; prefer `make down`.
14. **UTC date vs exchange date**: containers run UTC and code used `date.today()`. Under
    EST the 19:00 ET jobs land at 00:00 UTC, stamping every row a day forward — latent all
    summer, would have shifted the options history at the Nov DST change. Fix:
    `calendar.market_today()`. Tests pin both DST sides.
15. **Cross-exchange feature leak (M11)**: cross-sectional ranks grouped by `date` alone
    would rank Naspers against Apple. Grouped by `(date, exchange)`; a regression test
    proves per-market ranks span 0–1 where a global ranking would not.
16. **Vendor units glitch (M11)**: Yahoo intermittently reported JSE closes in Rand not
    cents — a −99%/+100× round trip that compounded the first JSE book to 8,788×. Fix:
    `data/cleaning.py` repairs a close a clean 100× off *both* neighbours. Four found.
17. **First champion with no floor (M11)**: the JSE model was auto-promoted at holdout
    Sharpe −0.069 because "beat the incumbent" can't gate a first model. Fix:
    `min_first_sharpe`; its derived predictions/books were deleted and it was retrained.
18. **Small-sample ratios published (M11)**: a 3-day live phase served Sharpe −54.93 from
    the API while the UI hid it. Fix: null ratios in the marts below `min_days_for_ratios`.
19. **Stale mart grain tests (M11)**: `unique(date)` / `unique(date, variant)` passed for
    as long as one market existed, then failed the day the JSE arrived — corrected to carry
    `exchange`; caught by the tests themselves.
20. **Orphaned MLflow model (M11)**: Phase 1 renamed the registry but never performed the
    MLflow rename, so `load_champion` returned None and scoring silently wrote zero rows.
    Fix: renamed (preserving versions + alias) + a `predictions_are_current` check.
21. **Python 3.14 base image**: builds the API image but not the dagster one — `dbt parse`
    dies on `mashumaro UnserializableField` (dbt-common dataclass introspection vs PEP 649
    deferred annotations). Declined with the finding recorded in `dependabot.yml`; node 26
    taken after building and serving it.
22. **Capture budget counted requests, not executions**: three option-capture runs
    cancelled *while still queued* (pre-market, never touched the vendor) exhausted the
    daily budget via the sensor's hopeful cursor, locking the repair sensor out for the
    whole evening of 2026-07-23. Fix: derive the budget from Dagster's run history —
    only runs with a `start_time` (left the queue) count (`summarize_capture_runs`).
23. **Catch-up sensor fired for a session that hadn't opened**: the exchange date flips
    at midnight, hours before trading, so at 00:08 ET the sensor requested
    `2026-07-24|XNYS` — and its fixed `catchup-{exchange}-{day}` run_key, which Dagster
    deduplicates *forever*, was thereby consumed: had the evening schedule also been
    missed, the day was silently unrescuable (the 20:05 JSE rescue that exposed this
    came from the schedule's missed-tick replay, not the sensor). Fix: today joins the
    expected window only once its scheduled ingest is overdue (`ingest_overdue`), and
    run_keys carry an attempt number budgeted from run history (`next_ingest_attempt`),
    mirroring incident 22's cure.
24. **First scheduled retrain promoted on a moved exam (2026-07-25)**: the 07-20
    JSE-onboarding backfill grew the XNYS panel (2023+ → 2018+), so the fractional 15%
    holdout cut slid from Dec-2025 back to Mar-2025 — into a stretch where raw 63-day
    momentum IC ran +0.039 (vs −0.004 after). The candidate scored holdout Sharpe 1.89
    on that long exam; the incumbent's stored 0.205 came from the old, shorter window;
    the gate compared the two as if they were the same test and auto-promoted. Two
    lesser leaks compounded it: the final fit early-stopped on the promotion holdout
    itself (308 rounds ground toward it; honest refit 1.61), and Optuna's CV folds
    overlap the holdout period. A matched 2026-only exam (OOS for both) showed the
    candidate no better — IC negative — and it was demoted same-day. Fixes: the gate
    re-scores the incumbent on the candidate's exact holdout (stored metrics never
    consulted; a poisoned-stub test enforces it), the final fit early-stops on an inner
    split, every model_runs row records its holdout window, and `/models/current`
    demotion fallback became version-aware. The 2025 momentum regime itself is a real
    finding — the cleanest case yet for judging on live record, not replay.
    **Validated 2026-08-01**: the next retrain met the same conditions and the gate
    absorbed them without incident — XNYS v1 re-scored 2.570 against its stored 0.205, so
    the challenger's 1.595 was rejected where the old gate would have read it as a
    landslide win. The fix is confirmed in production, not only in tests.
25. **Failure alerts were written where nothing could read them (2026-07-28)**: a degraded
    yfinance failed the XNYS ingest twice overnight; the run-failure sensor recorded both
    perfectly — into `$DAGSTER_HOME/alerts.jsonl` inside the *daemon's* container. The API
    serves `/alerts` from a **different** container with no `DAGSTER_HOME`, so it read
    `/tmp/alerts.jsonl`, found nothing, and returned `[]`; the path was also a writable
    layer rather than a volume, so `compose up` erased it. The alerting had a working
    detector and a dead reporter for its whole life, and every reassuring empty `/alerts`
    was uninformative. Fix: the log moved to a `pipeline_alerts` table (migration
    `3de6e54eece0`) — the database is the one durable thing both containers already share;
    writes swallow DB errors so a broken alert can never mask the failure it describes.
    Lesson: an observability feature isn't done until the read path is verified from the
    consumer's process, not just the producer's.
26. **A late session was never scored, and the check couldn't see it (2026-07-29)**:
    scoring only ever looked at `features["date"].max()`. XNYS 2026-07-27 was ingested
    late — rescued by the catch-up sensor at 04:05, *after* that night's 01:00 process —
    so it was never the maximum at any later run and was never scored: prices and
    features present, predictions absent, a permanent hole in the paper book. The live
    track record read 5 days instead of 6, and the missing day was positive, so the
    record understated itself (−0.40% → +0.50% once filled). `predictions_are_current`
    compared only the two *maxima*, which the next night's run pushed back into
    agreement, so it passed throughout. Fix: score every unscored feature date in a
    bounded window, never re-scoring a date some earlier champion already scored (that
    would rewrite the live record with a model that did not exist then — invisibly, since
    the marts take the newest version per date); the newest date stays idempotently
    re-scored so a fresh champion's view of today lands at once. The check now counts
    gaps as well as lag. Lesson: comparing maxima answers "has it stopped?", never "did
    it skip?" — and every rescue path needs a downstream consumer that can act on
    backfilled data, not just the newest.
27. **The JSE positions panel was blank, and nothing errored (2026-08-11)**: the fifth
    instance of the cross-market leak. `/portfolio/positions` scoped its snapshot by
    exchange, then looked up closes and scores with a **global** `max(date)`. With NYSE a
    session ahead of the JSE — the ordinary state, since NYSE ingests after midnight SAST
    — every JSE row asked for a close on a day the JSE never traded and got nothing back:
    0/20 prices and scores against NYSE's 20/20. `/options/{ticker}/idea` had the same
    shape and would have reported every idea unavailable on a US holiday. Both scoped to
    the rows actually being read. Found while writing a `routes.py` docstring claiming
    "everything is scoped to one market" and checking whether it was true — the earlier
    four leaks were whole endpoints missing the parameter, so nobody had looked for the
    subtler form, an **unscoped aggregate inside a correctly-scoped endpoint**.
28. **Feature drift was measured across both markets pooled (2026-08-11)**: incident 15's
    mistake — cross-market mixing — in a place nobody revisited after fixing it in the
    cross-sectional ranks. `run_drift_check` loaded every market's features into one
    distribution. Measured on live data: pooled share 0.077 against 0.154 for either
    market alone, and the worst pooled feature psi 0.21 against XJSE's 0.74. So the
    monitor was systematically half as sensitive as intended against a 0.3 retrain
    threshold, and when it did fire it retrained **both** markets on evidence about
    neither. The markets also drift on different features — NYSE volatility, JSE
    momentum — so the single number was an average of two unrelated things. Fix:
    per-market measurement, an `exchange` column on `drift_metrics` (legacy rows stamped
    `POOLED` rather than reassigned or deleted), a per-market cursor on the retrain
    sensor, and the exchange threaded through `/drift/latest` and the dashboard. Lesson,
    and the reason the next section exists: `run_drift_check` and `store_drift_report`
    had **no tests at all**, which is why 255 tests passed unchanged through a semantic
    rewrite. The bug was not missed by the tests; it was outside them.
29. **The outage rescue gave up permanently (2026-08-11/12)**: a ~24-hour internet outage
    failed four ingests per market. Everything then behaved as designed and the sessions
    still had to be recovered by hand, because the design had a hole: `next_ingest_attempt`
    counted **every run ever recorded** for a partition, so once a session burned its three
    attempts it was locked out of automatic recovery *forever*. Connectivity returned hours
    before anyone looked, and nothing retried. The catch-up sensor made outages survivable
    but not recoverable — the retry ceiling was right, making it permanent was wrong.
    Compounding it, the skip reason read `no missed trading days in the lookback window`
    while two sessions sat unrecovered: `missing_trading_days` had reported them correctly
    and the sensor dropped them on budget, then described the wrong cause. Fix: the budget
    reads only *today's* runs while the attempt number still counts every run ever (they
    answer different questions — a run_key is deduplicated forever, so numbering from today
    alone would reissue yesterday's key and vanish); and the skip reason now names the
    exhausted sessions and says it will retry tomorrow.
    One thing the outage cost that no fix recovers: **08-11 option chains**, where three
    repair runs reported SUCCESS having captured zero rows (the documented "wrote N rows is
    not captured the universe" edge, with N = 0). **STX40.JO's 08-11 bar** was written up
    here as a second permanent loss and was not one — it arrived at the vendor two days
    late and a plain re-fetch on 08-13 filled it, closing the benchmark gap. That
    correction is the more useful record: an absent bar and an unpublished bar look
    identical at the moment you look, so "the vendor does not have it" needs a re-fetch on
    a later day before it is a finding. See the data dictionary note.
    Lesson: a rescue mechanism needs a test for *resuming*, not only for stopping. Both
    halves of this were in code written five weeks earlier specifically to survive
    outages, and the tests written alongside it covered the budget being spent but never
    the budget being restored.
30. **The daily budget was counted over the wrong day (2026-08-12/13)**: the very next
    outage exposed the other half of incident 29. With the budget correctly scoped to
    "today", *which hours count as today* was still wrong: the boundary was built as an
    aware exchange-local midnight, and `dg.RunsFilter(created_after=...)` compares
    **wall-clock fields** against the naive-UTC `create_timestamp` column, discarding
    `tzinfo` entirely. So `2026-08-13 00:00+02:00` was read as `00:00 UTC` — 02:00 SAST,
    two hours into the day. Measured on the live instance for `2026-08-12|XJSE`: the same
    filter matched **3 runs when spelled `+02:00` and 10 when converted to UTC**. The
    sensor therefore saw 3 of its 3 attempts and kept firing; it had made 14 runs against
    a ceiling of 3, and would have continued indefinitely. Direction of the error is
    per-market and opposite: XJSE (UTC+2) opened its window 2h late so the budget never
    filled, XNYS (UTC−4) opened it 4h early so yesterday's late runs counted against
    today — the strict direction, and it applies to `option_snapshot_repair_sensor` too,
    which had carried the same construction since 2026-07-24 on captures that **cannot be
    refetched**. Fix: one `catchup.exchange_day_start_utc(day, exchange)` used by both
    sensors, converting with `.astimezone(dt.UTC)` so the wall clock Dagster reads is
    already the right instant.
    Lesson: the tests that would have caught this had to assert the **naive wall-clock**,
    not the instant. A natural `assert start == datetime(..., tzinfo=SAST)` passes with or
    without the conversion — the two values *are* the same instant — so it proves nothing
    about the only thing that mattered. Verified by reverting the fix: that assertion
    stayed green while the two wall-clock assertions failed. When a library ignores part
    of a value, test the part it reads.

## Coverage tracks debugging history, not risk (2026-08-11)

Prompted by "I don't trust that this is the only issue since you happened upon it by
chance." A repo-wide search over known bug classes — unscoped aggregates, naive
`date.today()`, swallowed exceptions, book-variant leaks, marts missing `exchange`,
missing small-sample guards, mutable defaults — found everything clean except the drift
pooling above. But pattern-matching only finds shapes already known, so the follow-up was
function-level coverage: **47 functions never executed by any test**.

Most were thin by design (CLI argument plumbing, Dagster assets over tested modules). Six
were decision logic, all at 0%: `drift_retrain_sensor`, `drift_report`,
`recent_prices_quality`, `option_snapshot_quality`, `option_snapshot_repair_sensor`,
`resource_headroom` — now all at 100%. Their pure helpers were already well covered; what
was bare was the wiring, which is where a guard fails quietly. A gate returning
`passed=True` because its query found nothing is indistinguishable from one that looked
and approved.

The generalisable finding: **tests and explanatory comments both cluster where debugging
has happened**, so the least-examined code is systematically the least protected — and the
last three bugs were all found there. Two of the six guards had been rewritten the same
morning and shipped untested, the same asymmetry that produced the bug they were fixing.

A second pass covered the five functions that build the evidence base — `fetch_daily_bars`
(vendor failure and Stooq fallback), `load_price_bars`, `build_dataset`, `score_history`
(~2,000 replay predictions per market) and `rebuild_portfolio` — taking coverage to 83%.
The initial reasoning for deferring them, that they fail loudly, turned out to be only
half right: a broken loader raises, but scoring one market with another's champion or
collapsing the three books into one produces a **full-looking dashboard built on the wrong
thing**. So those tests assert market isolation and book separation rather than that the
code runs.

Writing them surfaced a latent bug of the quietest kind: concatenating the Stooq fallback
onto an empty frame raises a pandas `FutureWarning`, and the behaviour it warns about —
losing dtype preservation — would have silently changed what a **total-outage day**
ingests. That path only executes when yfinance fails wholesale, so it would have broken on
some future pandas upgrade in the middle of an incident. Two bugs in one day found by
*writing* a test rather than by one failing.

That "genuinely thin" claim was then checked rather than asserted, by asking of each
remaining untested wrapper: what does it delegate to, and is *that* covered? Thirteen of
fourteen held — `option_chains` is two lines around `options_tickers`, which sits at 100%
with a test named for exactly the decision it makes.

The fourteenth did not. `snapshot_option_chains` was **32%**, the least-covered function
on any live path, and it is the only writer of data no vendor will sell back. It had been
mis-sorted into Tier 3 by reading "32%" as *partially covered* rather than as *the
least-covered thing guarding unrebuildable data*. Now 88%, with tests for the failure
modes that matter: one ticker's vendor error costing only that ticker, a re-run absorbing
into the same rows rather than doubling the table, the off-hours gate refusing and writing
nothing, and the stamped date coming from the exchange clock (incident 14). One test
documents a sharp edge instead of asserting it away — a partial snapshot returns a
positive count and raises nothing, which is deliberate for resumability and is exactly how
2026-07-27 captured 15 tickers of 50 and looked successful.

Three times in one day the wrong code was judged risky, always in the same direction:
**underestimating quiet partial-success paths.** The rule that survives is not
tested-versus-untested but **whether a failure announces itself** — and a function that
returns a plausible number while doing half its job is the hardest case to see, precisely
because nothing about the return value is wrong.

## Dependency policy history

Dependabot PR dispositions: action bumps and python/js-deps groups merged when green;
the 8-major js-deps group was closed as unresolvable (typescript 7 vs typescript-eslint 8
peer conflict) and replaced with a curated bump plus documented `ignore` rules for
typescript/eslint/@eslint-js/recharts majors.

The "decline Docker base-image majors untested" policy was revised on 2026-07-23 to
"test locally, then decide" — CI doesn't build images, but they can be built by hand.
Under that rule **node 26 was taken** (image built and served) and **python 3.14 declined**
(the dagster image can't build: `dbt parse` fails on `mashumaro UnserializableField`, i.e.
dbt-common's dataclass introspection vs PEP 649). The python-major decline is recorded as
a `dependabot.yml` ignore with the reason, so it isn't re-proposed. Twelve stale Dependabot
branches were deleted once the repo's `Protect` ruleset was scoped from `~ALL` to `main`.

## Testing architecture

428 checks total: 306 pytest (182 unit on synthetic data; 114 integration against a
disposable `market_test` DB created/migrated/dropped per session, truncated per test —
evidence tests seed raw data then run a real `dbt build` in that DB, MLflow registry tests
use a throwaway sqlite backend; 10 Dagster definition/sensor tests), 59 Vitest
(components + formatters, empty states, market switcher), 63 dbt tests (59 data + 4
unit — `dbt ls --resource-type test` counts both; `dbt build` runs the 59), plus
mypy/ruff/eslint/tsc, shellcheck, markdownlint, `alembic check` for model/migration
drift, and compose validation — all enforced in CI. Line coverage 84%.

**Green is not evidence.** Every serious bug in the log above shipped with fully green CI
and was found by reading data, not by a failing test. So a new test is verified by
breaking the code it guards and watching it fail — the practice caught a "passing" hook
that was only passing because `tail` had cropped its verdict, and a sabotage that appeared
to prove tests blind when the replacement string had simply never matched. Assert the
anchor applied before trusting the result.

## Owner preferences (established in-session)

Portfolio value matters (clean history, badges, README-first); honesty over flash —
in-sample results must be labeled as such; zero cost is a hard rule; DBeaver is the DB
UI (connect to `market`, not `postgres`); VS Code with ruff as formatter; mssql &
kubernetes extensions are workspace-disabled (project uses neither); Claude must never
give personalized investment advice — the platform presents evidence, the owner decides.
