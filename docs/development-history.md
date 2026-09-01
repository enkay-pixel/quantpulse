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

## Current model & data snapshot (as of 2026-08-19)

- **The live record.** XNYS crossed the 20-session floor on 2026-08-18 and its ratios
  publish for the first time: 21 sessions, **−1.17%** total, **Sharpe −1.43**, alpha
  **−22.6%** annualized, information ratio **−4.05**, beta 0.11, R² 0.02, win rate 47.6%.
  XJSE is 17 sessions and flat (+0.01%), ratios still withheld below the floor. Against the
  in-sample replay (NYSE Sharpe +0.74, JSE +1.94) the live record is the opposite sign. The
  annualized figures scale a 21-session sample and should be read for their sign, not their
  magnitude; the low beta confirms the negative alpha is signal rather than market exposure.
- **Two markets.** NYSE: 50 tickers, 108,240 bars, 105,090 feature rows, 566,646 option
  quotes over 19 snapshot days. JSE: 29 Top-40 tickers, 60,334 bars, 58,507 feature rows, no
  options (no free chain data). Both from 2018-01-02.
- **Champions**: XNYS v9 (2026-08-23), XJSE v3 (2026-07-25). XNYS v1 held the alias until
  2026-08-23 and was demoted as an artifact of the pre-backfill panel. Registered
  `quantpulse-lgbm-<exchange>`, MLflow alias and audit trail reconciled by an asset check.
  The figures each was promoted on are **not comparable across models**; the gate re-scores
  the incumbent on the candidate's exact holdout rather than trusting stored metrics.
- **The NYSE stall is resolved; the JSE one is not.** Five NYSE retrains were rejected
  because the incumbent had been fitted to a shorter panel and specialised on the evaluation
  window — not because nothing was good enough. Demoting it and retraining promoted v9 on
  2026-08-23. The JSE has five rejections outstanding and a different cause: challengers lose
  to the fit-free momentum baseline, which the champion also loses to.
