# Kronos again, on stocks it was never scored on here (pre-registered 2026-10-22)

**In short:** A second test of Kronos, the open price-chart model from the
[first study](kronos-zero-shot.md). It uses the same dates, settings and competitors, on 117
German, French and Swiss stocks that study never touched, and a control that can only fail when
the evaluation itself is broken. It only measures; nothing in production changes because of it.
**It came back clean and null.** Kronos ranked these stocks no better than the project's recipe
in any market, and showed no skill of its own in any; its average was below zero in all three.
Kronos stays not pursued.

**Status: run 2026-10-22/23, clean; the null is recorded** (see [Results](#results)). The
sections down to the results are the pre-registration, which reached `main` before any forecast
on its test dates existed, under the rule in [How to measure things
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

## Results

**Run 2026-10-22 16:30 to 2026-10-23 00:54 SAST, commit `2b65e98` (the pre-registration's merge),
Kronos code `67b630e6`: clean.** Every arm scored every member on every date:

- 27 dates for XETR, 28 for XPAR and 27 for XSWX;
- 40, 40 and 37 members each date;
- no missing label;
- the same members in every arm.

**The control, read first.** Its mean IC was +0.0018 on XETR, −0.0004 on XPAR and +0.0013 on
XSWX. All three are within twice their expected noise of about 0.001 and far inside the 0.01
tolerance, so the run is clean under rule 3.

**The reading** (mean IC over the dates; Kronos minus each arm, with one-sided 95% bounds,
Newey-West lag 1):

| market | window | dates | Kronos | recipe | momentum | Kronos − recipe | Kronos − momentum | Kronos skill, lower bound |
|---|---|---|---|---|---|---|---|---|
| XETR | full | 27 | −0.049 | +0.029 | +0.041 | −0.078 [−0.197, +0.041] not resolved | −0.091 [−0.250, +0.069] not resolved | −0.128 |
| XETR | strict | 12 | +0.076 | −0.023 | −0.084 | +0.099 [−0.092, +0.291] not resolved | +0.160 [−0.091, +0.412] not resolved | −0.049 |
| XPAR | full | 28 | −0.059 | −0.092 | +0.039 | +0.034 [−0.019, +0.086] not resolved | −0.097 [−0.189, −0.005] **behind** | −0.109 |
| XPAR | strict | 13 | −0.037 | −0.101 | +0.028 | +0.064 [−0.014, +0.142] not resolved | −0.065 [−0.224, +0.095] not resolved | −0.125 |
| XSWX | full | 27 | −0.053 | −0.032 | +0.004 | −0.021 [−0.122, +0.079] not resolved | −0.057 [−0.175, +0.061] not resolved | −0.118 |
| XSWX | strict | 12 | −0.065 | −0.023 | +0.031 | −0.042 [−0.136, +0.053] not resolved | −0.096 [−0.248, +0.057] not resolved | −0.156 |

**Under the rule:**

- **Against the recipe,** Kronos was ahead in no market and behind in none.
- **Kronos had skill** in no market. Its mean IC was below zero in all three, and no skill
  bound clears zero.
- **So: record the null, and Kronos stays not pursued.**
- **The strict window** reverses the sign against the recipe on XETR (−0.078 over the full
  window, +0.099 after 2025-09-09, unresolved both ways). Under the rule no action is taken on
  XETR's reading, which changes nothing, since the action is the null.
- **Against momentum,** the one resolved reading is that Kronos is behind it on XPAR.

**What it does not show.** That Kronos is useless. As the pre-registration said, only gaps of
about 0.05 in mean IC could clear the bound, and the Kronos-minus-recipe intervals span 0.10
to 0.38. It also leaves open whether a fine-tuned Kronos or another configuration would do better:
this was zero-shot, with one fixed configuration.

The recipe was weak here too: below zero on XPAR and XSWX. That says these are hard markets to
rank in 21-session windows over this period. It is not a judgement of the live models, which
trade other markets.

The direction matches the first study's unread figures, where Kronos was below zero in all three
markets. That study stays unread and is not pooled with this one.

### What the data held, found while checking it

**Holcim's spin-off is not credited in Yahoo's series.** `HOLN.SW` falls 48% on 2025-06-16, when
Holcim distributed Amrize, so its label at the 2025-06-04 test date (−35%) is a corporate action,
not a loss. Its momentum and volatility inputs are distorted for weeks after. Every arm saw the
same bars and was judged on the same label.

Removing Holcim from XSWX's evaluation is a check made after the reading, not part of the rule.
It moves nothing:

- Kronos − recipe becomes −0.030 [−0.132, +0.072], still not resolved;
- Kronos's skill bound becomes −0.124;
- the control is +0.0005.

The recipe still trained on Holcim's bars.

**Other one-day moves beyond −25% or +35%** in the 117 series:

- Avolta, March 2020, and Temenos, February 2024: real crashes, both before the test window.
- Stellantis's merger in January 2021 (+39% and +95%) and Sulzer's medmix spin-off in September
  2021 (−35%): corporate actions, in training history only.
- Stellantis on 2026-02-06 (−25%): inside the test window and taken as a real fall; it has not
  been checked against filings.

The same fetcher serves production, so [M13](../plans/m13-europe-wave.md)'s backfill must check
for this before computing features.

**A correction to the pre-registration's list of exclusions.** Roche was not missing from Yahoo.
`ROG.SW`, its non-voting certificates, returns nothing, but its bearer shares (`RO.SW`) have full
history. They were not among the candidates, so XSWX ran without Roche as registered.

**Timing.** Kronos took about 380, 315 and 280 seconds per date on XETR, XPAR and XSWX, against
441 s in the dry run. The whole run took 8 hours 23 minutes.

**Evidence:** `~/quantpulse-experiments/kronos-fresh-stocks-asof-2026-10-21/`:

- the scripts: `run_fresh.py`, `summarize_fresh.py`, `run_all.sh`, `choose_stocks.py`;
- the data: `prices.csv`, `selection.json`;
- the run's output: `out/` (scores, per-date ICs, `summary.json`), `summary.txt`, `run.log`;
- the sensitivity check: `sensitivity_holcim.py` and `.txt`;
- the provenance: `commit.txt`, `kronos-code-commit.txt`, `image-packages.txt`.
