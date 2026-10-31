# Corporate actions the stored prices do not credit (2026-10-23)

**In short:** The prices the model learns from leave out dividends in two ways. On the JSE and in
London the price vendor counts each dividend at a hundredth of its size, so a stock seems to fall by
its dividend on the day its shares start trading without it. And in every market, a dividend paid
after the market was first loaded is not counted at all, because stored prices are never rewritten.
A share split would be stored the same way, as a fall of half or more, and nothing checks for one.
Four other events are recorded wrongly too. Nothing has been changed: until the shadow verdict,
nothing may change what a past retrain trained on. This page proposes checks for new data and a fix
for January.

**Status: measured 2026-10-23 on the bars stored by 09:20 UTC that day; read-only.** The checks
and the fix below are proposals, not implemented.

## Why

The [Kronos replication](kronos-fresh-stocks.md#what-the-data-held-found-while-checking-it)
found that Yahoo's daily series, fetched through production's own `fetch_daily_bars`, does not
credit some corporate actions: Holcim falls 48% at the Amrize spin-off, Sulzer 35% at medmix,
and Stellantis jumps at its merger. Production's only repair, `repair_price_units`
([cleaning.py](../../src/quantpulse/data/cleaning.py)), catches the x100 unit glitch and nothing
else, and the `no_extreme_moves` quality check flags only moves beyond 50%
([quality.py](../../src/quantpulse/data/quality.py)). This page asks whether the three live
markets' stored prices carry the same kind of artefact.

## What was measured

All 263,674 stored bars of the 120 active XNYS, XJSE and XLON tickers, 2018-01-02 to
2026-10-22, pinned to `ingested_at <= 2026-10-23 09:20:35 UTC`:

1. **One-day moves beyond −25% or +35%**, close to close by stored row, as production's
   `pct_change` computes them. Also reversals (15% or more, two thirds back within five
   sessions), one-bar spikes (7% or more in and out, net of the market), and a watch list
   beyond −12% / +20% narrowed to moves made at the open against a flat market.
2. **Corporate actions known in these names** (GE's two spin-offs, AT&T's WarnerMedia, GSK's
   Haleon, the Anglo, Old Mutual and Naspers unbundlings, and others), checked on their dates.
3. **Yahoo's own record** beside every flagged row: its unadjusted close, its adjusted close, and
   the dividends and splits it lists. Then the same comparison on every dividend Yahoo lists for
   these tickers since 2018 (2,827): the share of each dividend the stored series credits on its
   ex-date.
4. **Where each artefact lands in training**, using production's own `compute_features`,
   `make_forward_returns` and `split_by_date` on the pinned bars. A level shift on a ticker's row
   *i* touches the labels of rows *i*−21 to *i*−1 and the features of rows *i* to *i*+62, the
   furthest any trailing window reaches. Each touched row is then placed in its champion's
   training window or holdout. XNYS v10 and XLON v1 store their windows; XJSE v3 predates the tags,
   so its windows were rebuilt from the bars stored by its fit time (2026-07-25 13:00 UTC), split
   as `train_final_model` splits.

Each artefact rests on an announcement or on Yahoo's own record. Each real move rests on a dated
news report, or, for well-known results days and the March 2020 sell-off, on its date alone. The
evidence file says which, and where only the price's shape supports a verdict.

## What came back

### Above the thresholds: one artefact in fourteen moves

| Market | Ticker | Date | Stored move | Verdict |
|---|---|---|---|---|
| XLON | IAG.L | 2020-09-14 | −30.8% | **Uncredited rights issue.** 3 new shares for every 2 at €0.92, 35.9% below the theoretical ex-rights price ([IAG, 2020-09-10](https://www.iairgroup.com/media/ocqb4eys/fully-underwritten-capital-increase-10-09-2020.pdf)), so the ex-rights to cum-rights ratio is about 0.65, the size of the stored fall. Market flat, no event in Yahoo's record. |
| XJSE | CPI.JO | 2020-03-18, 03-20 | −27.9%, +42.2% | Real: the March 2020 sell-off and rebound, both reported to the day |
| XJSE | SOL.JO | 2020-03-09 to 04-07 (5 days) | −46.6% to +53.5% | Real: the oil price war and recovery. The +53.5% on 04-07 is supported by its shape only (made during the session, on twice the usual volume) |
| XLON | IAG.L | 2020-03-16 | −27.0% | Real: travel bans |
| XLON | RR.L | 2020-11-09 | +43.8% | Real: the first vaccine result. The October 2020 rights issue is credited |
| XNYS | META, NFLX, INTC, ORCL | 2022–2025 | −35.1% to +36.0% | Real: results days |

### Below the thresholds: three more one-off artefacts

| Market | Ticker | Date | Stored move | What happened |
|---|---|---|---|---|
| XLON | TSCO.L | 2021-02-15 | −19.7% | The 50.93p special dividend, 21% of the price, is credited at a hundredth. The 15-for-19 share consolidation is credited. Corrected, the day is +1.7% |
| XJSE | BHG.JO | 2022-05-24 | −10.7%, then +15.3% | BHP's Woodside in-specie dividend went ex on the JSE on 05-24, a session before the ASX and London ([BHP](https://www.bhp.com/news/media-centre/releases/2022/05/determination-of-in-specie-dividend-in-connection-with-the-woodside-merger)). The adjustment was applied a session late, which leaves one bad bar |
| XLON | NG.L | 2024-05-20 | −8.5% | Yahoo applied National Grid's rights adjustment to only the four sessions before ex-rights (its unadjusted closes are fractional on 05-20 to 05-23 and round on either side). The step lands on a day with no news, three days before the rights issue was announced |

The known actions checked by date otherwise show no step: GE's spin-offs and AT&T's WarnerMedia
(Yahoo records each as a split factor), Haleon, Magnum and Aviva (each paired with a share
consolidation that offsets it), M&G, Thungela, Valterra, Nedbank's unbundling from Old Mutual, and
Prosus. One is left unconfirmed: Prudential's Jackson demerger (2021-09-20) opens 3.1% down,
about Jackson's value, with no event in Yahoo's record.

### Dividends on the JSE and in London, before their backfills

**Every dividend on XJSE and XLON up to the market's first load is credited at a hundredth of its
size.** Across 475 JSE and 828 London ex-dates since 2018 (of which 19 and 1 fall after the first
load and credit nothing; see the next section), the median share credited is 0.010, with the 10th
and 90th percentiles both at 0.010. NYSE dividends before its backfill are credited in full (1.004).
It is the quote unit: Yahoo lists a ZAc or GBp dividend in cents or pence and adjusts as if it were
rand or pounds. One large name per M13 market (SAP, LVMH, Nestlé, ASML) credits in full, like
Coca-Cola, while Unilever and Standard Bank credit 0.010. So the JSE and London series are price
returns where the NYSE's are total returns, and every ex-date reads as a fall the size of its
dividend:

| | XJSE | XLON |
|---|---|---|
| Ex-dates, 2018 on | 475 | 828 |
| Median dividend on its ex-date | 2.0% of the price | 1.4% |
| Largest | 12.8% (Exxaro, 2019-10-09) | 25.5% (Aviva's capital return, offset by its consolidation); 21.2% (Tesco) |
| Ex-dates above 5% | 48 | 19 |

The ones that crossed the watch list are Exxaro (−12.7%), Kumba (−12.6%; its R72.70 dividend was
9.5%), African Rainbow Minerals (−12.1%) and MTN (−10.0%). They are all ex-dates of this class.

yfinance's `repair=True` corrects the class: Kumba's ex-date moves from −12.6% to −3.5%, National
Grid's 2024 final dividend from −4.1% to +0.2%, and Tesco's from −19.7% to +1.7%. It does not
correct IAG's rights issue or BHP's late adjustment.

### Everything after the backfill, in every market

**No dividend after a market's first load is credited, on any market.** A bar is stored as the
vendor adjusted it on the day it was fetched, and is never rewritten
([ADR 0006](../adr/0006-price-data-is-filled-not-rewritten.md)). So when a stock goes
ex-dividend, the bars before it stay on the old basis, and the ex-date reads as a fall. ADR 0006
names the opposite risk, a re-fetched bar on a different basis from its neighbours. Never
re-fetching avoids that risk and creates this one.

| | XNYS | XJSE | XLON |
|---|---|---|---|
| First load | 2026-07-18 | 2026-07-23 | 2026-10-18 |
| Ex-dates since | 44 | 19 | 1 |
| Share credited | 0 | 0 | 0 |
| Largest | 1.6% (UPS) | 6.3% | 0.8% |
| Splits since | none | none | none |

The amounts are small so far, but they grow by one quarter's dividends every quarter. A split
would not be small. A 2-for-1 split would be stored as a −50% day for that stock, in its labels,
its features and the paper book's P&L. The `no_extreme_moves` check would not flag it, because it
tests for moves *beyond* 50%. A 3-for-2 split (−33%) would pass it too. No split has happened in
the universe since the backfills; nothing would catch the first one.

**Since then: the first step of that kind, on TKA.DE (Frankfurt) on 2026-10-28, found 2026-10-30
and left as stored until the fix (decided 2026-10-31).** thyssenkrupp spun off tk accelis, first
listed that day at one share per 20 thyssenkrupp shares (reported before the event, e.g.
[onvista](https://www.onvista.de/news/2026/10-21-thyssenkrupp-bringt-tk-accelis-naechste-woche-an-die-boerse-0-20-26566860)).
Yahoo now divides every earlier TKA.DE price by 1.104629 and multiplies every earlier volume by the
same factor, as it does for a split, but its action list shows nothing that day, as with National
Grid's rights adjustment above. The store keeps the old basis, so 10-28 reads −16.9% where the
adjusted move is −8.2%. Nothing flagged it, and `actions_since_load` as proposed below would not
either, since it reads Yahoo's action list. Comparing a fresh fetch's basis with the store's did.

- **Trained on before it was found.** The 2026-10-31 retrain promoted XETR v2, so 10-28 to 10-30
  are fixed under ADR 0006 point 3. Its booster is fitted up to 2025-05-26 and saw nothing of the
  step. Its holdout holds three TKA labels that span it, of about 13,000. XETR is not a market the
  [shadow](shadow-run.md) rule was registered for.
- **What it moves.** Scoring XETR's features with and without the step through v2: TKA's own ranks
  move a lot (63-day momentum 0.39 against 0.73 on 10-30), but v2 ranks it 3rd, 2nd and 4th of 41
  as stored against 5th, 8th and 8th corrected, on the long side every day either way.
- **Why it is left.** Scaling the bars from 10-28 would rewrite sessions v2 trained on, fail
  champion-forward's holdout reproduction for it, and need a factor on every ingest path until the
  fix. Setting the ticker aside is worse (the second check below says why). Left, TKA's 5-, 21-
  and 63-session features stay off until 11-04, 11-26 and 2027-01-29, and 18 more labels (the
  21 that span it, less v2's three) carry about −9.5 points as they enter weekly holdouts. A
  replay of XETR's history would book the −16.9% for a TKA long held over 10-27.
- **For the fix:** TKA.DE, 2026-10-28, spin-off, factor 1.104629, goes in its reviewed table.

Evidence: `~/quantpulse-experiments/m13-europe/phase3-end-check/` and
`~/quantpulse-experiments/m13-europe/tka-2026-10-28/`.

## Where they fall in the training panels

Rows of the panel production builds today (pinned as above), placed in the champion's windows:

| Artefact | Labels touched | Features touched | In the champion's |
|---|---|---|---|
| IAG.L 2020-09-14 | 21 | 63 | training window (XLON v1, 2018-04-03 to 2025-05-13) |
| TSCO.L 2021-02-15 | 21 | 63 | training window (XLON v1) |
| NG.L 2024-05-20 | 21 | 63 | training window (XLON v1) |
| BHG.JO 2022-05-24 | 1 (the other falls in BHG.JO's warm-up; its history starts 2022-01-31) | 64 | training window (XJSE v3, 2018-04-04 to 2025-02-26, rebuilt) |

**None of the four falls in a holdout.** Every retrain since the backfills has trained on all four,
the shadow arms included. Their size: the stored series steps 31%, 20% and 9% where the market
was flat or up, against a median spread of London's 21-session labels across stocks of 6.5% on a
date.

The JSE and London dividend class runs through every window of both markets:

| | XJSE | XLON |
|---|---|---|
| Panel rows (to 2026-09-22/23) | 59,317 | 87,794 |
| Label rows whose 21 sessions hold an ex-date | 9,062 (15.3%) | 16,786 (19.1%) |
| — in the champion's training window | 7,172 of 47,952 | 13,867 of 73,625 |
| — in the champion's holdout | 1,296 of 8,961 | 2,742 of 13,152 |
| Median understatement of those labels | 2.1 points | 1.4 points |
| Labels understated by more than 5 points | 891 | 455 |
| Feature rows with an ex-date in reach | 26,158 (44%) | 49,481 (56%) |
| Per-date rank correlation, stored label vs total-return label | mean 0.982, lowest 0.790; below 0.95 on 212 of 2,118 dates | mean 0.985, lowest 0.883; below 0.95 on 84 of 2,142 |

The last row is the ranking the gate's IC is scored against. It mostly survives, but not where
large dividends cluster.

Ex-dates since the backfill fall in the most recent holdouts: 181 label rows in XNYS v10's
holdout, and 795 and 259 in the latest candidates' (XNYS v17 and XJSE v16, both 2026-10-17). None
yet in a training window. London's single one touches no holdout.

## What this does not show

- **Whether any of it changed a model's skill, a promotion or the live record.** Not measured. A
  rank correlation of 0.98 says the label's order mostly survives, but the gap is not noise: it
  falls on high-yield names on dates set months in advance, and the features carry the drop, so a
  model can learn it. Read it as unmeasured, not as small.
- **The paper books.** The JSE and London books are built from these prices, so their longs miss
  dividends and their shorts are never charged them, and since July the NYSE book has been the
  same. The net effect on any record is unmeasured. It belongs on the replay's list of known
  biases until it is.
- **That the scan is complete.** Below 12% it rests on known events, on the gap and spike filters,
  and on Yahoo's own event list. Rights issues and spin-offs that Yahoo does not list show only
  as price shapes. On XJSE and XLON, 159 overnight gaps of 6–12% against a flat market fall on no
  dividend date and were not checked; most are likely results days. A screen for adjustments
  applied to part of a series, looking for fractional unadjusted closes, was tried and dropped:
  split-adjusted closes are fractional too, so it returned 21,196 runs.
- **The shadow run.** Both arms train and are scored on the same rows, so every artefact here is
  common to both. Nothing here was measured on the shadow run.
- **The NYSE is clean on this scan up to its backfill, not proven clean.** Its four moves beyond
  the thresholds are results days, and its splits, spin-offs and dividends up to 2026-07-18 are
  credited. After that, its ex-dates are uncredited like every market's.

## Proposed: checks where bars arrive

Three checks in [quality.py](../../src/quantpulse/data/quality.py), run by the CLI and the
existing asset check and by M13's backfill. They report on the live markets and change no stored
bar. A backfill refuses a market that fails the first, before its first bar is stored, as
`wrong_currency` does for a listing in the wrong currency.

1. **`dividends_credited`.** On a fresh fetch, not the store, fetch Yahoo's dividends and
   unadjusted closes beside its adjusted bars. On each ex-date, compute the share of the dividend
   the adjusted series credits. Fail a market whose median falls outside 0.9 to 1.1. This tests
   the vendor; the next check covers the store. Today it fails XJSE and XLON (0.010) and passes
   XNYS. On the four M13 markets it should pass, which is worth confirming per market before the
   backfill rather than assuming from one name each.
2. **`actions_since_load`.** Every dividend and split Yahoo lists for a ticker after its market's
   first load is, by construction, uncredited in the store. The check lists each one, and fails
   loudly on any split, since a split breaks the stock's next 63 sessions of features and the
   book's P&L on the day. It is for an operator to act on, not automatic: while the shadow window
   is open, rewriting the bars before a split is not an option (ADR 0006, point 3). Scaling the
   new bars to the stored basis changes nothing a past retrain trained on only until a retrain
   runs after the split: labels reach 21 sessions back, so that retrain's labels already read the
   new bars. Setting the ticker aside changes every past panel of its market at once:
   `load_price_bars` reads active listings only and ranks are taken within the market, so a
   rebuilt panel loses the ticker and re-ranks every other name (corrected 2026-10-31, on TKA.DE).
   Scaling has its own cost: the options book reads `prices.close` beside strikes that trade on
   the new basis. That choice is the owner's.
3. **`unexplained_jumps`.** One-day moves beyond −25% / +35%, and one-bar spikes of 7% or more in
   and out net of the market, on a date where Yahoo lists no event. These are listed for a
   person to classify, never repaired automatically: the scan above found real moves outnumbering
   artefacts thirteen to one above the thresholds, and silently "fixing" ambiguous data is what
   `cleaning.py` refuses to do. The verdicts go in a reviewed table of adjustments that the fix
   below applies. Holcim, Sulzer and Stellantis would have been listed. IAG's rights issue and
   BHP's late adjustment would too. National Grid's 8.5% step would not, and neither would the
   159 gaps left unchecked above: no threshold separates those from results days.

Before any of the three guards anything, break it and watch it fail
([measurement.md](../measurement.md#verify-a-test-by-breaking-the-code-it-guards)). Feed it
Kumba's 2021 bars with the dividend credited and with a hundredth credited, IAG's 2020 bars as
stored, and a synthetic 2-for-1 split. Then check that the sabotage actually applied.

## Proposed: the fix, after the verdict

Every part of this changes past training data, so none of it starts before the shadow verdict
(around the end of December 2026; [roadmap](../roadmap.md#next), item 1). It belongs in the same
break as item 6 there, building features and labels on the session calendar, so past panels
change once and are measured once.

1. **Compute the adjustment instead of storing the vendor's.** Store unadjusted bars and a table
   of corporate actions: Yahoo's dividends and splits, plus the reviewed rights issues,
   spin-offs and corrections from the third check. Build the adjusted series in code, with
   dividends taken in the quote's own unit. That fixes both dividend classes at their cause,
   handles splits whenever they come, and ends one of the risks ADR 0006 was written against: a
   series computed from fixed unadjusted bars does not drift when the vendor revises its
   adjustment. It needs its own ADR, since it changes what `prices` holds, which ADR 0006
   governs. `repair=True` is not a substitute. It corrects the hundredth only, does nothing for
   the store's own class, and it repairs other things as well (it would overlap
   `repair_price_units`).
2. **Measure before adopting.** Refit on the corrected panel against the stored one, paired by
   seed across rolling origins, under a rule merged to `main` before the run
   ([measurement.md](../measurement.md#fix-the-decision-rule-before-the-run-where-the-merge-cannot-erase-it)).
   The labels change, so the promotion margins need re-measuring, and no stored metric compares
   across the change.
3. **Decide how the live record crosses it.** Books that earn dividends on longs and pay them on
   shorts are a different book from today's. As with the tied-forecasts decision, the owner
   chooses whether the records split at the fix or are restated.
4. **Correct the docs that say otherwise.** The glossary's `close` ("adjusted for dividends and
   splits") is true only of the NYSE, and only up to its backfill. ADR 0006's context needs the
   same correction. Those are docs-only edits that change no training data, so they need not wait
   for the fix.

## Evidence

`~/quantpulse-experiments/corporate-actions-scan-asof-2026-10-23/`, pinned to
`ingested_at <= 2026-10-23 09:20:35 UTC`. Its `README.md` lists every file:

- the exports: `prices.csv`, `universe.csv`, `model_runs.csv`, `as_of.txt`, `commit.txt`;
- the scans: `scan.py`, `gap_shaped.py`, `spikes.py`, `residual_band.py` and their outputs;
- Yahoo's record: `yahoo_actions.py`, `dividend_credit.py`, `europe_dividend_credit.py`, and
  their outputs as fetched on 2026-10-23, since Yahoo revises its history;
- the training-window counts: `windows.py`, `windows.csv`, `champion_windows.csv`,
  `dividend_summary.csv`, `dividend_labels.csv`, and `after_backfill.py` for the store's class;
- every verdict with its source: `classification.csv`.
