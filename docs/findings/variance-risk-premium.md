# Is there a variance risk premium here? (2026-08-30)

The snapshot-forward option capture has run since 2026-07-20 because no free source sells
option history retroactively. The first question it can answer: did the option market charge
more for volatility than the underlying delivered?

## Method

`fct_iv_vs_realized` puts `atm_iv` beside trailing 21-day realised volatility for every
(ticker, snapshot) — 1,259 rows over 50 tickers and 27 snapshot days. Backward-looking on
purpose: comparing implied to *subsequent* realised volatility is the sharper question but
needs the realisation window to close, and only the earliest snapshots qualify yet.

## Result: none that this panel can measure

| level | n | mean premium | std err | t |
|---|---|---|---|---|
| ticker-day | 1,259 | +0.0026 | 0.0028 | 0.9 |
| day | 27 | +0.0044 | 0.0055 | 0.80 |

Average implied volatility is **32.5%** against realised **32.2%**. Options were priced almost
exactly at delivered movement, and the difference does not separate from zero at either level
of aggregation.

The two levels are reported together because 1,259 is not the effective sample size. Fifty
tickers on one day share market-wide volatility, and 21-day windows overlap between
consecutive snapshots. The check: if tickers were independent, the standard deviation of the
daily mean would be 0.0950/√50 = 0.0134. It is **0.0285**, over twice that. Day-level is the
honest aggregation, and it agrees.

## The unit error this nearly shipped as a finding

The first version subtracted `volatility_21d` from `atm_iv` directly. That column is a *daily*
standard deviation; `atm_iv` arrives annualised. The mismatch produced:

> premium **+0.3047**, t **80.1**, **100%** of ticker-days positive

which is exactly what a large, robust, obviously-real effect looks like. The tell was that
average realised volatility read 0.020 — 2% a year for single equities, which is not a number
that occurs. Multiplying by √252 gives 0.317, almost precisely the average IV, and the premium
collapses to nothing.

Recorded because the failure mode is not "wrong answer" but "spectacular answer". A comment in
that first version asserted both series were already annualised. It had not been checked.

## What this does not say

A positive variance risk premium is among the better-documented effects in options markets.
Twenty-seven days failing to find one is far more likely to be this window, or too little data,
than evidence the premium does not exist. The honest statement is that **this panel cannot
resolve it**, not that it is absent.

## Related

- [How to measure things here](../measurement.md) — the units and effective-sample-size rules
  this finding came from breaking
- [Options history analytics plan](../plans/options-history-analytics.md) — what else the
  snapshot history does and does not yet support