- **A simpler model beats the JSE champion.** `quantpulse baseline` scores every champion
  against noise, momentum, reversal and a linear ridge on one shared holdout. On the JSE,
  plain 63-day momentum takes IC 0.1167 and Sharpe 2.28 against the champion's 0.0681 and
  1.84, with half the drawdown and zero parameters. On the NYSE the champion wins decisively
  (IC 0.1907 against momentum's 0.0161). Momentum is now a standing competitor in the gate:
  no candidate is promoted without beating it, first champions included.
- **Noise scored Sharpe +0.47** on the NYSE holdout at IC −0.0015 — a signal containing
  nothing looking positive on Sharpe, which is direct support for gating on IC.

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
    a later day before it is a finding.
    Chasing that gap turned up a live corruption path: for a ticker genuinely missing a
    session, yfinance slides the **in-progress** bar into the empty slot and stamps it with
    the missing date. The same STX40.JO query returned one bar dated 08-12 with a NaN close
    when the window ended 08-13, and the identical bar dated 08-13 with close 10630 when it
    ended 08-14 — so a backfill of 08-12 run after the JSE close would have written today's
    price as yesterday's, in the benchmark the CAPM marts divide by. Only the
    `dropna(subset=["close"])` in `data/ingest.py` stopped it, because the live bar had no
    close yet. Tickers without a gap were unaffected (ABG/NPN/SOL matched across both
    windows), which is what makes it easy to miss — it bites only the instrument already
    having a bad day. See the data dictionary note.
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

31. **The shared venv cannot be rebuilt from its own manifest (2026-08-26)**: quantpulse
    installs editable into `~/nathan_playground/.venv`, a venv shared with the other projects
    in that monorepo and fed from two sources — `requirements.txt` for everything else and
    `make install` for this package. Attempting a clean rebuild showed `requirements.txt`
    does not resolve on python 3.13 at all: `pyppeteer` pins `websockets<11`, which has no
    wheels for 3.13 and contradicts every other consumer of websockets, and an unpinned
    `tokenizers` resolves back to 0.10.3 — no wheel, needs a Rust toolchain — where the live
    venv carries 0.21.4. `hnswlib` is declared and was never installed at all. The file is
    not a manifest; it is a list of names accumulated over time, and the environment was
    built incrementally under resolutions a single resolve can no longer reproduce.
    Consequence for this repo: `make install` is safe and repeatable, but the venv underneath
    it is not reconstructible, so a lost venv is a rebuild project rather than a command. A
    `pip freeze` is currently the only faithful record. The three packages that prompted the
    attempt — `datashader`, its transitive `numba`, and `httpx-cache`, none imported anywhere
    and none in `uv.lock` — were removed from `requirements.txt` and uninstalled instead,
    which is what the goal actually needed.
    Lesson: a dependency file that has only ever been appended to is not a manifest until a
    clean resolve has been run against it. Nothing here would have surfaced short of trying.

32. **Two published findings were sampling artifacts, and the error bar hid it (2026-08-30)**:
    the staleness curves were measured at **five origins**, with the error taken across 25
    (origin, seed) fits. That counts each origin five times, because re-drawing the seed
    re-draws the fit and not the market. Rolled across 46 origins tiling 2022–2026, the JSE
    inversion (published −0.1558 at age 0–20) becomes **+0.0058 ± 0.0289** and the NYSE
    six-week decay disappears entirely — the NYSE model holds ~+0.04 out to 83 days instead of
    falling through zero. Both runs are correct and agree at the five original origins; those
    five had simply landed on negative stretches of a series that swings from −0.53 to +0.35.
    The tell was available without re-running anything: the spread of the five origin means
    (0.309) was as large as the spread of all 25 fits (0.283), so the seeds were adding no
    independent information while multiplying the apparent n by five. The same audit refuted
    the round-count headline — "25 rounds beats early stopping on the JSE", +0.0166 (t +3.43)
    on one holdout, is **−0.0004 (t −0.10)** across 46 origins, winning in 12 of them.
    Consequence: the weekly retrain cadence loses its evidence (it is unmeasured, not wrong),
    and two investigations — the round count and the embargo boundary — were correctly finding
    nothing because there was nothing there. `docs/measurement.md` already carried the rule
    ("use the error that matches the question") and already recorded a staleness curve failing
    it once before by quoting seed error; rolling the origin was the fix then, five origins was
    not enough of it, and the pooled error bar made the shortfall invisible.
    The audit was then finished against the remaining one-holdout findings, and all of them
    moved: the three-tree page's inner-validation/holdout curve correlation (published −0.555
    on the NYSE and +0.436 on the JSE, "the markets disagree") is −0.008 and +0.080 across
    origins, its ~0.025 "IC given up" is matched by picking a round at random, and neither
    early stopping nor CV stopping beats a random round on either market. Its conclusion — the
    round choice is arbitrary — survived; every mechanism it offered did not.
    The ablation page held up best of the set — it scores across four walk-forward folds and
    pairs on the seed — but those folds are **fixed**, and re-measuring its largest effect
    showed what that costs: the drop-one delta for `vol_63`, published at t +9.14 (XNYS) and
    t −5.35 (XJSE), is t +0.7 and t +0.2 across 49 rolling origins. The apparent contradiction
    between that page and `vol_63`'s univariate forward IC dissolved with it — there was no
    disagreement, only two fixed folds. What replaced it is resolved and more useful: on the
    NYSE, ranking on raw `vol_63` scores +0.0802 against +0.0452 for a tree fitted on that one
    column and +0.0281 for the full model, a fitting cost of −0.0349 (t −3.1). The signal is
    there and every layer of the model subtracts from it.
    Lesson: **the unit of generalisation is the window, not the fit.** Average within an origin
    before taking the error, and when a claim is about the market, count origins. A finding
    that survives many seeds at few origins has been shown to be reproducible, not true.

## Fault injection: exercising a path that had never run (2026-08-13)

Prompted by "what else needs to fail hard before this is ready to present?". Counting the
incident log answers it more usefully than guessing: **six of the last eight incidents were
in recovery or observability paths** (22, 23, 25, 26, 29, 30) — code that only executes once
something else has gone wrong. That is not bad luck. The happy path runs every weekday and
is corrected constantly because someone is looking at its output; a recovery path runs
monthly, so an error there survives until an outage flushes it out. Two outages in three
days is why 2026-08-11→13 produced so many findings at once.

