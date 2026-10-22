# ADR 0005: Exchange as a first-class dimension (multi-market)

**Status**: accepted, amended 2026-10-18 · **Date**: 2026-07-23

**In short:** Everything is kept separate per stock market (New York, Johannesburg, London), so
figures from one market are never mixed into another's.

## Context

The platform was NYSE-only. Adding a second market (the JSE) is not a config change: the
single line that ranks tickers cross-sectionally (`features/engineering.py`) would, with a
mixed universe, rank Naspers against Apple — different currency, session and macro — and
the features would silently degrade into noise. Exchange has to be a real dimension carried
through features, models, books, marts and the API. Design record: [../plans/m11-multi-market.md](../plans/m11-multi-market.md).

## Decision

- **`exchange` is a first-class dimension**, sourced from `universe.exchange`. `prices` /
  `features` / `predictions` do **not** carry it — tickers are globally unique (JSE uses a
  `.JO` suffix), so they join `universe` when a market is needed, avoiding denormalisation
  drift. `portfolio_snapshots` and `model_runs` carry it (per-market aggregates with no
  ticker). All dbt marts carry it and partition every window function by it.
- **A registry of markets** (`data/calendar.Exchange`) holds each market's calendar,
  timezone, close hour, currency, benchmark, `has_options`, and quantile width. All date
  logic is exchange-aware; nothing uses the container's UTC clock.
- **`raw_prices` is partitioned by `(date, exchange)`** (`MultiPartitionsDefinition`), with
  a per-market post-close schedule in each market's own timezone. A JSE holiday is not an
  NYSE holiday, and one cron cannot serve two closes. **Accepted cost:** existing
  single-dimension partition keys are orphaned — cosmetic, since `prices` is untouched and
  the catch-up sensor reads coverage from `prices`, not Dagster partition state.
- **One champion per market** (`quantpulse-lgbm-<exchange>`), not one pooled model. The data
  is not the constraint; attribution is, and pooling would muddle it.
- **Quantile width is per-market, set from breadth** so each book holds a comparable *number*
  of positions (~10/side), not a comparable percentile: 20% of 50 US names, 35% of 29 JSE.
- **Two-phase delivery**: the NYSE-only refactor was proven behaviour-preserving
  (`max |Δ daily_return| = 0` over 2085 days) before the JSE was added, so "nothing
  regressed" stayed a checkable claim — the same discipline that makes the book comparison
  meaningful.

## Consequences

The dashboard gains a market switcher (in the URL), and every endpoint takes `?exchange=`.
The options layer stays NYSE-only (`has_options=false`; no free JSE chain data). Onboarding
the JSE surfaced gaps this dimension made visible and worth fixing platform-wide: a vendor
units bug (`data/cleaning.py`), a missing first-champion Sharpe floor, and small-sample
ratios that are now nulled at source. Adding a third market is now a config change plus a
backfill — the architecture is the reusable part.

## Amendment (2026-10-18): adding a market, the checklist from London

London was added as the third market to test the claim above. The architecture held: no code
assumed two markets beyond three tests and one dashboard sentence. Everything London found was
in the data, the display, or a reading fixed before it arrived, and each is now checked rather
than remembered. Design record: [../plans/m12-london-pilot.md](../plans/m12-london-pilot.md).
The next markets follow it in waves, starting with [M13](../plans/m13-europe-wave.md), which adds
a headroom phase before onboarding: four markets at once is where the laptop stops fitting.

Before ingesting:

1. **Calendar.** The market is in `exchange_calendars`.
2. **History.** Every listing has vendor history from the panel start; a shorter one is left out,
   since a model needs the same history as its peers.
3. **Currency, per listing.** Each listing is quoted in the market's currency. Yahoo quotes two
   London lines in dollars; `quantpulse backfill` now refuses a market holding one.
4. **Benchmark.** The market's index fund is in its universe, with history (it may publish a day
   late; the freshness check reports that).
5. **Breadth.** `quantile_width` gives about ten names a side, and every stock has a canonical
   Wikipedia title. `test_every_registered_market_is_fully_onboarded` checks both.
6. **Registry.** Timezone, close hour, currency, display unit, `has_options`, the dbt `benchmarks`
   entry, and an `ic_promotion_margin`, which has no default.

Onboarding:

1. **Fingerprint the other markets first** (`prices`, `features`, `predictions`, and the paper
   books), then sync the universe, backfill, recompute features, and compare. They must be
   identical; London's were, row for row.
2. **Train the first champion** through the unchanged gate: the Sharpe floor and the momentum
   competitor. If none clears it, the market shows its data and research without a model.
3. **Replay-score the history** (`quantpulse score --replay --exchange X`), build the marts, and
   read the dashboard in the browser, prices included: the price chart and positions had drawn
   JSE prices as dollars since July, and London's onboarding is what found it.
4. **Measure the margin and the learning-rate ceiling before the first challenger.** The margin
   is 2 sd of the champion's specification refitted with only the seed changed
   ([promotion-margin.md](../findings/promotion-margin.md)); doing so for London found the JSE's
   had fallen to a third of its noise. The ceiling follows
   [learning-rate-ceiling.md](../findings/learning-rate-ceiling.md); London needed 0.02, as the
   JSE does.
5. **Keep pre-registered readings to their own markets.** A study or verdict fixed before the
   market arrived holds its markets and margins in code; a new market is not added to it.
6. **Update the runbook** with the ingest time in local time across both clock changes.
