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
  walk-forward CV, Optuna(15). Promotion gate compares **IC**, not Sharpe: holdout IC ≥
  champion + a per-market margin (`Exchange.ic_promotion_margin`, 2 sd of a measured seed
  re-roll), IC ≥ 0, DD > −35%, Sharpe kept only as a wide veto (`max_sharpe_regression`
  0.50) applied **after** IC decides. A **first** champion must clear `min_first_sharpe`
  (0.0) — without it a model that lost money out-of-sample becomes the dashboard's
  champion. Why IC: refitting one spec with only the seed changed moves Sharpe by sd
  0.12–0.24 and moves it ~2.0 across six-month windows, while IC moves by 0.003–0.004.
  The old 0.05 Sharpe margin sat 5–10× **below** its own noise floor.
  Since 2026-08-14 a candidate must also beat a **standing competitor** — a fit-free
  63-day momentum rule scored on the same holdout — by the same margin, first champions
  included, because a lineage can beat each other while all losing to a one-line rule.
  Measured 2026-08-23: XJSE momentum IC 0.1094 vs champion v3's 0.0569, so the JSE champion
  still does not earn its place on the backtest; the gate stops the next one repeating it
  but cannot demote the incumbent. It is deliberately left running — that case rests on
  holdout IC, which does not predict live behaviour here (see below). `quantpulse baseline`
  reports the comparison on demand; reasoning and reopen trigger in docs/roadmap.md.
  Champions: **XNYS v9** (promoted 2026-08-23, IC 0.059 / Sharpe 1.65), XJSE v3 (IC 0.063 /
  Sharpe 1.51). XNYS v1 was **demoted 2026-08-23**: it was fitted two days before a backfill
  tripled the panel, so it specialised on the evaluation window, re-scored at IC 0.1777 and
  blocked five retrains while the live book lost money
  ([findings/unbeatable-incumbent.md](docs/findings/unbeatable-incumbent.md)). Promotion
  figures are **not comparable across models**; never compare a stored metric to a fresh
  one — the gate re-scores instead.
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
  `uv lock`). The **pre-commit hook rev must match that pin**, and CI fails on drift:
  dependabot updates pyproject but has no pre-commit ecosystem configured, so the hook
  silently stays behind and you get commits the hook reformats and CI then rejects. Same
  guard as markdownlint, whose rev is likewise mirrored in ci.yml. `uv` is guarded the
  same way: CI pins `setup-uv` and the rev must match the `uv-pre-commit` hook, or the
  two write lock files in formats the other did not expect. Note the locally installed
  uv is a third version and is nobody's to pin — keep it near the other two by hand.
- mypy strict-ish; pytest markers: `integration` needs live Postgres.
- dbt: `transform/`, profiles via env vars, tests use the `arguments:` nesting,
  package pins in `transform/package-lock.yml` (committed). Marts join the Dagster
  graph via dagster-dbt (group `transform`); sources map with `meta.dagster.asset_key`.
- `web/package.json` carries an `allowScripts` entry for `fsevents@2.3.3`, vite's macOS
  file-watcher. npm 11 refuses to run install scripts until each is approved by name and
  exact version, so a bump needs re-approving — which is the point. Approve named
  packages, never `--all`, or the next transitive dependency to add an install script
  runs it unreviewed.
- Frontend: palette/roles as CSS vars in `web/src/index.css` (dataviz method: legends
  for ≥2 series, status colors always icon+label, vendor chunks split).
- Docs live in `docs/`, indexed by [docs/README.md](docs/README.md). Measurement
  write-ups live in [docs/findings/](docs/findings/README.md), one per investigation;
  `ml-test-score.md` is the scorecard that links to them, not the lab notebook. Before
  measuring anything, read [docs/measurement.md](docs/measurement.md) — the gotchas
  below record individual mistakes; that file records the rules that would have
  caught them. The repo root is also
  an Obsidian vault (`.obsidian/app.json` committed, per-machine state gitignored). Write
  **markdown links, never `[[wikilinks]]`** — they render as literal brackets on GitHub,
  which is where this is actually read. `scripts/check_doc_links.py` fails CI on a wikilink
  or a relative link that points nowhere, so the rule does not rely on being remembered.
  Publishing a site later means Quartz on GitHub Pages, which is free; Obsidian Publish is
  $8/month and declined.
