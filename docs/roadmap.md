# Roadmap & project state

**Updated 2026-08-19.** What exists today, how it actually performs, and what comes next.
For *how* it was built and every bug paid for along the way, see
[development-history.md](development-history.md); for design rationale see [adr/](adr/).

## What this project is

A local-first, zero-cost MLOps platform for a self-adapting ML investing model, now running
**two markets — NYSE and the JSE**. Dagster orchestrates daily ingest → features → champion
scoring → paper books → drift checks per market; weekly and drift-triggered retraining
promotes challengers through the MLflow registry; dbt builds analytics marts; FastAPI serves
them; a React dashboard presents the evidence with a market switcher. Everything runs free
on one 16 GB machine via Docker.

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
| M11 | Multi-market | Exchange as a first-class dimension (schema, calendar registry, per-market partitions/schedules/champions/books/marts); JSE added; dashboard market switcher; resource-headroom check; three paper books (`daily`/`horizon`/`long_only`) |

**Quality gates:** 391 Python tests (232 unit + 140 integration against a disposable
database that runs a real `dbt build` + 19 Dagster), 59 Vitest, 63 dbt tests (59 data +
4 unit), plus mypy / ruff / eslint / tsc, shellcheck, markdownlint,
`alembic check` for model/migration drift, and compose validation — all enforced in CI.

Read that with the caveat the log earns: every serious bug found so far shipped with CI
fully green. The tests catch regressions in what has already gone wrong; the bugs that
matter have been found by reading the data and asking whether it makes sense.

## Current state (2026-08-19)

### The live record — the only numbers worth judging

XNYS crossed the 20-session floor on 2026-08-18, so its ratios are published for the first
time. They are negative.

| | NYSE (XNYS) | JSE (XJSE) |
|---|---|---|
| Live sessions | 24 (from 2026-07-20) | 20 (from 2026-07-23) |
| Total return | **−1.15%** | **+1.70%** |
| Sharpe | **−1.27** | **+2.68** |
| Annualized vol | 9.2% | 8.1% |
| Win rate | 45.8% | 50.0% |
| Beta / R² | 0.07 / 0.011 | −0.09 / 0.033 |
| Alpha (annualized) | −17.5% ± 30.6% | +24.7% ± 30.3% |
| Alpha t-statistic | **−0.57** | **+0.81** |
| Information ratio | −2.60 | −3.17 |

The two markets point opposite ways and neither one resolves. Each alpha carries a standard
error larger than the estimate itself, so both t-statistics sit well inside the ~2 that would
make either distinguishable from zero. After roughly a month live, the record does not
separate skill from noise on either market — in either direction.

This is a weaker claim than this table used to make. It previously read "the sign is
meaningful; the magnitude is not yet", quoting a −22.6% alpha. A sign is only meaningful once
it clears its own error bar, and neither of these does. The annualized figures are a total
return of about a percent scaled up by 252, not a rate anything has sustained.

The replay comparison still stands as the useful part — NYSE Sharpe **+0.74**, JSE **+1.94**
in-sample against a live record that resolves to nothing — because the point was never the
live sign but the size of the gap between a fit and a forecast. Keeping the phases apart is
why that is visible at all rather than blended into one flattering number.

Beta 0.07 and −0.09 with R² near zero confirm the book is market-neutral as designed, so
whatever these returns are, they are not hidden market exposure. The information ratio is
negative on both markets including the one that made money: it is benchmark-relative rather
than beta-adjusted, so a market-neutral book that sits out a rising index scores badly on it
by construction. It and alpha answer different questions and are expected to disagree here.

Books trail prices by one session by construction.

### The replay — in-sample throughout

Everything below describes a fit, not a forecast.

| | NYSE (XNYS) | JSE (XJSE) |
|---|---|---|
| Universe | 50 tickers | 29 (Top 40 with usable history) |
| Price bars (from 2018) | 108,240 | 60,334 |
| Champion | v1 · IC 0.026 · **holdout Sharpe 0.21** | v3 · IC 0.063 · **holdout Sharpe 1.51** |
| Quantile width | 20% (≈10/side) | 35% (≈10/side, set from breadth) |
| Options | 566,646 quotes, 19 snapshot days | none (no free JSE chain data) |

A connectivity outage cost **three consecutive option snapshot days (08-11 to 08-13)**, and
those are gone for good — chains are live-only, so a missed day is a permanent hole. Every
price session was recoverable and has been recovered, including a full XNYS day that failed
20 ingest attempts overnight and landed first try once the connection returned.

