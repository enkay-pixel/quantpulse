# Data dictionary — `market` database

> **Three databases share this Postgres server.** Only `market` (schemas `public` +
> `analytics`) is ours — defined by Alembic migrations and `src/quantpulse/db/models.py`.
> The `mlflow` and `dagster` databases are owned by those tools and **must not be modified
> by us**. Their conventions differ on purpose and are not a defect: MLflow stores every
> timestamp as `bigint` epoch-milliseconds and IDs as `varchar` (backend-portable, UTC by
> construction); Dagster uses naive `timestamp without time zone`. If you inspect the server
> in DBeaver and see int/varchar where you expected a datetime, you're almost certainly
> looking at one of those two, not at `market`.

Populated from M1 onward; columns finalized alongside the Alembic migrations. Since M11
the platform is multi-market, so **`exchange` is a dimension** on the tables that need it.
Tickers are globally unique (JSE names carry a `.JO` suffix), so `prices`, `features` and
`predictions` reach their market by joining `universe` rather than carrying the column.

**Types are chosen deliberately:** dates are `date`, all `*_at` timestamps are
`timestamptz`, prices/greeks/IV are `double precision` (matches numpy and the ML stack —
`numeric` would be pedantic here), counts are `bigint`, feature vectors / positions /
metrics are `jsonb`. Categorical *domain* columns carry CHECK constraints that document and
enforce their vocabulary — `asset_type`, `option_type`, `source`, `run_type`, `decision`.
`exchange` and `variant` are intentionally **not** CHECK-constrained: they are config-driven
(markets from `data.calendar.EXCHANGES`, books from `ml.portfolio.BOOKS`) and validated in
Python, so a DB CHECK would duplicate that and force a migration on every new market or book.

| Table | Grain | Purpose |
|---|---|---|
| `universe` | ticker | Tradable universe with metadata (name, type stock/etf, active flag, **exchange** — the source of truth for which market a ticker belongs to) |
| `prices` | (ticker, date) | Daily OHLCV bars, adjusted; source column (yfinance/stooq). Vendor unit glitches repaired on write (see `data/cleaning.py`) |
| `features` | (ticker, date) | Engineered features; cross-sectional ranks are computed **within** each exchange |
| `predictions` | (ticker, date, model_version) | Champion-model forward-return scores, per market's own champion |
| `model_runs` | run id | Training/evaluation/promotion audit log (metrics, decision, MLflow run id, **exchange**). Append-only: a `demotion` row withdraws *its own version's* promotion (the prior champion stands). `metrics` also carries audit strings — the holdout window (`holdout_start/end/days`) and demotion reasons — which the API filters to numbers |
| `drift_metrics` | (date, **exchange**, metric) | KS/PSI feature drift, measured **per market** — pooling halved the signal and hid its size (incident 28). Rows written before 2026-08-11 carry `exchange = 'POOLED'`: they measured both markets mixed and belong to neither, so queries filtering by a real market code correctly skip them |
| `portfolio_snapshots` | **(date, exchange, variant)** | Simulated paper-book equity, exposure, turnover. Several *books* (`daily` / `horizon` / `long_only`) run per market — see [architecture.md](architecture.md) |
| `option_quotes` | (snapshot_date, ticker, expiry, strike, option_type) | Daily live option-chain snapshots + Black-Scholes Greeks. NYSE only (no free JSE chain data). Accumulates forward — no free history exists to backfill |
| `pipeline_alerts` | alert id | Pipeline failures recorded by the Dagster run-failure sensor, served at `GET /alerts`. Operational tail, not an audit trail: trimmed to the newest 200. In the database because the daemon writes it and the API (a different container) reads it |

Every `ticker` column (`prices`, `features`, `predictions`, `option_quotes`) is a foreign
key to `universe.ticker` (`ON DELETE RESTRICT`), so no derived row can point at a ticker the
platform doesn't know.

## `analytics` schema (dbt-managed — see `transform/`)

Every mart below carries `exchange`, so the dashboard's market switcher scopes each one.
The two option marts are single-market by necessity. Ratios (Sharpe, information ratio,
win rate, beta) are **nulled below 20 days** (`min_days_for_ratios`): a handful of days
annualizes to a confident-looking number that is pure noise. Counts and totals survive at
any sample size.

| Relation | Grain | Purpose |
|---|---|---|
| `stg_*` (views) | 1:1 with raw | Typed, renamed staging; `stg_predictions` dedupes to newest model version; `stg_portfolio_snapshots` pins `variant = 'daily'` but keeps every market |
| `fct_daily_returns` | (ticker, exchange, date) | Simple returns + 21-day rolling volatility/mean |
| `fct_signal_performance` | (date, exchange, signal_quintile) | Next-day realized return per signal quintile (1 = strongest), ranked **within each market** — model-skill readout |
| `fct_portfolio_daily` | (date, exchange) | Portfolio with cumulative return, running drawdown, rolling 63d Sharpe, and evidence `phase`, all partitioned per market. **Three phases**: `replay` (before the first promotion), `backfilled` (a day scored by a champion promoted *after* it — in-sample, so excluded from the live record), `live` (genuinely out-of-sample) |
| `fct_portfolio_vs_benchmark` | (date, exchange) | Strategy equity vs that market's benchmark (SPY / STX40.JO) indexed to the portfolio's first date. Joins the benchmark on date **inner**, so a day the vendor has no benchmark bar for is dropped rather than nulled — see the note below |
| `fct_track_record` | (exchange, phase) | Per-phase performance summary — the `live` row is the honest out-of-sample record |
| `dim_universe` | ticker | Members with exchange and price-coverage metadata |
| `fct_alpha_beta` | (exchange, phase) | CAPM decomposition vs the market's benchmark: beta, annualized alpha, R², tracking error, information ratio (Postgres regression aggregates over excess returns) |
| `fct_option_summary` | (ticker, snapshot_date) | ATM implied volatility and put/call open-interest ratio (NYSE) |
| `fct_iv_surface` | (ticker, snapshot_date, expiry, option_type, moneyness_bucket) | Mean IV — the volatility smile/skew and term structure (NYSE) |

