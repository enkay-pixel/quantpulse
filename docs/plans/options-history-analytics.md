# Options history analytics

The snapshot-forward design has been accruing since 2026-07-20 because no free source sells
option history retroactively. This is what that buys, and — as importantly — what it does not
buy yet.

## What exists (2026-08-30)

| | |
|---|---|
| Snapshot days | 27 of 30 sessions; 08-11 to 08-13 are a permanent hole from the connectivity outage |
| Tickers | 50, all with ≥20 days |
| Ticker-days | 1,268, `atm_iv` 0% null |
| Expiries per ticker-day | median 10 |
| Price history | 2018-01-02 onward, 2,176 sessions |

One ticker-day carries `atm_iv` 0.016. That is a single illiquid contract, not the pre-market
capture signature — which would depress all 50 tickers on a day, and does not. The
`option_snapshot_quality` check reads median IV among traded contracts and correctly ignores it.

## Correction: most of this already exists

The first version of this plan proposed building three things. Checking the marts rather than
the roadmap found two of them already written:

- **`fct_iv_surface`** gives mean IV by (ticker, snapshot, expiry, moneyness bucket). Its own
  header says it: across strikes is the smile, across expiries is the term structure. Both
  pieces I proposed to build are already there.
- **`fct_daily_returns.volatility_21d`** is trailing realized volatility, already computed for
  every ticker-day.

What is actually missing is smaller and more specific.

## Build now

1. **`fct_iv_vs_realized`** — the only genuinely new analysis. Joins `fct_option_summary.atm_iv`
   to `fct_daily_returns.volatility_21d` and reports the spread: the variance risk premium, per
   ticker-day. **1,268 observations**, because each ticker-day is one comparison rather than one
   of 27 snapshots. This has a real answer today.
2. **Surface `fct_iv_surface`.** It is built, tested, and consumed by nothing — no API route,
   no dashboard component. The term structure and skew are already computed and invisible,
   which is a cheaper win than anything that needed building.

## Deferred, with what each needs

Not "later" — these have counts attached so they resurface on their own.

| Deferred | Why | Needs |
|---|---|---|
| IV rank / percentile | Over 27 observations a "percentile" is a min-max scaler wearing a better name | ~250 snapshot days (≈1 year) |
| IV-change → next-day return | 27 observations. Three findings reversed at this sample size in the week of 2026-08-23 | ~250 days, and the paired method in [measurement.md](../measurement.md) |
| Forward implied vs realized | The realization window must close; only the earliest snapshots qualify today | Accrues on its own; usable from ~2026-10 |

## Design

- `fct_iv_term_structure` — ticker × snapshot × maturity bucket, from `stg_option_quotes`
- `fct_iv_vs_realized` — ticker × snapshot, `atm_iv` beside trailing realized vol and their spread
- Endpoints alongside the existing `/options/*` routes
- An Options-tab section, sample size on the face of it

## The rule this follows

Everything here is measured against [How to measure things here](../measurement.md). The
temptation with a new dataset is to look for a signal in it immediately; at 27 observations
that produces findings which reverse, which is exactly what the last week of this project
was spent undoing.
