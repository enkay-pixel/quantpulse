# Did options price more volatility than then arrived? (pre-registered 2026-10-14)

**In short:** New York options priced in more movement than then happened — about 5 points of
volatility on average — but over one calm stretch, which may simply be markets calming down.

**Status: measured 2026-10-14. Options were priced above what then arrived — by the pre-registered
rule, against the pre-registration's own expectation.** The sections down to the results are the
pre-registration, pushed to `main` on its own before any code or run existed, under the rule in
[How to measure things here](../measurement.md#fix-the-decision-rule-before-the-run-where-the-merge-cannot-erase-it).
They are unchanged.

## Why

The [variance risk premium study](variance-risk-premium.md) compared implied volatility with the
*trailing* 21-day realized volatility, and found none it could resolve (+0.0044, t 0.80 at day
level, 27 days). It named the sharper question and deferred it: an option prices the volatility
still to come, so the fair comparison is with the volatility that then arrived. That needs each
snapshot's realization window to close, and enough of them now have.

## What it can and cannot show

**It will probably not resolve, and that is known now.** The window holds 37 snapshot days, and
each realization window spans 21 sessions, so consecutive days share most of theirs: the 37 days
hold fewer than two independent windows. Fifty tickers on one day also share market-wide
volatility, so the ticker-day count is not the sample size either. On the trailing study's spread,
only a premium of roughly 0.04 (four volatility points) or more could clear the bound below. The
single-stock premium reported in the literature is of the same order, so a resolution is possible
but not expected.

It is worth running anyway. It is the question the snapshot-forward capture was built to answer,
it is cheap, and the window grows by itself: the same query re-run later answers the same question
with more data.

## Window, fixed in advance

- **Snapshots:** NYSE, **2026-07-20 to 2026-09-14** — every snapshot whose next 21 sessions had
  closed by the pin, **2026-10-13**. That is 40 sessions, less the three lost to the 2026-08-11 to
  08-13 outage: 37 snapshot days.
- **Implied volatility:** `fct_option_summary.atm_iv`, as stored — the at-the-money contract at the
  expiry nearest 30 calendar days out (at least 7), annualized by the vendor.
- **Forward realized volatility:** the sample standard deviation of the ticker's next 21 daily
  simple returns (sessions *t*+1 to *t*+21), annualized by √252. This is exactly the definition of
  `fct_daily_returns.volatility_21d`, moved forward. A row whose window holds fewer than 21
  returns is dropped.

## Measure

Per (ticker, snapshot): **forward premium = implied − forward realized**, both annualized.

Per snapshot day: the mean across that day's tickers. **The headline is the mean of those daily
means**, with a Newey-West error at lag 20, because each day's window overlaps the next twenty.
The ticker-day mean is reported beside it and decides nothing, for the reason above.

**Units check, fixed in advance:** the mean forward realized volatility must lie between 0.05 and
1.5 — a single-stock annualized volatility. Outside that, the run stops as a units error and
nothing is read. The trailing study nearly published a premium of 0.30 at t 80 because one series
was daily and the other annual; this is the check that would have caught it.

## Reading rule, fixed in advance

1. **Options priced above what arrived** if the one-sided 95% *lower* bound on the headline is
   above zero.
2. **Options priced below what arrived** if the one-sided 95% *upper* bound is below zero.
3. **Otherwise not resolved**, reported with how many more snapshot days the current mean would
   need at the current error — never as "no premium".

Reported alongside, deciding nothing: the ticker-day mean, the trailing premium over the same
rows, and which forecast came closer to the volatility that arrived — implied, or trailing
realized — by mean absolute error.

None of these outcomes changes anything in the platform. This is a description of the option
market on this panel, not a strategy.

## Disclosures

- **The trailing comparison over the first 27 of these days has been seen:** IV 32.5% against
  trailing realized 32.2%, premium +0.0044 (t 0.80) at day level.
- **No forward realized volatility has been computed** for any snapshot before this page was
  written.
- **The window is one regime.** It runs from late July to mid-September 2026, and a premium
  measured over one stretch of one market is a description of that stretch.

## Results (measured 2026-10-14, pinned at 2026-10-13)

The units check passed: forward realized volatility averaged **0.267**, an annual figure.

| NYSE, snapshots 2026-07-20 to 2026-09-14 | value |
|---|---|
| Rows / tickers / snapshot days | 1,752 / 50 / 37 |
| Implied volatility (mean) | 0.317 |
| Realized over the next 21 sessions (mean) | 0.267 |
| **Forward premium, day level** | **+0.0489 ± 0.0047** (Newey-West, lag 20) |
| One-sided 95% bound | lower **+0.0412** |
| **Reading** | **options priced above what arrived** |

Alongside, deciding nothing: the ticker-day mean is +0.0499; the *trailing* premium on the same
rows is +0.0121, close to the earlier study's unresolved +0.0044; and implied volatility was the
better forecast of what arrived, missing by 0.074 on average against 0.082 for trailing realized.

### The pre-registration expected otherwise, and said why

It predicted no resolution, reasoning that the window holds fewer than two independent windows
and that only a premium of about 0.04 or more could clear the bound. The second half held: the
premium came in at 0.049, the size it said could resolve. What it got wrong was expecting a smaller
premium.

The error is likely understated, and the result survives that. The daily means have a lag-1
autocorrelation of 0.74, so the 37 days are worth about five independent ones, and an error built
that way is about 0.0095 rather than 0.0047 — a lower bound of +0.033, still above zero. The reading
would fail only with an error above 0.030. It is also consistent throughout: 36 of 37 day means are
positive, the two non-overlapping 21-day blocks give +0.054 and +0.042, and 46 of 50 tickers have a
positive average premium.

### What it does not say

- **That this is a standing premium.** Implied volatility tracked the trailing level (0.317 against
  0.305) and the market then calmed to 0.267. Over one stretch, "options carry a premium" and
  "volatility fell after being priced from the recent past" produce the same numbers; separating
  them needs windows from other regimes, which the snapshot history will accrue.
- **Anything tradeable.** A premium measured gross of spreads, on 50 names, over seven weeks, is a
  description of that stretch of this panel.

Evidence: `~/quantpulse-experiments/forward-vrp-asof-2026-10-13/` — every row, the daily means,
the summary, the log, `run.py` and the commit that ran it. To regenerate:
`quantpulse forward-vrp --first 2026-07-20 --as-of 2026-10-13`, after
`dbt run --select fct_iv_vs_forward_realized`.

## Related

- [Is there a variance risk premium?](variance-risk-premium.md) — the trailing version, and the
  units error this page's check is for
- [Options history analytics plan](../plans/options-history-analytics.md) — where this was deferred
