# ADR 0005: Exchange as a first-class dimension (multi-market)

**Status**: accepted · **Date**: 2026-07-23

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