### Why two marts can disagree about the live day count

`fct_track_record` counts a day if the paper book has a row for it. `fct_alpha_beta` and
`fct_portfolio_vs_benchmark` additionally need a **benchmark** bar for that date, and they
inner-join to get it — so a day the vendor is missing the benchmark for disappears from
those two while remaining in the track record. The counts then differ by one, with nothing
on screen explaining it.

The `benchmark_freshness` asset check now catches this at ingest rather than leaving it to
be noticed by hand-comparing day counts. It reports any session a market ingested that its
benchmark lacks, over a 30-session window, per market. It exists as a *separate* check
because both existing guards are blind to it by design: the catch-up sensor's coverage
floor is a share of the universe (28 of 29 JSE names clears 0.8 comfortably and never
retries), and `recent_prices_quality` judges every ticker against one 0.95 completeness
ratio, which scores a single absent day 0.967. Both are right to shrug at one missing
ticker — the benchmark is simply not one ticker among fifty. Non-blocking: a stale
benchmark thins the alpha numbers, it does not corrupt them, and it must never stop an
ingest.

The catch-up sensor then *acts* on it. `catchup.benchmark_missing_days` makes an absent
benchmark its own reason to re-ingest a session, alongside thin coverage; the two reasons
are deduplicated so a day that is both spends one attempt, not two. It is bounded twice
over, because unlike coverage this trigger cannot fix itself — a re-ingest only helps if
the vendor has since published. The per-session daily budget caps attempts at three, and
`BENCHMARK_RETRY_SESSIONS` keeps only the newest five ingested sessions eligible, so a bar
that never arrives stops being chased after about a week instead of being re-fetched for
the full 30-day lookback. The asset check goes on reporting it over the longer window:
reporting forever is cheap, retrying forever is not.

**Usually the cause is a bar that has not arrived yet, not one that is missing.** JSE bars
in particular can land a day or more late: STX40.JO had no 2026-08-11 bar when the session
was first ingested *or* when it was retried the next morning against both yfinance and
Stooq — the gap looked permanent, and was written up here as one. Two days later the bar was
simply there (close 10857), and a plain re-fetch closed the gap. Two lessons, both paid for:

- **A benchmark gap is not evidence of a hole at the vendor.** Before concluding anything,
  re-fetch on a later day. An absent bar and a not-yet-published bar are indistinguishable
  at the moment you look, and the second one is far more common.
- **A wider window does not recover a missing bar — it invents one.** This bullet previously
  claimed the opposite, on the strength of `2026-08-12 -> 2026-08-13` returning nothing while
  `2026-08-05 -> 2026-08-13` returned a row. That row was the phantom described below, not the
  missing bar, and acting on it is precisely how the corruption gets written.
  Measured properly on 2026-08-14, once STX40.JO's 08-12 bar had actually been published:

  | query | rows returned |
  |---|---|
  | narrow `08-11 -> 08-12` | 08-11 @ 10857 |
  | narrow `08-12 -> 08-13` | 08-12 @ 10770 |
  | narrow `08-13 -> 08-14` | *(empty)* |
  | wide `08-05 -> 08-13` (ends before today) | 08-05, 08-06, 08-07, 08-11, 08-12 |
  | wide `08-05 -> 08-14` (ends **today**) | …the same, **plus 08-13 with a NaN close** |

  Narrow and wide agree on every genuinely published date. The only row the wide window adds
  is the phantom, and it appears only when the window reaches into a live session. So a
  one-day fetch returning nothing means the vendor has nothing: re-fetch on a later day,
  never on a broader range.

**The last row of a yfinance window can carry the wrong date.** When a ticker is genuinely
missing a session, the in-progress bar can slide into the empty slot and be stamped with the
missing date. Reproduced on STX40.JO, which has no 08-12 bar:

| query | last row | open | close |
|---|---|---|---|
| `2026-08-10 -> 2026-08-13` | **2026-08-12** | 10755 | NaN |
| `2026-08-10 -> 2026-08-14` | **2026-08-13** | 10755 | 10630 |

Same bar, two different dates — the later window reveals it as 08-13's live session. Had the
close been populated at fetch time, backfilling 08-12 would have written **today's price
under yesterday's date**: silent corruption, in the benchmark, in the column the CAPM marts
divide by. What prevented it is the `dropna(subset=["close"])` in `data/ingest.py` — the
in-progress bar had no close yet. That drop is load-bearing, not hygiene; don't "tidy" it
into a fillna. Tickers *without* a gap are unaffected (ABG/NPN/SOL returned identical 08-12
closes in both windows), which is what makes this easy to miss: it only bites the instrument
already having a bad day.

Practical rule: **do not backfill a window whose end falls on a session still trading.** Wait
for that session to close. Do not reach for a wider range instead — widening is what produces
the phantom, and it recovers nothing that a one-day window would not already have returned.

Whatever the cause, the gap is left as a gap. Carrying the previous close forward or
interpolating would fabricate the observation the CAPM decomposition divides by, and a
made-up denominator quietly undermines the one number that exists to be an honest read. One
absent day against 2,000+ is a rounding error in the regression; a fabricated one is a lie
of unknown size. A gap that persists for more than a few sessions *after* a re-fetch is the
one worth investigating as a vendor-reliability problem — not patching at this layer.
