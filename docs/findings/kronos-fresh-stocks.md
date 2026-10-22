# Kronos again, on stocks it was never scored on here (pre-registered 2026-10-22)

**In short:** A second test of Kronos, the open price-chart model from the
[first study](kronos-zero-shot.md). It uses the same dates, settings and competitors, on 117
German, French and Swiss stocks that study never touched, and a control that can only fail when
the evaluation itself is broken. It only measures; nothing in production changes because of it.

**Status: pre-registered; not yet run.** This page reached `main` before any forecast on its test
dates existed, under the rule in [How to measure things
here](../measurement.md#fix-the-decision-rule-before-the-run-where-the-merge-cannot-erase-it).

## Why

The first study could not be read. Its single random draw per date excluded zero on London by
chance, and the owner left it unread rather than change the control after seeing the outcome
([first study, results](kronos-zero-shot.md#results)). That leaves the question open. Asking it
again on the same stocks would test a design chosen after their figures were seen. New stocks give
a clean slate with everything else held fixed.

## What it can and cannot show

**The same leak protection as the first study.** Every label is a return realised after
2024-07-01, after the end of Kronos's pre-training data in June 2024. The strict window repeats the
reading on test dates after 2025-09-09, the last change to the weights.

**It will very probably not resolve small differences**, for the same reason as the first study:
27 or 28 non-overlapping windows per market, so only gaps of about 0.05 in mean IC can clear the
bound. The strict window has 12 or 13 dates and resolves less.

**These markets are not ones the project trades.** The recipe arm is the production recipe run on
their bars, not a model that has ever been served. Its learning-rate ceiling for these markets was
never measured. It uses London's (0.02), the nearest measured market.

**The selection favours past winners.** Stocks are chosen from today's index members by today's
market value, so the panel holds companies that grew or stayed large. This applies to every arm
alike. It flatters momentum more than it flatters a model with no view of the cross-section.

**It does not settle the first study.** The two are not pooled, and the first stays unread.

## The stocks

The rule is mechanical, and no returns or forecasts were looked at to make the choice
(`choose_stocks.py` in the evidence folder):

1. **Candidates:** today's members of the DAX and MDAX (Xetra, `.DE`), the CAC 40 and SBF 120
   (Euronext Paris, `.PA`), and the SMI and SMIM (SIX Swiss Exchange, `.SW`).
2. **Eligible:** Yahoo Finance quotes the stock in the market's currency (EUR, EUR, CHF). It must
   have daily bars from no later than 2018-01-05 to no earlier than 2026-10-16, fetched through
   production's own `fetch_daily_bars` for 2018-01-01 to 2026-10-21. It must also have a market
   value on Yahoo.
3. **Chosen:** the 40 largest eligible stocks by that market value.

| market | eligible | chosen |
|---|---|---|
| XETR | 46 of 51 | SAP SIE ALV DTE MUV2 IFX DHL MRK DB1 DBK RHM EOAN BAS RWE BAYN CBK MBG VOW3 BMW HNR1 TLX HEN3 ADS HEI FRE SRT3 MTX BEI SY1 VNA CON G1A FME EVK QIA BNR NEM LHA PAH3 ZAL |
| XPAR | 48 of 50 | OR MC TTE AIR SU RMS SAF AI BNP SAN CS EL ENGI DG HO ACA GLE BN ORA STMPA LR SGO DSY KER PUB VIE CAP AMUN RI EN ERF BVI IPN STLAP AC GET ADP CA SW RNO |
| XSWX | 37 of 44 | NOVN NESN UBSG ABBN CFR LISN ZURN SREN LONN GIVN HOLN SCMN SCHP SIKA KNIN SLHN EMSN SGSN GEBN VACN SOON PGHN STMN LOGN BCVN SPSN BEAN PSPN AVOL BARN FHZN SUN TEMN DKSH ADEN CLN TECN |

These were left out:

- **History starts too late:** Siemens Healthineers, Daimler Truck, Porsche, Siemens Energy,
  Covestro (its current Yahoo series begins on 2026-10-20), Unibail-Rodamco-Westfield, Alcon,
  Sandoz, Galderma and SIG.
- **No market value on Yahoo:** Michelin.
- **No data:** Roche, Baloise and Helvetia.

Switzerland therefore has 37 stocks, without Roche. That is a large gap in its index, recorded
here rather than patched by hand.

The bars are stored in `prices.csv` in the evidence folder, 261,487 rows. They are never written
to the database.

## Measure

This is the first study's [measure](kronos-zero-shot.md#measure), with these differences only:

- **Test dates:** every 21 sessions of the market's calendar (`exchange_calendars` XETR, XPAR,
  XSWX), from the first session on or after 2024-07-01, through the last whose 21-session forward
  window is in the stored bars.

  | market | test dates | first | last | strict window (after 2025-09-09) |
  |---|---|---|---|---|
  | XETR | 27 | 2024-07-01 | 2026-08-26 | 12 dates |
  | XPAR | 28 | 2024-07-01 | 2026-09-18 | 13 dates |
  | XSWX | 27 | 2024-07-01 | 2026-09-07 | 12 dates |

- **Members and labels** follow the first study's rules. A member must have at least 400 bars and
  a bar on the test date. Its label is the close-to-close return over the next 21 sessions of the
  calendar, and a member without the bar that ends that window is left out of that date.
- **Arms:**
  1. **Kronos:** unchanged. Kronos-small revision `901c26c1` and Kronos-Tokenizer-base revision
     `0e011738`, the last 400 bars, 21 steps ahead, T = 1.0, top_p = 0.9, top_k = 0, five paths
     averaged in batches of ten, seeded per test date.
  2. **The recipe:** the weekly retrain's candidate on these bars. It uses all thirteen
     engineered features with cross-sectional ranks within the market, a learning-rate ceiling of
     0.02 and seed 42.
  3. **Momentum:** `mom_63_cs_rank` on the test date.
- **The control:** for each test date, the mean IC of 1,000 seeded random rankings of that date's
  members against their labels. This replaces the first study's single random arm.
- **Per arm and date**, the Spearman IC. **Per market and comparison**, the mean difference over
  dates, its Newey-West standard error with lag 1 (`quantpulse.ml.metrics.newey_west_se`), and
  one-sided 95% bounds (mean ± 1.645 × error).

**What the control can catch.** A random ranking's expected IC is exactly zero, whatever the labels
are. Averaged over 1,000 draws per date and 27 dates, its own noise is about 0.001. The tolerance
below is ten times that, so it fires on a broken evaluation and essentially never by chance. Two
examples it would catch: labels that are missing or tied for most members, or a correlation step
that does not return a rank correlation. It cannot catch a look-ahead leak; the dates and the
stored-bars rule guard against that.

## Decision rule, fixed in advance

Per market:

1. **Kronos ahead of the recipe** if the lower bound on mean(Kronos − recipe) is above 0;
   **behind** if the upper bound is below 0; otherwise **not resolved**. The same reading is made
   against momentum.
2. **Kronos has skill** if the lower bound on its own mean IC is above 0.
3. **Not a clean run** if the control's mean IC over the market's dates is more than 0.01 from
   zero, or cannot be computed. Then:
   - Nothing above is read until the cause is found.
   - If a defect is found, it is fixed, every affected figure is recomputed, and both versions are
     reported.
   - If no defect is found, the run is reported unread, and Kronos stays not pursued.

Across markets, read only once all three are in and all three are clean:

- **Ahead of the recipe in at least two markets and behind in none:** propose a forward research
  shadow on the live markets. Kronos would be scored each week and recorded beside the champion,
  used by no book. The shadow would start after the [shadow run](shadow-run.md)'s verdict, before
  which nothing that trains production may change.
- **Otherwise, skill in at least two markets:** record it. Using Kronos as an input to the recipe
  would be its own pre-registered study after the verdict.
- **Otherwise:** record the null. Kronos stays not pursued.

The strict window is reported beside every figure. If it reverses the sign of a market's
difference against the recipe, no action is taken on that market's reading.

## Disclosures

- **This test was designed after the first study's unread figures were seen.** Those figures put
  Kronos below zero in all three markets. To keep that from steering this test:
  - the dates and the Kronos settings are the first study's, unchanged;
  - the recipe and momentum arms are unchanged except for the market-dependent ceiling;
  - the stocks are chosen by a mechanical rule from market value alone;
  - the one design change, the control, answers how the first control failed, not what any arm
    showed.
- **Timing was measured before this page, and nothing else.** One dry run scored the 37 Swiss
  members on 2023-03-01, inside the pre-training window. It took 441 s for Kronos and 21 s for the
  recipe. No accuracy figure was computed. The full run is expected to take about 11 hours.
- **Compute and isolation.** Each market and arm group runs in a throwaway container from the
  first study's image (the project image plus CPU PyTorch). Each container has 3 GB, 6 CPUs, no
  network, and the source mounted read-only. It never touches the stack or the database.
  - Kronos's code is read from the starred mirror at commit `67b630e6` and is not copied here.
  - The weights come from the local Hugging Face cache at the revisions above.
  - The scripts, prices, scores, the image's package versions and the commit are kept in
    `~/quantpulse-experiments/kronos-fresh-stocks-asof-2026-10-21/` (`choose_stocks.py`,
    `run_fresh.py`, `summarize_fresh.py`, `run_all.sh`).