- Commits: imperative subject, body explains why, trailer
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. Pre-commit hooks installed —
  incl. gitleaks (222 rules) over every staged diff, since this repo is public and a
  leaked token must be *rotated*, not force-pushed away. False positives go in
  `.gitleaks.toml` narrowly scoped to rule + path + line pattern, never as a blanket skip.
- **A merge subject must not repeat the branch's own commit subject.** `main` then shows the
  same line twice and the log no longer distinguishes the merge from the work it brought in.
  Either omit `--subject` (GitHub writes `Merge pull request #N from ...`) or write one that
  summarizes the branch rather than restating its tip. Dependabot merges avoid this for free,
  since the branch commits are `chore(deps):` and the merges are retitled `build(deps):`.
  Two pairs on `main` predate this rule and stay as they are: rewording a pushed commit needs
  a force-push, and the `Protect` ruleset blocks `non_fast_forward` on the default branch.
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
- An outage longer than the scoring floor widens the window back to the last scored date
  (`scoring_window_start`), so a trip doesn't leave permanent holes. Safe only because
  `fct_portfolio_daily` marks a day scored by a champion promoted **after** it as
  `backfilled`, not `live` — otherwise a long catch-up files in-sample predictions as
  out-of-sample evidence, and nothing about the date reveals it.
- Scoring fills **every unscored feature date** in a 30-day window, not just the newest —
  a late/rescued ingest is never the max again, so it would go unscored forever (incident
  26). Never re-score a date an earlier champion already scored: the marts take the newest
  model version per date, so it silently rewrites the live record. Freshness checks that
  compare *maxima* answer "has it stopped?", never "did it skip?" — count gaps too.
- **Anything computed across markets must group by exchange** — ranks (incident 15) and
  drift (incident 28) both pooled them, and pooling halves a signal while looking healthy.
  In the API the subtle form is an unscoped aggregate inside a correctly-scoped endpoint:
  `max(Price.date)` over the whole table returns whichever market ingested last, which
  blanked the JSE positions panel for weeks (incident 27). Scope every `max()` to the rows
  you are about to read.
- **Unit and Dagster tests must never touch a database** — `tests/conftest.py` points them
  at a dead address so a stray query fails instantly instead of silently reading the live
  `market` DB on localhost and passing. If a sensor gains a new DB-backed call, stub it in
  the suite's fixture. This is why "passes locally, fails in CI" happened on 2026-08-13, and
  there the local pass was the wrong answer, not CI.
- **A noise floor belongs to the procedure that measured it, and does not transfer.**
  `Exchange.ic_promotion_margin` is 2 sd of a seed re-roll on *tuned* models. Reused to judge
  an ablation — which refits at default parameters, where early stopping picks a different
  tree count per seed — it is 3-6x too small (measured: 2 sd is 0.0375 XNYS / 0.0228 XJSE,
  against margins of 0.0060 / 0.0080). Judged against the borrowed one, every feature cleared
  it and the sweep produced a ranked list of "harmful" features that was entirely seed noise.
  `ablation.measured_noise_floor()` re-measures on each run; anything new that calls a
  difference significant must do the same, and a sweep whose floor exceeds the effect it is
  testing is underpowered, not a finding. Watch the ratio of significant results to tests
  run: 1 in 26 at two sigma *is* the false-positive rate, not a discovery.
- **A greedy search seeded at `-inf` always accepts its first candidate.** Forward selection
  reported one "selected" feature on a market where nothing beat zero, because the first
  comparison was against negative infinity rather than against the skill of an empty set.
  Seed a running best at the value of doing nothing, not at a sentinel.
- **Two models fitted to different panels are not comparable, and nothing records that.**
  The NYSE champion was trained two days before a backfill tripled the history (panel began
  2023-04; backfilled to 2018-04). It re-scores at IC 0.1777 on the shared holdout while
  challengers trained on the long panel score ~0.06 — reproduced exactly by refitting on the
  short panel (25 trees, 0.1792). The holdout sits right after the regime the short panel
  covered, so a specialist beats generalists on their shared exam every time, which is the
  whole promotion stall. `model_runs` stores each run's holdout window but not its training
  span, so this is invisible in the data. Re-scoring the incumbent on the candidate's holdout
  is necessary and not sufficient: same exam, different syllabus. Suspect it whenever an
  incumbent looks untouchable, and note the live book was losing money the whole time that
  incumbent scored 0.1777. Models now tag `train_start`/`train_end`, the audit row carries
  both the candidate's span and the incumbent's, and the gate warns when they differ *or*
  when the incumbent predates the tag. It warns rather than refuses: whether a mismatch
  should block a promotion is a judgement nobody has made yet, and a gate that silently
  refuses is its own kind of stall.
