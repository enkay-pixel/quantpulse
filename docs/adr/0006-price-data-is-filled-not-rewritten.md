# ADR 0006: Price data is filled, not rewritten, and is fixed once a model has trained on it

**Status**: accepted · **Date**: 2026-10-13

**In short:** A stored price is never overwritten: gaps are filled, and once a model has trained on
a day, that day is fixed, so past models can be re-run exactly.

## Context

`prices` is the base every feature, label, model and book is built from, and it is written by
more than one path: the scheduled ingest, the catch-up sensor's retries, and by-hand
re-materializations. Until now each of them upserted whole sessions, which made three things
possible without anything noticing:

- **A model's training data could change after it was fitted.** The shadow run
  ([findings](../findings/shadow-run.md)) refits every week's candidates and requires each refit
  to reproduce exactly; a week whose data was revised afterwards cannot be recovered. The
  champion-forward replay depends on the same property.
- **A stored bar could be rewritten with a differently adjusted price.** The vendor serves
  dividend-adjusted closes as of the fetch date, so re-fetching a stored session after a
  corporate action replaces one bar with a price on a different basis from its neighbours.
- **A second vendor could fill a gap with a bar on different units.** The Stooq fallback was
  meant for this and could never do it ([incident 37](../development-history.md)), but the risk
  was the design, not the outage.

Meanwhile the gaps that actually occur are late bars rather than missing ones: on 2026-10-12 the
vendor had the absent NYSE bars by the next afternoon.

## Decision

1. **One source.** yfinance is the only price vendor. A ticker it does not return is left absent,
   named in the log, and reported by the post-close check.
2. **Gaps are filled, never rewritten.** A re-ingest of a session that is already partly stored
   fetches only the missing tickers and inserts without overwriting (`FILL_ONLY_TAG`,
   `upsert_prices(overwrite=False)`). The catch-up sensor does this on its own for the newest five
   ingested sessions.
3. **A session a model has trained on is fixed.** The sensor stops filling a session once a
   training run has used it (`catchup.latest_training_day`). Revising one by hand is an
   operator's decision, and while a pre-registered shadow window is open it is not taken.
4. **No fetch ends on a session still trading.** A one-day request runs to the next calendar day,
   so yesterday is not fetched while today trades (`catchup.fetch_would_end_in_open_session`).

Whole missing days are the exception to 3: the catch-up sensor still re-ingests a session below
the coverage floor whenever it can, because a missing day costs more than a lost refit.

## Consequences

- A bar that arrives after the next retrain stays missing in the record unless filled by hand
  later. For a Friday session that leaves under a day; the cost is a few absent ticker-days,
  reported, against a training set that cannot drift.
- Past models stay reproducible from the stored data, which is what makes forward scoring of a
  retired candidate, or of the shadow arm, evidence rather than an approximation.
- Correcting a genuinely bad stored bar remains possible, through a by-hand re-materialization,
  which still overwrites. It is deliberate rather than a side effect of a retry.
- Features and labels still shift by row, so a missing ticker-day stretches that ticker's returns
  across the gap. Building them on the session calendar instead changes past training data and is
  deferred until the shadow window closes.