Both benchmark gaps have since closed. STX40.JO's 08-12 bar arrived two days late and was
backfilled by hand; its 08-13 bar arrived a day later still and was recovered **by the
catch-up sensor's benchmark trigger without intervention** — the first time that mechanism
closed a gap unaided. `benchmark_freshness` passes on both markets.

Those champion Sharpes are the numbers each model was *promoted* on, and they are not
comparable across models — see the retrain log below for why. Both were measured under the
pre-fix evaluation (early stopping on the promotion holdout), so neither is a clean
out-of-sample estimate.

### Retrain log

| Date | XNYS | XJSE |
|---|---|---|
| 2026-07-25 | candidate promoted on a mismatched exam, **demoted same day** (incident 24) | v3 promoted, like-for-like vs v2 |
| 2026-08-01 | v3 rejected — 1.595 vs incumbent **2.570** | v4 rejected — 1.326 vs incumbent **1.786** |
| 2026-08-08 | v4 rejected | v5 rejected |
| 2026-08-15 | v5 rejected — IC 0.0698 vs incumbent **0.1884** | v6 rejected — IC 0.0679 vs **momentum baseline 0.1159** |

The 2026-08-01 run is the first under the corrected gate, and it is worth reading closely
because it demonstrates the failure it was built to prevent. Those incumbent figures appear
nowhere in the database: they were computed at decision time by re-scoring each champion on
its challenger's exact 311-day holdout. XNYS v1's **stored** Sharpe is 0.205, from a
131-day window; re-examined on the longer window it scores **2.570**. Same model, same
code, different exam, a 12× difference in apparent skill.

So the old gate would have compared the challenger's 1.595 against a stored 0.205, declared
a landslide, and promoted a model that is in fact substantially worse — repeating the
previous week's error exactly. The new gate rejected both challengers without drama. One
retrain is not a trend, and rejection may or may not turn out to be the normal outcome, but
the mechanism is now demonstrated in production rather than only in tests.

### Promotion has stalled on both markets

Three consecutive retrains have promoted nothing, and the two markets are stalled for
different reasons — which the weekly check now separates rather than reporting as one count:

- **XNYS** — nothing has beaten the champion (best challenger IC 0.0852 against 0.1000). The
  gate is right and the model is stuck.
- **XJSE** — a challenger *did* beat its champion (0.0684 against 0.0625) and was rejected
  anyway, because it lost to the momentum baseline. The JSE lineage is improving on itself
  while still failing to justify itself.

The 2026-08-15 run was the first under the standing competitor, and it is the first
promotion in the project's history blocked by something other than the incumbent.

**Replay book performance** (daily / horizon / long-only), in-sample:

| book | XNYS ann · Sharpe | XJSE ann · Sharpe |
|---|---|---|
| `daily` | 7.7% · 0.73 | 21.8% · 1.94 |
| `horizon` (21d) | 14.3% · 1.30 | 34.8% · 2.94 |
| `long_only` | 34.6% · 1.16 | 41.9% · 1.41 |

**Read these carefully.** The horizon book's edge over daily is ~85% trading cost, not
signal (see the resolved horizon-mismatch finding below). The long-only book's higher
return is market beta it carries by construction — that is what the CAPM decomposition
strips out. And every number carries survivorship and in-sample bias. NYSE's holdout
Sharpe is 0.21, JSE's 1.51 (pre-fix evaluation; see above); on 29 JSE names with ~8
years the JSE number has wide error bars and only live days will settle it. A related
regime finding from incident 24: raw 63-day momentum IC ran **+0.039 over Mar–Dec 2025
and −0.004 since** — replay windows that include that stretch flatter any momentum model.

- **Signal quality:** NYSE quintile forward returns are monotonic across the replay window
  (real ranking skill, modest in magnitude). JSE IC (0.055) is roughly double NYSE's.

## Resolved: the horizon mismatch was a cost problem, not a signal problem

**Settled 2026-07-22.** The model forecasts 21-day returns while the paper book
rebalanced daily, and the two disagreed wildly (Sharpe 0.26 vs 1.33). Rather than pick
one, both now run over the same predictions as separate *books* — a book being one way
of turning the signal into a portfolio. They differ in exactly one thing, how often they
rebalance, which is what lets the difference between them be blamed on that and nothing
else. Measured over the full replay:

| book | rebalance | ann. return | Sharpe | max DD | mean turnover | cost drag |
|---|---|---|---|---|---|---|
| `daily` | every day | 7.76% | 0.73 | −26.9% | 0.230 | **5.79%/yr** |
| `horizon` | every 21 days | **14.40%** | **1.31** | −16.2% | 0.026 | 0.65%/yr |

Add the charged costs back to each book and the 6.64 percentage-point gap splits cleanly:

- **85% of it (5.68 points) is trading cost.** The daily book trades 9× as much to chase
  a signal that only refreshes meaningfully every few weeks.
- **15% (0.97 points) is the signal itself.** Before costs the two books are close —
  14.76% vs 15.72% — so the 21-day forecast is *not* badly degraded when applied daily.
  It simply isn't worth 7%/yr in commissions and slippage to act on it that often.

This also closes the confound: the horizon book (Sharpe 1.31) now agrees with the
horizon-matched backtest (1.33). They disagreed before because they described different
portfolios *and* the paper book double-charged costs through a mismatched capital
convention — both fixed.

**Knock-on effect worth knowing about:** correcting the double-charged costs moved the
daily book's CAPM alpha from **−0.56% to +4.74% annualized** (beta −0.05, R² 0.007
unchanged). Nothing about the signal changed — the old figure was measuring a portfolio
that paid twice for its trades. The information ratio is still negative (−0.34), and the
window is still in-sample, so this is *not* evidence of skill; it is one bug's worth of
distortion removed from a number the dashboard reports.

**The caveat that governs every number above:** this is replay, scored in-sample over the
champion's own training window, and it carries the survivorship bias described below. The
champion's true out-of-sample Sharpe was 0.21. Read the table as *"trading daily destroys
value through costs"* — a mechanical conclusion that holds regardless of whether the
signal is any good — and not as *"this earns 14% a year."*

Both books are rebuilt on every `portfolio_equity` materialization, stored in
`portfolio_snapshots` keyed by `variant`, and compared at `GET /portfolio/books`. The
dashboard and every dbt mart still describe the `daily` book, so the evidence layer is
unchanged.

### Original sweep that surfaced it

`quantpulse sensitivity` sweeps the backtest across trading-cost and short-borrow
assumptions. Two things came out of the first run, and the second matters more:

- **Costs are not what's holding the strategy back.** On the monthly-rebalanced
  backtest the result degrades gracefully — 17.2% annualized at zero cost, still 8.3%
  at a punitive 1% round trip plus 3% borrow. The breakeven round-trip cost is
  **above 1%**: the sweep never found it, because the strategy stays profitable at the
  harshest cost tested. (Re-measured 2026-07-22 after the turnover fix below; the
  earlier "~1%" figure was the grid ceiling being misreported as a measurement.)
- **But that backtest and the live paper book were not the same strategy.** The model
  forecasts **21-day** forward returns and the backtest held positions for roughly that
  long, while the paper portfolio rebalanced **daily** — using a 21-day signal to bet on
  tomorrow. That mismatch is what the dual-book work above set out to measure, and it
  turned out to be worth ~6.6pp a year, almost all of it in trading costs.

**Caveat that keeps this honest:** the sensitivity run scores the champion over its own
training window, so those figures are largely *in-sample*. The champion's true holdout
Sharpe was 0.21. Do not read 1.33 as a real edge — read it as evidence about how the
constructions differ, which is a question about design, not about alpha.

## Known biases in the replay

Every backtested number on this project carries these. They are stated rather than fixed,
because fixing them needs data that costs money — but a result you cannot caveat is a
result you should not quote.

- **Survivorship bias (the big one).** `configs/universe.yaml` lists each market's tickers
  *as they exist today*, and the replay runs back to 2018-01-02. Every name in it survived
  to 2026: no delistings, no bankruptcies, no index deletions, no acquisitions. Free
  point-in-time index constituents effectively do not exist, so the honest move is to
  treat replay returns as an **upper bound**, not an estimate. It biases in the same
  direction as every other soft assumption here, which is exactly why it is written down.
- **In-sample scoring.** The replay equity curve scores each champion over its own training
  window. NYSE's holdout Sharpe is 0.21, JSE's ~1.5 — the replay curves sit far
  above both. Read the replay as a description of the fit, not as evidence of skill.