So the remaining risk is concentrated in paths that have *not yet run*, which is a finite
list. The largest was the drift retrain sensor: **23 drift readings, zero above threshold**,
so its firing branch had never executed outside a test. Same profile as the catch-up sensor
before that produced four separate incidents.

Injecting the failure it exists to detect — a drifted reading, followed through to the job
it triggers — immediately found a real one. The sensor measures per market, fires per
market, and tags the run with the drifting exchange; `champion_model` then ignored the tag
and looped over **every** market. So a JSE drift reading would also retrain the NYSE: the
precise failure incident 28 is named after ("it retrained both markets on evidence about
neither"). Incident 28 fixed the measurement and left the action, and nothing caught it
because the branch had never run. Fixed by scoping the loop to the run's `exchange` tag,
with an untagged run (the Saturday schedule) still covering every market, and an unknown
code raising rather than silently widening back to all markets.

The lesson is about *discovery method*, not this bug. Every finding this week came from
reality forcing it, which is reactive. The remaining unexercised paths are nameable — the
`backfilled` phase under a long outage, demotion (run once) — and each can be triggered
deliberately, on a chosen afternoon, instead of at 2am mid-outage.

### Drill 2: the DST transition (2026-08-13)

US clocks change on 2026-03-08 and 2026-11-01; South Africa never changes. Every
DST-sensitive path was exercised against both sides. The **code** turned out to be right
everywhere — `market_today` already had five tests including a fixed-offset guard,
`is_post_close` and `ingest_overdue` work in local time so EST looks identical to EDT, the
schedules carry `execution_timezone` so Dagster handles the cron, and Python's `fold`
resolves the repeated 01:30 hour while the nonexistent 02:30 normalises without raising.

The **tests** were not. `exchange_day_start_utc`, written the same morning, passed every one
of its 17 tests when its tz lookup was replaced with hardcoded `{"XNYS": 4, "XJSE": -2}`
offsets — correct in August, an hour wrong from November. Every fixture was dated 2026-08-13,
and in EDT a fixed offset is indistinguishable from a correct one. The catch-up budget would
then have counted over a window shifted by an hour on the first EST session, which is the
same class of bug as incident 30 and would have been just as invisible. Pinned both sides,
plus the JSE staying at 22:00Z and the inter-market gap moving 6h→7h — a constant-offset
assumption fails all three.

Also added a guard that no schedule fires between 01:00 and 03:00 local, where a time either
does not exist or happens twice. Nothing sits there now; the point is that moving one there
becomes a deliberate decision rather than a discovery in November, and for the option
capture a skipped evening is permanent.

### Drill 3: the backfilled phase (2026-08-13)

`fct_portfolio_daily` has never produced a single `backfilled` row — 4,188 rows, all
`replay` or `live`. The mart's labelling was already covered by four tests against a real
dbt build. The gap was upstream, in the scoring that creates the condition, and the drill
found a way for the phase to fire when it should not.

`score_latest` always re-scores the newest feature date, deliberately, so a freshly promoted
champion's view of today lands immediately. That is right when the champion existed on that
date. It is wrong when it did not: the marts take the newest model version per date, so
re-scoring hands an already-`live` day to a model trained on it, and the day flips to
`backfilled` and **leaves the out-of-sample record**. The live track record is the one number
this project asks to be judged on, and it would have shortened silently.

Not hypothetical, and not rare. The retrain runs Saturday; the process job runs Mon-Fri
regardless of whether the market traded. Any Monday US market holiday following a Saturday
promotion leaves the newest feature date on Friday, before the new champion existed. The next
one is **Labor Day, 2026-09-07** — about three weeks out.

Fixed by giving the scoring layer the same notion of "promoted on" the mart uses
(`champion_promoted_on`), and forcing the newest-date re-score only when the champion
predates that date. Genuinely unscored dates still fill in and are still labelled
`backfilled` honestly — the guard protects days that were already scored, nothing else.
Verified inert against production: both champions predate the last scored date, so current
behaviour is unchanged.

### Drill 4: demotion (2026-08-13)

The demotion path itself came out clean, which is worth recording as plainly as a bug. Both
demotions on record — XJSE v1 (incident 17) and XNYS v2 (incident 24) — were promoted and
withdrawn the same day, and in both a legitimate promotion shares that date, so
`first_live_date` is not set by a withdrawn one. The API already resolves the champion by
falling back to the most recent promotion with no later demotion. The marts deliberately
ignore demotions, and that is defensible: a model that *was* champion produced genuinely
out-of-sample predictions on the days it served, and demotion is forward-looking. The one
structural fragility — a first-ever promotion demoted with no replacement — is self-limiting,
because a market with no champion produces no predictions and therefore no live days.

What the drill did find was next door. `stg_predictions` deduplicates to one score per
(ticker, date) by keeping the newest `model_version`, and `model_version` is varchar (MLflow's
type), sorted as **text**. `'9' > '10'` is true in a string sort, and any single-digit version
from 2 up beats `'10'`. So from version 10 onward the dedupe would have selected an *older*
model, and the paper book, track record and alpha decomposition would all have been
attributed to a champion that had already been replaced — silently, since nothing fails.

XJSE was at version 5 and retrains add one per market per week: roughly five weeks of runway,
landing around late September 2026. Nothing had gone wrong yet because no date currently
carries two versions — which is precisely why it needed a test rather than a sighting. Fixed
with a cast, which also raises on a non-numeric version instead of mis-ordering it: the right
way round for the column that decides which model the evidence came from.

### Drill 5: the dagster-dbt seam (2026-08-13)

Chosen because the previous four all sat at seams, and this is the widest one: five dbt
sources declare `meta.dagster.asset_key` in `transform/models/staging/sources.yml`, which is
what makes the marts wait for the pipeline that feeds them.

The seam is healthy — all five (`raw_prices`, `predictions`, `portfolio_equity`,
`champion_model`, `option_chains`) resolve and the edges are wired, with `market/universe`
correctly appearing as an unmanaged external source since it is seeded by
`quantpulse sync-universe` rather than any asset. Manifest staleness, the other half of this
seam, is bounded already: `transform/target/` is gitignored and the manifest is regenerated by
`prepare_if_dev()`, by the cold-start parse, or baked at image build.

What was missing was any guard. Rename a Python asset without editing `sources.yml` and
nothing errors: dagster-dbt invents an external asset with the stale key, the dbt models
depend on that phantom rather than the real producer, and the ordering guarantee inside
`process_job` disappears — marts would build from whatever Postgres happened to hold. Two
tests now pin it, one for orphans and one asserting the five specific edges, because a
sources.yml that lost every `meta.dagster` block would pass the orphan check (each source
becomes its own external asset, none missing a producer) while the entire transform layer
detached from the pipeline. Verified by renaming `raw_prices` to `daily_bars` in sources.yml,
which is exactly the mistake being guarded, and watching both fail.

### Drill 6: the API/mart ratio contract (2026-08-13)

Drilled for its timing: XNYS was 3 sessions from the 20-day floor, and the first moment the
platform can publish an *earned* ratio is a poor moment to find out the path was never
exercised.

Every test of this contract checked only the suppressing half. Below `min_days_for_ratios`
the marts null Sharpe, volatility, win rate, beta, alpha and information ratio, and the API
passes the nulls through; `test_small_samples_never_publish_a_ratio` pins exactly that. No
test asserted the opposite — that a phase with enough days actually *publishes*. The
asymmetry is dangerous because its failure mode is invisible: ratios nulled forever look
identical to a young track record, which is what the project genuinely had for weeks.

Demonstrated rather than argued. Raising the floor from 20 to 200 — suppressing every ratio
for roughly ten months — left **all 19 existing API and mart tests green**. The new suite
fails three.

The path itself turned out to be correct: a 30-day live phase publishes finite numbers on
both `/track-record` and `/portfolio/alpha-beta`. So this drill bought coverage, not a fix.
The fixture puts both phases on opposite sides of the floor in one build (10 replay, 30 live),
which also pins the floor as **per phase** rather than global — the failure behind incident
18, where a 3-day live phase served a Sharpe of −54.93. Finiteness is asserted too: JSON has
no NaN or Infinity, and that only becomes reachable once a phase is allowed to publish.

### Drill 7: MLflow registry vs the Postgres audit trail (2026-08-13)

Two systems record which model is champion, updated separately. MLflow's `@champion` alias
decides what `load_champion` deserializes and therefore what actually scores; `model_runs`
decides what the dashboard reports and how `fct_portfolio_daily` dates the `backfilled`
boundary. Nothing spans both writes — `train_evaluate_promote` sets the alias first and
commits the audit row after — so a failure in between leaves MLflow promoted and Postgres
silent. The dashboard would keep naming the old champion while the new one wrote every
prediction, and every number on screen would be attributed to a model that did not produce it.

They currently agree (xnys v1, xjse v3, both matching the latest non-demoted promotion), and
nothing was reconciling them. `champion_registry_agrees` now does, per market, non-blocking,
reporting both answers. It reports and never repairs: deciding which of two disagreeing
records is right means knowing whether the promotion was intended, and that is not a call to
automate against a registry the scoring pipeline deserializes.

The demotion-aware "who is champion according to the audit trail" query was extracted to
`ml.promotion.audit_champion` and the API endpoint now calls it. Two copies would have been
the very bug the check exists to find: the platform comparing two answers that were never
independent, agreeing with itself while disagreeing with the model doing the scoring.

Running it found a bug in the check itself — the ORM expires attributes on commit, so
reading `model_version` after the session block raised `DetachedInstanceError`. Only surfaced
by executing it against the real stack; a test holding a longer-lived session would have
passed. Verified afterwards by pointing the live xjse alias at v5 and watching the check fail
with `audit says v3, MLflow @champion is v5`, then restoring — production re-verified clean.

Seven drills, seven findings, none of them the thing being drilled: the drift injection found a
bug in the *job* rather than the sensor, the DST drill a gap in *tests* rather than code, the
backfilled drill a bug in *scoring* rather than the mart, and the demotion drill a sort order
in *staging* rather than demotion, and the dagster-dbt drill an absent *guard* rather than a
broken mapping, the ratio-floor drill a missing *half* of a contract rather than a
wrong one, and the registry drill an absent *reconciliation* rather than a mismatch.
That is the argument for doing them — what a rehearsal
turns up is rarely what you set out to check. It also locates the risk better than "recovery
paths" did: all four sat at a **seam between two layers that were each correct alone**. A
sensor that tagged and a job that ignored the tag. A function that handled DST and tests that
did not. A mart that labelled phases correctly and scoring that fed it the wrong attribution.
A varchar column written by MLflow and read by SQL that assumed numbers. Wherever two
components hand something to each other is where the next drill should look.

Injection runs against the disposable `market_test` database, never the live one. Writing a
fabricated drift reading into `market` would risk the daemon picking it up on its next tick
and filing a genuine `model_runs` row triggered by invented evidence — corrupting the audit
trail this project exists to keep honest.

## Audited against a published rubric, and what it found (2026-08-14)

Prompted by the observation that seven fault-injection drills had all rediscovered
documented failure patterns. Scoring against an external rubric says what to look for
instead of waiting to be surprised, and produces a citable claim. Full itemisation in
[ml-test-score.md](ml-test-score.md); the score is **2.5**, set by Model Development at 2.5
against Monitoring 6.0 and Infrastructure 5.0. The shape is the finding: the pipeline
around the model has had far more adversarial attention than the model itself.

Two gaps were closed the same day.

**A simpler-model baseline** (`ml/baselines.py`, `quantpulse baseline`). Nothing had ever
compared the champion against a simple rule, so the promotion gate could pass a lineage of
models that all lost to one. Every competitor sits the same exam through
`pipeline.score_holdout`. The result matters: on the JSE, plain 63-day momentum beat the
champion on every metric (IC 0.117 against 0.068, Sharpe 2.28 against 1.84, half the
drawdown) with zero parameters and no fitting. On the NYSE the champion won decisively
(IC 0.191 against momentum's 0.016). Read the JSE replay numbers accordingly — they may be
measuring momentum rather than the model. Two by-products: a pure noise control scored
Sharpe +0.47 on XNYS at IC −0.0015, which is direct support for gating on IC rather than
Sharpe; and momentum and reversal scored oppositely on both markets, so the backtest
responds to signal direction rather than flattering anything ranked.

Momentum is now a **standing competitor in the promotion gate**: no candidate is promoted
without beating it by the per-market IC margin, first champions included, and the gate fails
closed if the baseline cannot be scored. It governs promotion, not incumbency, so a champion
already installed can still lose to momentum until something replaces it.

**A rollback path** (`quantpulse demote`, with `--dry-run`). Previously no code performed a
demotion; the rows in `model_runs` had been written by hand. The ordering is the design:
resolve the fallback, write the audit row, move the alias, commit last, so a registry
failure leaves the audit trail untouched.

## Comments carry rules, docs carry history (2026-08-14)

Comments and docstrings across the codebase had grown into a narrative of how each rule came
to exist — incident numbers, dates, measured values, which ticker broke on which morning.
That serves the author, not the next reader, who carries none of the context that makes it
readable. Roughly 40 files were pruned: the rule and the reason stay, stated plainly and
generally; the anecdote moves here. Fixture dates and design rationale stayed. This file,
the data dictionary and the runbook are the places that can afford context.

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

559 checks total: 429 pytest (269 unit on synthetic data; 141 integration against a
disposable `market_test` DB created/migrated/dropped per session, truncated per test —
evidence tests seed raw data then run a real `dbt build` in that DB, MLflow registry tests
use a throwaway sqlite backend; 19 Dagster definition/sensor tests), 66 Vitest
(components + formatters, empty states, market switcher), 64 dbt tests (60 data + 4
unit — `dbt ls --resource-type test` counts both; `dbt build` runs the 60), plus
mypy/ruff/eslint/tsc, shellcheck, markdownlint, `alembic check` for model/migration
drift, and compose validation — all enforced in CI. Line coverage 83%.

**Green is not evidence.** Every serious bug in the log above shipped with fully green CI
and was found by reading data, not by a failing test. So a new test is verified by
breaking the code it guards and watching it fail — the practice caught a "passing" hook
that was only passing because `tail` had cropped its verdict, and a sabotage that appeared
to prove tests blind when the replacement string had simply never matched. Assert the
anchor applied before trusting the result.

**A local pass can mean the test found production.** The benchmark re-ingest trigger
(2026-08-13) added a second, unstubbed query to the catch-up sensor. The Dagster suite is
meant to run without a database and stubs `missing_trading_days`; nothing stubbed the new
call, so it opened a connection — and found the developer's *live* `market` database on
localhost:5432. Every local run was green. CI caught it only because its Postgres has no
`prices` table. A suite that is supposed to be hermetic has to be *made* hermetic, so
`tests/conftest.py` now points every non-integration test at a dead address; a stray query
fails instantly, by name, on the laptop. Verified by removing the stub again and watching
it fail with no special invocation. The near-miss is the point: "passes locally, fails in
CI" is usually read as a CI problem, and this time the local pass was the wrong answer.

**And the fixture has to be able to tell the difference.** Verifying `benchmark_gaps`
(2026-08-13) by swapping its set difference for the 0.95 ratio it exists to replace left
all five new tests green — the sabotage applied, but every fixture used a five-session
window where one absent day is 0.2 and fails any threshold. The bug only exists at
realistic sizes: 1 missing in 30 is 0.033, which slips under 0.05. A test written at a
size the bug cannot occur at is not a weak test, it is a decoration. Size the fixture to
the failure, then break the code to prove it. The same shape appeared hours earlier in
incident 30, where the natural instant-comparison assertion passed with and without the
timezone fix.

## Owner preferences (established in-session)

Portfolio value matters (clean history, badges, README-first); honesty over flash —
in-sample results must be labeled as such; zero cost is a hard rule; DBeaver is the DB
UI (connect to `market`, not `postgres`); VS Code with ruff as formatter; mssql &
kubernetes extensions are workspace-disabled (project uses neither); Claude must never
give personalized investment advice — the platform presents evidence, the owner decides.
