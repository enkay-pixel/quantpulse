# Roadmap & project state

**Updated 2026-07-23.** What exists today, how it actually performs, and what comes next.
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

**Quality gates:** 204 Python tests (156 unit + 40 integration against a disposable
database that runs a real `dbt build` + 8 Dagster), 59 Vitest, 74 dbt checks, plus mypy /
ruff / eslint / tsc / compose validation — all enforced in CI.

## Current state (2026-07-23)

Two markets, each with its own champion, books and evidence. **Every performance figure
below is in-sample replay** — the live phase begins at each champion's promotion and is the
only number worth judging.

| | NYSE (XNYS) | JSE (XJSE) |
|---|---|---|
| Universe | 50 tickers | 29 (Top 40 with usable history) |
| Price bars (from 2018) | 107,500 | 59,929 |
| Champion | v1 · IC 0.026 · **holdout Sharpe 0.21** | v2 · IC 0.055 · **holdout Sharpe 1.32** |
| Quantile width | 20% (≈10/side) | 35% (≈10/side, set from breadth) |
| Options | 83,555 quotes, 4 snapshot days | none (no free JSE chain data) |

**Replay book performance** (daily / horizon / long-only), in-sample:

| book | XNYS ann · Sharpe | XJSE ann · Sharpe |
|---|---|---|
| `daily` | 7.7% · 0.73 | 21.8% · 1.94 |
| `horizon` (21d) | 14.3% · 1.30 | 34.8% · 2.94 |
| `long_only` | 34.6% · 1.16 | 41.9% · 1.41 |

**Read these carefully.** The horizon book's edge over daily is ~85% trading cost, not
signal (see the resolved horizon-mismatch finding below). The long-only book's higher
return is market beta it carries by construction — that is what the CAPM decomposition
strips out. And every number carries survivorship and in-sample bias. NYSE's true holdout
Sharpe is 0.21, JSE's 1.32; on 29 JSE names with ~8 years, that 1.32 has wide error bars
and only live days will settle it.

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
  window. NYSE's true holdout Sharpe was 0.21, JSE's 1.32 — the replay curves sit far
  above both. Read the replay as a description of the fit, not as evidence of skill.
- **JSE breadth.** 29 names at 35% quantiles is ~10 per side — comparable to NYSE by
  design — but the pool it draws from is thin, one name (BHG.JO) has only half the history,
  and Naspers/Prosus is a large, Tencent-linked share of the index. A holdout Sharpe of
  1.32 on this many names has wide error bars.
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
  dashboard 8080 · Postgres 5432 (database `market`).
- Schedules run **only while the stack is up**, and each market ingests in its own
  timezone two hours after its own close (NYSE 18:00 ET, JSE 19:00 SAST). Processing runs
  once after the latest close (19:00 ET), then a Saturday 09:00 ET retrain per market plus
  a drift-triggered retrain sensor. All schedules ship `RUNNING`.
- **Options snapshots must run post-close** (NYSE only). Measured on the same universe:
  post-close averages ≈33% ATM IV (realistic) versus ≈2.1% pre-market (stale, untraded
  contracts). A full 50-ticker snapshot takes ~10 minutes and commits per ticker, so it is
  safe to interrupt and simply re-run. The repair sensor is gated to post-close so it never
  fills a partial day with pre-market junk.
- Missed days are safe: ingestion is idempotent and partitioned by `(date, exchange)` —
  re-materialize the affected partitions in the Dagster UI.
- Dates are exchange dates, never the container's UTC date: use `calendar.market_today()`.
- **Base images**: node 26 is in; python stays on 3.12 (3.14 breaks dbt-common's
  dataclass introspection under PEP 649 — verified by building, recorded in `dependabot.yml`).

## Next

1. **Let it run.** The live track record and the options history only accrue with time;
   no code substitutes for weeks of scheduled runs. Highest value, zero effort.
2. **Let the JSE live phase judge the 1.32.** Its live record begins at the v2 promotion
   (2026-07-23). A holdout Sharpe that high on 29 names is either signal or a favourable
   draw, and only accumulated live days distinguish them.
3. **Screenshots** predate the market switcher — regenerate with headless Chrome against a
   running stack, now per market:
   `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu
   --hide-scrollbars --force-device-scale-factor=2 --window-size=1440,1230
   --screenshot=docs/assets/dashboard.png --virtual-time-budget=9000 "http://localhost:8080/?market=XNYS#overview"`
   (tab slugs `overview`/`evidence`/`options`/`model-book`, `?market=XNYS|XJSE`; tune height).
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

## Known issue: the promotion gate compares across cost regimes

The champion's stored metrics (`model_runs`, MLflow) were computed on 2026-07-18 under the
**old** backtest, which charged a flat turnover of 0.4. Challengers are now scored with
*measured* turnover, averaging 0.533 — roughly 33% more cost. So a challenger is judged
under a stricter regime than the incumbent it must beat.

Sizing it: the champion's stored holdout Sharpe is 0.205 on a 2.27% annual return. The
extra cost is ≈0.16%/yr, which re-scored today puts it near **0.19**. The promotion margin
is 0.05, so the effective bar sits about 0.015 too high — around 30% of the margin.

Left as-is deliberately. The bias favours the incumbent, which is the safe direction to
fail, and changing the decision gate immediately before a long unattended stretch is worse
than the bias itself. **If a challenger is ever rejected within ~0.02 of the bar, that
rejection is not trustworthy** — re-score both under current code before believing it.

The durable fix is structural rather than a one-off re-score: stored metrics go stale
whenever evaluation code changes, so `ml/pipeline.py` should re-evaluate the incumbent with
today's backtest instead of reading numbers computed by a previous version of itself.

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

**Still to be earned:** every JSE figure above is in-sample replay. Its live phase begins
at the 2026-07-23 promotion and is the only number that will settle whether a holdout
Sharpe of 1.32 on 29 names with ~8 years of history was signal or a favourable draw.

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