- **JSE breadth.** 29 names at 35% quantiles is ~10 per side — comparable to NYSE by
  design — but the pool it draws from is thin, one name (BHG.JO) has only half the history,
  and Naspers/Prosus is a large, Tencent-linked share of the index. A holdout Sharpe of
  ~1.5 on this many names has wide error bars.
- **Cost model resolution.** Trading costs are linear in turnover with no market-impact
  term and no bid-ask spread by name. Fine for liquid large caps at small size; wrong the
  moment the universe widens or size grows. JSE shorting in particular is thinner and dearer
  than the 1%/yr borrow the backtest charges.
- **No shorting constraints.** The long/short books assume every name is shortable at the
  modeled borrow rate. Hard-to-borrow names cost far more, and sometimes are simply
  unavailable — which is exactly why the `long_only` book exists alongside them.

Fixed on 2026-07-22: the backtest previously charged a **flat** turnover equal to the
quantile width (0.4) rather than measuring position churn, so costs were blind to
whether the book actually traded. Measured turnover averages 0.533 (range 0.28–0.85) —
the old proxy understated trading costs by ~33%.

Also fixed the same day: `ml/portfolio.py` weighted each side at 1.0 (gross exposure
2.0) while computing the *same* halved `(long − short) / 2` return, so it charged ~2×
the cost of the backtest for identical churn, and charged no borrow at all. Both books
now share `ml/backtest.py`'s convention — 0.5 per side, gross exposure 1.0, borrow
accrued daily. This is why the daily book's Sharpe moved from 0.26 to 0.73 without any
change to the signal: it had been paying double for its trades.

Fixed 2026-07-23 while onboarding the JSE: Yahoo intermittently reports a JSE close in
Rand rather than cents (SBK.JO went 22,775 → 228.86 → 23,322 in three sessions with
normal volume). Left in, that −99%/+100× round trip compounded the first JSE book to
8,788×. `data/cleaning.py` repairs a close sitting a clean factor of 100 from *both*
neighbours — deliberately narrow, since no equity falls 99% and recovers 100-fold in two
days. Four glitches were found and repaired. Also fixed: unreliable ratios are now nulled
in the marts below `min_days_for_ratios` (20), so a three-day live phase no longer serves
a Sharpe of −54.93 to any consumer; and the promotion gate now has a first-champion Sharpe
floor, after the first JSE candidate was promoted at holdout Sharpe −0.069 (a model that
lost money out-of-sample) purely because "beat the incumbent" cannot gate a first model.

## Operating notes

- `make up` (fast, reuses images) · `make build` after code changes · `make down`.
- Ports: Dagster 3000 · MLflow **5001** (macOS AirPlay owns 5000) · API 8000 ·
  dashboard 8080 · Postgres 5432 (database `market`). All published on **127.0.0.1
  only** — Dagster and MLflow ship without auth, and an exposed registry would let
  anyone on the LAN swap the champion (see architecture.md).
- Schedules run **only while the stack is up**, and each market ingests in its own
  timezone two-and-a-half hours after its own close (NYSE 18:30 ET, JSE 19:30 SAST).
  Processing runs once after the latest close (19:00 ET), then a Saturday 09:00 ET
  retrain per market plus a drift-triggered retrain sensor. All schedules ship `RUNNING`.
- **Options snapshots must run post-close** (NYSE only). Measured on the same universe:
  post-close averages ≈33% ATM IV (realistic) versus ≈2.1% pre-market (stale, untraded
  contracts). A full 50-ticker snapshot takes ~10 minutes and commits per ticker, so it is
  safe to interrupt and simply re-run. The repair sensor is gated to post-close so it never
  fills a partial day with pre-market junk.
- Missed days are safe: ingestion is idempotent and partitioned by `(date, exchange)` —
  re-materialize the affected partitions in the Dagster UI. The catch-up sensor requests
  them automatically for two reasons: thin coverage, or an **absent benchmark bar** even on
  an otherwise-complete session (the benchmark is one ticker, so it never moves the coverage
  ratio, but the CAPM marts inner-join it and lose the whole day). Each session gets three
  attempts per day, and the budget **resets daily** — an outage that burns its attempts
  recovers by itself once connectivity returns. Benchmark-only retries additionally expire
  after five sessions, since retrying cannot help if the vendor never publishes.
