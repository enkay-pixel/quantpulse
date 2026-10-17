# M12 — More markets, starting with a London pilot

**Status: APPROVED 2026-10-17, in progress.** One market first, to prove that a third market is
"a config change plus a backfill" (ADR 0005) and to turn what it takes into a checklist the next
markets follow.

**In short:** London joins as the third market, beside the NYSE and the JSE, with its own
universe, model, books and research pages. Nothing about the two existing markets changes, and
that is checked, not assumed.

## Decisions (settled at approval)

| Question | Decision |
|---|---|
| Which markets first | **London alone, as a pilot.** English Wikipedia for attention, prices in pence (the path JSE cents already use), a close during the SAST evening, and a FTSE 100 fund to benchmark against. Europe, then other time zones, follow its checklist. |
| Before or after the shadow verdict | **Now.** The verdict is read per market, so London gets its own model, shadow fits and later verdict without touching NYSE or JSE readings. |

## What was verified first (not assumed)

- **Calendars.** `exchange_calendars` has XLON, and every market considered next (XETR, XPAR,
  XAMS, XSWX, XTSE, XASX, XTKS, XHKG, XBOM, BVMF, XKRX, XSES). India's NSE is not there; BSE is.
- **Prices.** Yahoo serves London from 2018 in pence (`GBp`). Of 44 FTSE 100 candidates, 40
  stocks have history from early 2018 to this week. Dropped: Ashtead (no longer listed in
  London), M&G (listed 2019) and Haleon (2022), since a model needs the same history as its peers.
- **Benchmark.** `ISF.L`, the iShares FTSE 100 fund, has history from 2018. Its newest close was
  missing on 2026-10-17 for the day before: Yahoo publishes some London funds a day late, which
  the benchmark freshness check reports and the next fetch fills.
- **Market-specific code.** An audit found little: the dbt `benchmarks` variable (already tested
  against the Python registry), and dashboard statements that name the JSE where they mean "a
  market without US data". Options, short interest and SEC filings stay US-only by their flags.
- **The freeze.** The shadow verdict is per market (`~/quantpulse-experiments/shadow-run/<market>`).
  Features rank within a market, so London rows cannot move NYSE or JSE features.

## The market

```python
XLON = Exchange(
    code="XLON",
    timezone="Europe/London",
    close_hour=17,  # the session ends 16:30; the first whole hour after it
    currency="GBp",  # pence: a 1428 quote is £14.28
    benchmark="ISF.L",
    has_options=False,  # no free London chains
    display_divisor=100.0,
    display_symbol="£",
    quantile_width=0.25,  # 40 names -> 10 per side, matching the other two markets
)
```

`ic_promotion_margin` and `learning_rate_ceiling` start at the defaults and are **measured** before
the first challenger is judged against a champion, as each was for the JSE: the variance study for
the margin (the RNG-only refit spread), the learning-rate finding's method for the ceiling.

Ingest runs at 19:30 London time: 20:30 SAST now, 21:30 SAST after the UK clocks change on
25 October. Processing stays after the NYSE close, so London is in it every night.

## Phases

1. **Generic wording.** Dashboard statements that name the JSE where they mean "a market without
   options, short interest or SEC filings" say that instead. No behaviour changes.
2. **Configure London.** The registry entry, the `XLON` universe block (40 stocks and `ISF.L`),
   the dbt `benchmarks` entry, and the Wikipedia titles, checked canonical.
3. **Backfill and prove nothing moved.** Fingerprint NYSE and JSE `features` and `predictions`,
   backfill London from 2018, build its features, and compare: the two existing markets must be
   identical row for row, as the JSE onboarding proved with `max |Δ| = 0`.
4. **First champion.** Train London through the unchanged gate. A first champion must clear the
   Sharpe floor; if none does, London has data and research pages but no model yet, and the
   dashboard says so rather than showing an empty book.
5. **Measure and record.** Compute headroom (processing time and memory with three markets), the
   promotion margin, the learning-rate ceiling, the runbook's keep-on windows, and an ADR 0005
   amendment that turns this into the onboarding checklist.

## Risks

| Risk | Mitigation |
|---|---|
| A shared change moves NYSE or JSE data during the freeze | Phase 3's row-for-row comparison gates every merge that touches shared code |
| Yahoo reports a London price in pounds instead of pence | The unit repair that catches JSE rand/cent glitches is generic (a −99% day then +100×); a test proves it on a London series |
| The benchmark lags a day | The freshness check already reports it; the book compares on days both have |
| No first champion clears the floor | London shows its data and research without a model, said plainly |
| Three markets outgrow the laptop | Measured in Phase 5 against the resource report before a fourth is added |
| Dual listings (BAT, Anglo American) read as the same company twice | Each market is its own book and currency; the brief's attention notes cross-market interest |

## Out of scope

- Options, short interest and SEC filings for London (no free source).
- Currency conversion and cross-market books: each book is one market, one currency.
- Markets beyond London until this pilot's checklist exists.