- **The early-stopping split does not predict holdout performance.** Fixed 2026-08-23 to stop
  on IC rather than RMSE, which was right — RMSE stopped after one round — but it did not fix
  the underlying problem. Inner-validation IC is negative at every round on XNYS, and the
  inner-val and holdout curves correlate **−0.555** there (all seeds negative) against +0.436
  on XJSE. Following either costs ~0.025 IC versus an oracle round, which is the size of the
  whole model's IC. Picking the round from CV folds instead helps one market and hurts the
  other. So the tree count is near-arbitrary with respect to the gate, and round-to-round
  spread (~0.03) is another noise source under every IC figure, alongside the seed. Do not
  "fix" it by stopping on the holdout — that is the leak the inner split exists to prevent.
- **Early stopping validates on RMSE while the gate scores IC.** On the full panel the final
  fit stops after a single boosting round in seven of eight seeds — RMSE on noisy 21-day
  forward returns plateaus immediately, so `early_stopping` sees no improvement. Holding
  trees fixed, IC peaks near 10-25 trees. A stopping rule has to watch the metric the
  decision is made on.
- **How long a model stays useful is still unmeasured, and one wrong answer has already been
  retracted.** `quantpulse staleness` freezes a model and scores it forward across rolling
  origins. Measured at five origins it showed NYSE skill dying at six weeks and the JSE curve
  *rising* with age; at 46 origins **both effects vanish** — NYSE holds ~+0.04 out to 83 days,
  JSE sits at zero throughout. The weekly cadence is therefore not justified by measurement,
  and not shown to be wrong either. Roll the origin *far enough*: the failure was five origins
  plus an error bar pooling 25 (origin, seed) fits, which counts each origin five times because
  the seed re-draws the fit and not the market. Averaging within an origin before taking the
  error is the rule — see
  [measurement.md](docs/measurement.md#the-seed-is-not-a-sample-of-the-market).
- **A green test run is not evidence.** Every serious bug in the incident log shipped with
  CI green and was found by reading data. Verify a new test by breaking the code it guards
  and watching it fail — and assert your sabotage actually applied, because a
  non-matching string looks exactly like a test that cannot see the bug. Coverage tracks
  where debugging has happened, not where risk is: six guards sat at 0% until 2026-08-11.
- Cross-container state goes in **Postgres**, never a file under `DAGSTER_HOME`: that path
  is per-container and not a volume, so the API cannot read what the daemon writes and
  `compose up` erases it (incident 25 — failure alerts were invisible for weeks). Verify
  observability from the *consumer's* process, not the producer's.
- Sensor `run_key`s are deduplicated by Dagster **forever** — never give a retryable
  rescue a fixed key (one premature/failed attempt strands it for good). Budget from run
  history and suffix the attempt number; only runs with a `start_time` spend budget
  (`catchup.next_ingest_attempt` / `summarize_capture_runs`). Also: the exchange date
  flips at midnight, so "today" is not a *missed* session until `catchup.ingest_overdue`.
- A session is re-ingested for **two** reasons — thin coverage *or* an absent benchmark
  (`catchup.benchmark_missing_days`), deduplicated so a day that is both spends one attempt.
  The benchmark trigger needs its own bound (`BENCHMARK_RETRY_SESSIONS`) because it cannot
  fix itself the way coverage can: if the vendor never publishes the bar, retrying changes
  nothing, so eligibility expires after five sessions while `benchmark_freshness` keeps
  reporting it. Any future "re-run until X appears" trigger needs the same treatment.
- **`dg.RunsFilter(created_after=...)` ignores `tzinfo`** — it compares wall-clock fields
  against the naive-UTC `create_timestamp` column, so an aware local datetime silently
  shifts the boundary by the offset (incident 30: the same filter matched 3 runs as
  `+02:00` and 10 as UTC, and the catch-up sensor made 14 attempts against a ceiling of 3).
  Build day boundaries with `catchup.exchange_day_start_utc()`, never
  `datetime.combine(day, time.min, tzinfo=ex.tz)`. Testing this needs an assertion on the
  **naive wall-clock**; comparing instants passes either way, because they *are* the same
  instant — that is precisely why it shipped.
- **A vendor gap is a "not yet", not a "never", until you re-fetch on a later day.** JSE
  bars can arrive 2+ days late — STX40.JO's 08-11 close showed up on 08-13 after two failed
  retries and had already been written up as a permanent hole. Re-fetch before concluding.
- **yfinance can stamp the last row of a window with the wrong date**, but only for a ticker
  that is genuinely missing that session: the in-progress bar slides into the empty slot. So
  backfilling a gap while the market is still trading can write *today's* price under
  *yesterday's* date. The `dropna(subset=["close"])` calls in `data/ingest.py` are what stop
  it (the live bar has no close yet) — load-bearing, never fillna them. Don't backfill a
  window ending on a session still trading.
- **Widening the fetch window does not recover a missing bar** — it only invents one. Measured
  on STX40.JO 2026-08-14: narrow one-day windows and a wide window return *identical* closes
  for every genuinely published date (08-11 10857, 08-12 10770). The only row the wide window
  adds is a phantom — 08-13 with a NaN close, which is that day's live session sliding into
  the empty slot. A wide window ending *before* today produces no phantom. So a one-day fetch
  returning nothing means the vendor has nothing; the fix is to re-fetch on a later day, never
  a broader range. (An earlier version of this file claimed the opposite, from a diagnosis
  that mistook the phantom for recovered data.)
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
  Note what the surviving links point *into*: `Docker.app/Contents/Resources/bin/`. That is
  inside the app bundle, so a Docker Desktop upgrade that moves or renames that directory
  breaks `docker`, `docker-credential-osxkeychain` and `hub-tool` for all 17 launchd jobs
  at once — and silently, since nothing runs `which docker` after an upgrade. Re-check with
  `readlink -f /opt/homebrew/bin/docker` after upgrading. Checked 2026-08-23 on 4.87.0:
  `docker` and `docker-credential-osxkeychain` both still resolve, `hub-tool` has gone from
  PATH and nothing uses it.
- **BuildKit hangs resolving registry metadata while the network is fine.** Symptom is
  `failed to solve: DeadlineExceeded` on the `FROM` lines. Connectivity and the credential
  helper are both red herrings: `curl https://ghcr.io/v2/` returns 401 in under a second,
  and a *running container* reaches ghcr.io in 0.3s. The difference is the path — `docker
  info` shows builds routed through Docker Desktop's own proxy at
  `http.docker.internal:3128`, and that is what stalls.
  **Fix: `docker pull` the base images named in the `FROM` lines**, then build. With them
  local, BuildKit resolves metadata without the proxy round-trip and the build runs normally.
  Two things that did *not* work, both tried on 2026-08-26: restarting Docker Desktop, which
  had appeared to fix it on 08-23 and did nothing on 08-26 — so the earlier advice here to
  restart was wrong, or at best a coincidence; and `DOCKER_BUILDKIT=0`, which hangs on the
  same lookup. Note `docker pull` itself hung on 08-23 and worked on 08-26, so try it first
  and treat a hang there as the same fault rather than a different one.
  (`UseContainerdSnapshotter` is on, which changes how BuildKit resolves images — a plausible
  contributor, never confirmed.)
- **Never pipe a build to `/dev/null`.** A failed build is otherwise indistinguishable from a
  cache hit, so the stale image keeps serving while you believe you deployed. This has now
  cost time twice: once on 08-23 for an hour, and again on 08-26 immediately after being
  written down here. Grep the container for the change instead of trusting the build ran:
  `docker compose exec -T <svc> grep -c '<new symbol>' /app/src/...`.
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
  Screenshots carry data through 2026-08-21 and show the live decomposition on both
  markets; regenerate when the dashboard changes shape — recipe in docs/roadmap.md "Next",
  and measure the capture height at 1440 width or the page reflows and the shot gains a
  tail of empty black.
- **Declined, don't re-propose**: a local LLM Q&A layer over the data
  ([ADR 0004](docs/adr/0004-no-llm-question-answering-layer.md)). The `verdict()` functions
  in the React cards ARE the summarization layer — deterministic, unit-tested, cannot
  fabricate a statistic; any safe LLM design just restates them. Ad-hoc questions go to
  DBeaver. Write new explanations as verdict functions, not model calls. Same call as
  declining Spark.