- **Option snapshots do not survive an outage.** Chains are live-only, so a day the stack
  was down post-close is a permanent hole — unlike price bars, there is nothing to re-fetch.
  This is the one part of the pipeline where downtime costs data outright (08-11 and 08-12
  were lost this way).
- A vendor gap is usually a *late* bar, not a missing one: re-fetch on a later day before
  concluding anything. And do not backfill a window whose end falls on a session still
  trading — for a ticker with a genuine hole, the in-progress bar can slide into the empty
  slot under the wrong date (see data-dictionary.md).
- Dates are exchange dates, never the container's UTC date: use `calendar.market_today()`.
- **Base images**: node 26 is in; python stays on 3.12 (3.14 breaks dbt-common's
  dataclass introspection under PEP 649 — verified by building, recorded in
  `dependabot.yml`); the MLflow image and uv are pinned to their client/lockfile versions
  (`latest` meant unreproducible builds). Image builds survive flaky laptop Wi-Fi: uv
  cache mounts (retries accumulate wheels), bounded download concurrency, pip timeouts.

## Audited against an external rubric

Scored against the ML Test Score (Breck et al.) on 2026-08-14: **2.0** — *basic
productionisation*. The score is the minimum of four sections, and the shape is the finding:
monitoring 6.0 and infrastructure 4.0 against **model development 2.0**. The pipeline around
the model has had far more adversarial attention than the model itself. Full itemised scoring
and the ranked gap list: [ml-test-score.md](ml-test-score.md).

That gap is now closed, and it found something. `quantpulse baseline` scores the champion
against noise, momentum, reversal and a linear ridge on one shared holdout. On the **JSE,
plain 63-day momentum beats the champion on every metric** (IC 0.117 vs 0.068, Sharpe 2.28 vs
1.84, half the drawdown) with zero parameters. On the **NYSE the champion wins decisively**
(IC 0.191 vs momentum's 0.016). Read the JSE replay numbers accordingly: they may be
measuring momentum rather than the model. Detail in [ml-test-score.md](ml-test-score.md).

## Decisions standing, and what would change them (2026-08-24)

Each of these is measured and settled as far as measurement can settle it. None is acted on,
and each names the evidence that would reopen it. Write-ups in [findings/](findings/README.md).

**Keep running the JSE model, despite it losing to momentum.** The case against it is
holdout IC — momentum 0.1094 against champion v3's 0.0569 — plus a staleness curve that is
negative at every model age. That case rests entirely on a backtest metric this project has
just shown does not predict live behaviour: the NYSE incumbent scored 0.1777 on its holdout
while the live book lost money. Demoting on that basis would repeat the error documented in
[the incumbent finding](findings/unbeatable-incumbent.md). The JSE live record is positive
(+1.70%, Sharpe 2.68) but unresolved at 20 sessions, alpha t +0.81. *Reopen at 60 live
sessions, or sooner if live Sharpe turns negative or alpha resolves either way.* Withdrawing
it is one command (`quantpulse demote`) whenever that call is made.

**Do not prune the NYSE feature set**, though pruning to `vol_21` resolves at t +3.00 across
sixteen tuned seeds. `vol_21` was selected on this panel, so the result supports "pruning
helps here" rather than "`vol_21` is the column", and +0.0133 is smaller than the
round-to-round spread early stopping already contributes. *Reopen on confirmation from a
fresh panel period.*

**Do not set a per-market round count**, though a fixed 25 rounds beats early stopping on the
JSE at t +3.43. Nothing resolves on the NYSE, and the count that looks best there is worst on
the JSE. *Reopen on confirmation from a fresh panel period.*

**Offline/online correlation stays open by construction.** It cannot be closed by work, only
by time — 24 NYSE and 20 JSE live sessions is far too short to correlate against anything.
*Revisit near 250 sessions.*

**Keep recharts on 2.x.** The 2.x branch is end-of-life upstream and `npm ci` says so on every
install, but 3.x changes the chart API across six components, `npm audit` reports no
vulnerabilities, and nothing in 3.x is needed. The Dependabot major-ignore stays. *Reopen on
a security advisory, or when a 3.x-only feature is actually wanted.*

## Next

1. **Let it run.** The live track record and the options history only accrue with time;
   no code substitutes for weeks of scheduled runs. Highest value, zero effort. **XNYS is
   3 sessions from the 20-day floor** (17 live days), at which point the marts start
   publishing its Sharpe, information ratio, beta and win rate instead of nulling them —
   the first ratios this platform will have earned rather than replayed. XJSE follows about
   a week later. Read them as a first reading on a small sample, not a verdict.
2. **Let the JSE live phase judge the champion (now v3).** Its live record accrues since
   the first JSE promotion (2026-07-23). A holdout Sharpe of 1.5 on 29 names is either
   signal or a favourable draw — the momentum-rich 2025 stretch (incident 24) leans
   toward the latter — and only accumulated live days distinguish them.
3. **Screenshots** carry data through 21 Aug 2026 and show the live decomposition on both
   markets, including alpha with its standard error. Regenerate when the dashboard changes
   shape or the live record reaches a milestone worth showing. Recipe, per market and tab:
   `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu
   --hide-scrollbars --force-device-scale-factor=2 --window-size=1440,HEIGHT
   --screenshot=docs/assets/dashboard.png --virtual-time-budget=9000
   "http://localhost:8080/?market=XNYS#overview"` (tab slugs
   `overview`/`evidence`/`options`/`model-book`, `?market=XNYS|XJSE`).
   **Measure HEIGHT at 1440 width**, not at whatever the browser happens to be: read
   `document.body.scrollHeight` with the viewport already at 1440, because the layout
   reflows and a height taken at a narrower width leaves a page of empty black below the
   content. Current values — overview 1257, evidence 1277, options 1149, model-book 686.

4. **Options history analytics** — once ~20+ snapshots exist: IV rank/percentile,
   realized-vs-implied volatility, IV-change signals. This is the payoff for the
   snapshot-forward design, and it needs no new data source.
5. **Model improvements** — only once live evidence justifies them: richer features
   (fundamentals, cross-asset), alternative targets, or an ensemble. Measure first.
6. **Deferred dependency majors** — typescript / eslint / recharts carry documented
   Dependabot ignore rules; python-3.14 base image declined (dbt-common/PEP 649); dbt
   `tests:` → `data_tests:` rename when the tooling requires it.
7. **Databricks Free Edition companion repo** — the same pipeline expressed in
   PySpark/Delta as a separate portfolio piece. Spark was deliberately *not* used here:
   the data is far too small to justify it, and being able to say so is the stronger
   engineering signal.

## Resolved: the gate no longer trusts stored incumbent metrics (incident 24)

This section used to size a ~0.015 bias from comparing a measured-turnover candidate
against a flat-turnover incumbent, and prescribed the durable fix. The first scheduled
retrain (2026-07-25) demonstrated the failure mode at ~100× that size: the 07-20 JSE
backfill had grown the XNYS panel from 2023+ to 2018+, the fractional 15% holdout cut
slid nine months earlier into a momentum-rich 2025 stretch (raw 63-day momentum IC
+0.039 there vs −0.004 since), and a candidate scoring 1.89 on the long exam "beat" an
incumbent whose stored 0.205 came from a different, harder window. The candidate was
auto-promoted; a matched 2026-only exam (out-of-sample for both) showed no improvement
— its IC was negative. It was demoted the same day (see `model_runs`).

The durable fix is in: `ml/pipeline.py` **re-scores the incumbent on the candidate's
exact holdout under current code** at decision time — stored metrics are never consulted
(a poisoned-stub test enforces this). The final fit early-stops on an inner validation
split so the holdout stays untouched, and every `model_runs` row records its holdout
window (`holdout_start/end/days`), so a moved exam is visible in the audit trail rather
than archaeology.

**Confirmed in production 2026-08-01.** The next retrain hit the same conditions and the
gate handled them silently: XNYS v1 scored **2.570** re-examined on the challenger's
311-day holdout against its stored **0.205**, so the challenger's 1.595 — which the old
gate would have read as a landslide win over 0.205 — was correctly rejected. The
comparison the gate makes is now internally consistent by construction; the stored number
remains a historical record of what a model was promoted on, not a figure to compare
against.

## Measured: the gate's metric was noisier than its own decision margin

Four challengers were rejected across the 2026-08-01 and 08-08 retrains. Rather than
assume that meant they were worse, the noise was measured — refit one specification
changing only the RNG, and score one fixed model across different windows.

| | Sharpe | IC |
|---|---|---|
| **XNYS** seed re-roll (12 fits) | 1.565 ± **0.119** (spread 0.38) | 0.083 ± **0.003** |
| **XJSE** seed re-roll (12 fits) | 1.808 ± **0.235** (spread 0.87) | 0.067 ± **0.004** |
| One fixed model, 6-month windows | sd ≈ **2.0**, range 0.6 → 5.9 | — |

The old gate required a challenger to beat the champion's Sharpe by **0.05**, five to ten
times *below* the noise of simply re-rolling the seed — and ~40× below the window noise.
Decisions inside that band were coin flips wearing a number. IC is 2–2.4× more stable in
relative terms (3.6% vs 7.6% on XNYS), which is unsurprising: Sharpe divides by a
volatility estimate and inherits noise from both parts, then gets amplified by regime.

So **the gate now compares IC** with a per-market margin set at 2 sd of the measured
re-roll (0.006 XNYS, 0.008 XJSE), and Sharpe is demoted to a wide veto that may overrule a
promotion but never cause one. Replayed over both retrains, no decision changes — but the
*reasons* do, and one is instructive: on 08-01 the JSE candidate's IC was genuinely
**higher** (+0.0042), and the margin correctly refused it as smaller than a re-roll.

Two related findings from the same investigation, both recorded because they overturn
plausible-sounding intuitions:

- **Early stopping on RMSE is a no-op.** Validation RMSE never improves on 21-day forward
  returns — it drifts *worse* from round 1 — so the fit stops after 1–6 trees every time.
  It costs nothing (holdout results are flat from 6 to 800 trees) but it is not the tuned
  stopping rule it appears to be.
- **More history helps; the incumbent's edge is not contamination.** Restricting training
  to 2023+ scored 0.807 against 1.787 for the full panel. And the incumbent's advantage
  sits entirely in the window it never early-stopped against (+1.39) rather than the
  overlapping one (−0.31) — the opposite of the leak that was suspected.

**Caveat**: these numbers come from a holdout inside the 2025 momentum-rich stretch, which
inflates Sharpe. Re-measure with the variance study when the panel or evaluation code
changes materially, rather than treating the margins as permanent.

## JSE: what the first champion cost to establish

The first JSE candidate was promoted at holdout Sharpe **-0.069** — a model that lost
money on data it had never seen — because the promotion gate had no floor for a *first*
champion ("beat the incumbent" cannot gate a model with no incumbent). It has since been
withdrawn, a `min_first_sharpe` floor added, and the second candidate promoted at
**+1.32**.

**Attribute that carefully.** Two things changed between the two trainings, and only one
of them was the intended experiment:

| change | effect |
|---|---|
| Repaired 4 vendor unit glitches (`data/cleaning.py`) | **most of it** — holdout IC 0.024 → 0.055, and IC is width-independent |
| Widened JSE quantiles 20% → 35% | **+0.08 Sharpe** in a same-data, same-model sweep |

Measured on one panel with one model, varying only the width: 20% gives 49.3%/2.71,
35% gives 37.9%/**2.79**, 40% gives 32.6%/2.66. So widening is a small risk-adjusted
improvement that trades return for stability — not the cause of the turnaround.

The width itself is set from breadth, not tuned: 35% of 29 JSE names and 20% of 50 US
names are both ~10 positions per side. Slicing a thin market at the wide market's
percentile would hold 6, roughly doubling per-position idiosyncratic risk.

**Still to be earned:** every JSE figure above is in-sample replay. The live phase began
at the 2026-07-23 promotion (the champion is now v3, holdout Sharpe 1.51 under the same
pre-fix evaluation) and is the only number that will settle whether a holdout Sharpe this
high on 29 names with ~8 years of history was signal or a favourable draw.

## Deliberately not doing

- **A local LLM question-answering layer.** Scoped 2026-07-22 and declined — see
  [ADR 0004](adr/0004-no-llm-question-answering-layer.md). Short version: any design safe
  enough to trust reduces the model to restating what the dashboard already says in
  English, because the deterministic `verdict()` functions are the summarization layer and
  they cannot fabricate a number. Ad-hoc questions belong in DBeaver against the
  `analytics` marts. If it is ever revisited, the ADR fixes the order of work.
- **Spark / Databricks in this repo** — see item 6 above; the data does not justify it.

## Why options work the way they do

Free option data is **live-only** — yfinance gives full chains but no history, and real
historical chains cost thousands per year. So options are not a backtested strategy here;
they are an analytics layer that **builds its own history forward**, one daily snapshot at
a time. In a few weeks that becomes a dataset genuinely worth analysing, which is also why
keeping the scheduled runs alive is the single highest-value thing to do.
