# M13 — The first wave of more markets: Frankfurt, Paris, Zurich, Amsterdam

**Status: APPROVED 2026-10-22; phases 0–5 done by 2026-10-28 (Europe backfilled, the three live
markets proven unchanged, Zurich's first champion promoted, Frankfurt, Paris and Amsterdam
without a model, and each market's margin and ceiling measured). The 2026-10-31 retrain judges the
first challengers.** It follows the checklist London produced
([ADR 0005 amendment](../adr/0005-exchange-as-a-first-class-dimension.md), from the
[M12 pilot](m12-london-pilot.md)) and, unlike London,
starts with the laptop's headroom, because four markets at once is where the current design
stops fitting.

**In short:** Xetra (XETR), Euronext Paris (XPAR), SIX Swiss Exchange (XSWX) and Euronext
Amsterdam (XAMS) join as markets four to seven. Each has its own universe, model, books and
research pages. The existing three markets do not change, and that is checked row for row, as
it was for London. Before anything is added, the one step whose memory grows with the number of
markets is changed to work one market at a time.

## Decisions (settled at approval)

| Question | Decision |
|---|---|
| Which markets | **The four European markets together.** London's time zone, Yahoo data of the same kind, English Wikipedia pages for nearly every company, and an index fund with history from 2018 in each. Canada, then Asia-Pacific, then the rest follow as later waves. |
| How to make room | **Change the code first, then measure.** The features step, which holds every market in memory, works one market at a time, and a run executes at most two steps at once. A larger memory cap is the fallback if the measurement still says so. Raising it first would leave the next wave with the same problem and less room to run experiments. |
| When | **Brought forward to 2026-10-23** (the owner's decision that day). The plan was to deploy after Saturday 2026-10-24's retrain, so nothing changed under London's first challenger. Then the 10-23 01:00 processing run and that day's 13:00 research job held 99% and 98% of the daemon's cap in memory it cannot reclaim. Nothing was killed. The retrain is a single step, so neither phase 0 change touches its duration reading. |

## What was verified first (not assumed)

- **Calendars.** `exchange_calendars` has XETR, XPAR, XSWX and XAMS (checked for M12).
- **Prices, history and currency.** Yahoo serves all four from 2018 in the market's currency.
  Eligible candidates have bars from 2018-01-05 or earlier through 2026-10-16 or later, quoted in
  EUR or CHF, with a market value:
  - XETR: 46 of 51 DAX and MDAX names;
  - XPAR: 48 of 50 CAC 40 and SBF 120 names;
  - XSWX: 38 of 45 SMI and SMIM names;
  - XAMS: 35 of 49 AEX and AMX names.

  The usual reason for leaving one out is a listing after 2018, for example Siemens
  Healthineers, Porsche, Prosus, Universal Music, DSM-Firmenich and Alcon. Two more cases:
  - Unilever's Amsterdam line starts only in December 2020.
  - Baloise and Helvetia return nothing.
- **Roche is there under its bearer shares.** Yahoo returns nothing for `ROG.SW`, the
  non-voting certificates, and full history for `RO.SW`. Switzerland lists Roche as `RO.SW`.
- **Breadth.** With `quantile_width = 0.25`, 40 names give 10 a side, Zurich's 38 give 9 or 10,
  and Amsterdam's 35 give 8 or 9.
- **Benchmarks**, all with history from 2018 in the market's currency:
  - `EXS1.DE`, iShares Core DAX;
  - `CAC.PA`, Amundi CAC 40;
  - `CSSMI.SW`, iShares SMI;
  - `IAEX.AS`, iShares AEX.
- **Run concurrency.** Dagster runs one job at a time (`max_concurrent_runs: 1`), so the four
  ingests that fire at the same European hour queue rather than stack. Inside a run, steps still
  execute in parallel processes, and that is where the memory goes (below).

Evidence: `~/quantpulse-experiments/m13-europe/` (`feasibility.py`, `feasibility.json`) and, for
the first three markets, the stock selection of the
[Kronos replication](../findings/kronos-fresh-stocks.md), which used the same rule.

## Headroom, and why it comes first

The daemon's container was capped at 1.5 GiB, and is at 2 GiB since 2026-10-24 (below). Each step
runs in its own process, and every process
starts at about 285 MiB because it loads the whole stack. Measured with three markets (120
listings):

- **The nightly `features` step** reached 814 MiB, because it computes every market in one frame.
  That is about 530 MiB of working memory, roughly 4.4 MiB per listing. The wave takes the panel
  to about 277 listings, which puts this one step near 1.5 GiB on its own.
- **The research job at 13:00 on 2026-10-22** ran four steps at once. The container stood at
  1,373 MiB when the last of them ended, 89% of the cap. That is with today's markets.
- **The nightly processing run** reports its first container-wide figure tonight, the night of
  2026-10-22/23, which is the first since #158.

Phase 0 therefore changes how the work is laid out. It does not change what is computed:

1. **Features one market at a time.** `features` is the only step that holds every market at
   once; `predictions` and `drift_report` already loop over markets. Ranks are already computed
   within a market, so the output is identical by construction, and the fingerprint proves it.
   The step's peak then follows the largest market, 50 listings, not the sum, so later waves add
   time, not memory.
2. **Rows built a chunk at a time.** Measured while building phase 0: of the step's 814 MiB, 342
   were the upsert's list of one dict per row for the whole panel (1.37 KiB a row). Computing
   the features themselves took about 280 MiB above the imports.
3. **At most two steps at once per run**, using the multiprocess executor's `max_concurrent`.
   This adds seconds to a run, and it bounds the research job, which today is the closest to the
   cap.
4. **Skip unchanged feature rows.** The nightly upsert rewrites every feature row (2.36 million
   updates when London arrived), and seven markets would more than double that.
5. **Measure** for two nights with the three markets, then decide. **The gate is the
   `resource_headroom` check's own line:** the heaviest run must hold less than 85% of the cap
   in memory the container cannot reclaim (decided 2026-10-22).
   - **No lower bar can be met.** A run with two steps alive sits at about 78% from the stack
     alone, whatever the markets. The two ingest runs on the evening of 2026-10-22 left the
     container at 1,191 and 1,199 MiB: the daemon and its code server, the run's worker, and
     two step processes of about 290 MiB each.
   - **What grows with markets is the features step**, which phase 0 bounds by the largest
     market.
   - **The same line is read again after the backfill, with seven markets.** If a run crosses
     it either time, the cap rises, within the 7.75 GiB the Docker VM has, and the experiment
     containers shrink to match.
   - **Postgres is recorded with each reading.** It stood at 412 of its 512 MiB that evening,
     mostly reclaimable cache, and seven markets' data will add to it.

**The first night on phase 0 (2026-10-24 01:00):**

| | 2026-10-23, before | 2026-10-24, phase 0 |
|---|---|---|
| `features` step peak | 806 MiB, 34 s | **417 MiB, 20 s** |
| Feature rows written | all 256,114 | **103** (the new day's) |
| Heaviest run, container's unreclaimable memory | 1,527 MiB, **99%** of the cap | 1,336 MiB, **87%** |

- **The freeze proof is identical.** Prices, features and predictions are unchanged through
  2026-10-22, and the nine books through 2026-10-21, their last row before the deploy (evidence
  in `~/quantpulse-experiments/m13-europe/phase0-deploy/`).
- **87% is over the gate,** so the cap rose to 2 GiB after that day's retrain, as the plan says.
  The same run sits at 65% of it.
- **The retrain itself took 1.4 minutes** for three markets and peaked at 76% of the old cap.
- **Experiment containers shrink to 2.5 GB,** so the caps still fit Docker's 7.75 GiB.

**Night two, on the 2 GiB cap (2026-10-26/27), and the gate is cleared:**

- **Processing (01:00):** 1,430 MiB at its heaviest, **70%** of the cap.
- **Research job:** its first full runs at two steps at once reached 1,287 MiB on 10-26 (63%) and
  1,339 MiB on 10-27 (65%), against 98% when it ran four steps at once.
- **`resource_headroom` passed,** its first pass since phase 0.
- **What 10-27's research reading is:** the job's 13:00 run and retry failed on a brief DNS
  outage, and the 65% is from the re-run at 13:24.

Every run since the cap rose is under the 85% line, so phase 1 can start.

**Night three, the first with seven markets (2026-10-27/28), after the backfill:**

- **Processing (01:00):** 1,441 MiB at its heaviest, **70%** of the cap, against 1,430 MiB with
  three markets.
- **The `features` step** took 418 MiB in 41 s, against 417 MiB in 20 s with three markets. Its
  memory follows the largest market and its time the sum, as phase 0 intended.
- **The four European ingests at 21:30 SAST** held at most 1,198 MiB, 58%.
- **`resource_headroom` passed.** Postgres stood at 190 of its 512 MiB at 01:15.
- **The research job (13:00 on 2026-10-28),** its first run with seven markets, reached
  1,566 MiB, **76.5%** of the cap, in 3 minutes 14 seconds. Its readings with three markets were
  63% and 65%. Its steps each peaked at 397 MiB or less, as before, so what grew is the container
  around them, not any one step.

So with seven markets every run is under the 85% line; the heaviest is about 175 MiB below it.

## The markets

The calendar codes and timezones below are verified. The trading hours and Roche's listing come
from this check. The margins and ceilings began as placeholders and were measured in phase 5.

```python
XETR = Exchange(code="XETR", timezone="Europe/Berlin", close_hour=18,  # Xetra ends 17:30
                currency="EUR", benchmark="EXS1.DE", display_symbol="€", ...)
XPAR = Exchange(code="XPAR", timezone="Europe/Paris", close_hour=18,   # Euronext ends 17:30
                currency="EUR", benchmark="CAC.PA", display_symbol="€", ...)
XSWX = Exchange(code="XSWX", timezone="Europe/Zurich", close_hour=18,  # SIX ends 17:30
                currency="CHF", benchmark="CSSMI.SW", display_symbol="CHF ", ...)
XAMS = Exchange(code="XAMS", timezone="Europe/Amsterdam", close_hour=18,
                currency="EUR", benchmark="IAEX.AS", display_symbol="€", ...)
# all: has_options=False, display_divisor=1.0, quantile_width=0.25 (XAMS 0.33, set in phase 2),
# ic_promotion_margin=0.027 and learning_rate_ceiling=0.02 until measured (phase 5)
```

The 0.027 placeholder was the widest margin measured on any market, so that a challenger could not
be promoted on a too-small margin before its own was measured. 0.02 was the ceiling both non-US
markets needed. Phase 5 replaced both: margins 0.006 XETR, 0.017 XPAR, 0.023 XSWX and 0.031 XAMS,
and the default ceiling, 0.2, for all four.

Ingest runs at 20:30 local time: 21:30 SAST from 2026-10-25, when Europe's clocks change, and
20:30 SAST in summer. That is before New York closes, so all seven markets are in each night's
processing.

## Phases

0. **Headroom.** The four changes above, behind a row-for-row fingerprint of all three markets'
   `features`, `predictions` and books. Two nights are then measured. Before merging, the new
   step's rows were computed from the live panel read-only and compared with the stored ones:
   identical, all 256,001 of them (`phase0_proof.py` in the evidence folder).
1. **Generic changes.** The dashboard's market picker becomes a menu: seven four-letter buttons do
   not fit a phone's width. Nothing else on the dashboard names a market, which London proved.
   **Done 2026-10-27:**
   - The picker is a native menu.
   - Each option names its market by city beside its code, as in "Johannesburg (XJSE)". The
     names come from a required `display_name` in the registry, served by `/exchanges`, so a
     new market cannot be registered without one.
   - Checked in the browser at desktop and phone width: the menu is 164 px wide at 375 px, with
     no sideways scroll.
2. **Configure.** The four registry entries, the universe blocks (the 40 largest eligible names
   per market, checked against each index's current composition), the dbt `benchmarks` entries,
   and canonical English Wikipedia titles.

   **Done 2026-10-27, not deployed: it goes live with phase 3's backfill.**

   **Candidates.** The index members on English Wikipedia: DAX and MDAX; CAC 40 and CAC Next 20
   (the SBF 120 page lists no members); SMI and SMIM; AEX and AMX.

   **Chosen.** The same rule as London and the Kronos replication: quoted in the market's
   currency, bars from early 2018, then the largest by market value.

   | market | eligible | chosen | a side |
   |---|---|---|---|
   | XETR | 78 | 40 | 10 |
   | XPAR | 50 | 40 | 10 |
   | XSWX | 37 | 37 | 9 |
   | XAMS | 30 | 30 | 10, at a 0.33 width (the owner's choice) |

   **Left out:**
   - companies another market here already holds: Shell, Unilever and RELX in London, Prosus on
     the JSE, and Airbus, which goes to Paris;
   - by the owner's choice, Holcim (the Amrize spin-off) and Stellantis (the 2021 merger), whose
     histories carry corporate actions Yahoo does not credit.

   Amsterdam has 30 rather than 35 because Wikipedia's AMX table still lists companies that have
   left the market.

   **The dividend check passes in all four markets.** It is the
   [corporate-actions finding](../findings/uncredited-corporate-actions.md#proposed-checks-where-bars-arrive)'s
   `dividends_credited`, run on every chosen name. The median share of each dividend that the
   adjusted series credits is 1.026 to 1.029, so these markets are total returns, unlike the JSE's
   and London's hundredth.

   **One-day moves beyond −25% or +35%** among the chosen are all real: Delivery Hero (2022
   guidance), Avolta and Fugro (March 2020), and Temenos (the 2024 short report).

   **Wikipedia titles.** Each was checked against its article's first sentence, because a title
   can resolve and still be the wrong page: Temenos is also a Greek word, Fresenius a surname, and
   "OCI" redirects to a Korean company. Six companies have no English article of their own and are
   listed as `null`: Helvetia Baloise, IMCD, TKH, Basic-Fit, OCI and AMG. The page-view fetch
   leaves them out.

   Evidence: `~/quantpulse-experiments/m13-europe/phase2/`.
3. **Backfill and prove nothing moved.** Fingerprint the three markets, sync the universe,
   backfill all four from 2018, list the one-day moves that may be uncredited corporate actions
   (see Risks), build features, compare: the three must be identical.

   **Done 2026-10-27.** Phase 2 was deployed at 14:51 SAST, and every step ran in a throwaway
   container.

   - **Universe:** sync-universe added 151 listings and deactivated none.
   - **Backfill:** 338,514 bars, 2018-01-02 to 2026-10-26. The end is given explicitly, because
     the default (today) would have stored the European session then trading as its close. The
     currency guard refused nothing. The CLI has since been fixed to choose a safe end itself
     ([data dictionary](../data-dictionary.md)). At that hour it would also have refused the
     26th for the four new markets, since the request ran to the 27th while they traded.
     **Checked 2026-10-30: no 10-26 bar is the 10-27 session.** All 151 stored 10-26 bars are
     the vendor's 10-26 bar; five in Zurich have since been revised by the vendor by a tick or a
     few hundred shares. Evidence: `~/quantpulse-experiments/m13-europe/phase3-end-check/`.
   - **One-day moves:** the stored moves beyond −25% or +35% are the five real ones found in
     phase 2.
   - **Features:** 329,001 rows for the four new markets. The other three wrote **0 rows**: their
     256,354 rows came out identical.
   - **Page views:** 141 titles from 2018.
   - **The fingerprint of XNYS, XJSE and XLON** prices, features, predictions and books through
     2026-10-26 is **identical** before and after.
   - **The dashboard** lists all seven markets. The new four show their data and say no champion
     is trained yet.

   Evidence: `~/quantpulse-experiments/m13-europe/phase3/`.
4. **First champions** through the unchanged gate. Any market whose first model misses the Sharpe
   floor shows its data and research without a model. Then replay-score each market's history,
   build the marts, and read every market in the browser, prices included.

   **Done 2026-10-28, from 01:10 SAST, once that night's processing run had been checked.** Every
   step ran in a throwaway container. **Zurich has its first champion. Frankfurt, Paris and
   Amsterdam do not**, and show their data and research without a model.

   | market | holdout IC | momentum's IC | needed | holdout Sharpe | outcome |
   |---|---|---|---|---|---|
   | XETR | 0.022 | −0.002 | 0.025 | 0.65 | rejected: short of momentum plus the margin |
   | XPAR | −0.043 | 0.015 | 0.042 | −1.14 | rejected: IC below zero |
   | XSWX | 0.024 | −0.025 | 0.002 | 1.34 | **promoted, v1** |
   | XAMS | −0.003 | 0.042 | 0.069 | −1.08 | rejected: IC below zero |

   *Needed* is momentum's IC plus the market's margin, the 0.027 placeholder. Each holdout runs
   from 2025-06-19 or 06-20 to 2026-09-28, 320 to 327 days.

   - **Frankfurt missed on the placeholder margin, by 0.003.** A first model must beat momentum
     by the market's margin, and Europe's is the placeholder until phase 5 measures it. At a
     margin of 0.024 or less this candidate would have been promoted. The gate stays unchanged;
     Saturday's retrain fits a new candidate, judged on the measured margin.
   - **Paris and Amsterdam fail on their own IC,** which is below zero, so no margin would have
     promoted them.
   - **Zurich, replayed:** 81,775 predictions from 2018-04-04 to 2026-10-27, and three books
     through 2026-10-26. The daily book's in-sample replay is +42.7% over 2,151 days, Sharpe 0.65.
     Its live record starts with the next processing run.
   - **The marts** built with all 145 dbt models and tests passing.
   - **The fingerprint of XNYS, XJSE and XLON** prices, features, predictions and books through
     2026-10-27 is **identical** before and after.
   - **The dashboard, read for all seven markets.** Zurich shows prices in CHF beside CSSMI.SW,
     champion v1, and its replay labelled in-sample. The three without a model showed no price at
     all, because the price panel cycles through the model's forecasts and they have none. It now
     cycles through the market's stocks instead (in €), and the empty panels say no model has
     cleared the gate rather than that nothing has been trained.
   - **`predictions_are_current` failed every night** on those three, because it reported any
     market with no predictions. Since 2026-10-28 a market that has never had a champion passes
     and is listed under `awaiting_first_champion`, so the check can still go red for a market
     that really has stopped (the owner's choice).

   Evidence: `~/quantpulse-experiments/m13-europe/phase4/`.
5. **Measure before the first challenger.** For each market, a margin study (about 10 minutes)
   and a learning-rate ceiling study (about 1.5 hours). They run one at a time in throwaway
   containers, about 7 hours in all, and must finish before the next Saturday retrain. Then
   update the runbook with the new ingest times and record the headroom with seven markets.

   **Done 2026-10-28, from 17:13 to 21:43 SAST.** The rules were written down before the first
   fit, and every panel was built from the bars stored by 15:00 UTC that day. Each ceiling study
   took about an hour and each margin study one or two minutes.

   | market | ceiling | collapses at 0.2 / 0.06 / 0.02 | margin | was |
   |---|---|---|---|---|
   | XETR | 0.2 | 2 / 1 / 2 of 18 | **0.006** | 0.027 |
   | XPAR | 0.2 | 18 / 18 / 18 | **0.017** | 0.027 |
   | XSWX | 0.2 | 4 / 4 / 5 | **0.023** | 0.027 |
   | XAMS | 0.2 | 12 / 11 / 11 | **0.031** | 0.027 |

   - **No market needs a ceiling.** Adopting one needs at least three fewer collapses out of 18,
     and none removes more than one. London's collapses came from the fastest learning rates;
     Europe's mostly do not ([learning-rate-ceiling.md](../findings/learning-rate-ceiling.md#europe-2026-10-28)).
   - **Each study measures production.** The newest panel at seed 42 under the placeholder
     reproduces each first model's holdout IC to four decimals, in all four markets.
   - **The margins, from 2 sd of a sixteen-seed refit** ([promotion-margin.md](../findings/promotion-margin.md#europe-2026-10-28)).
     Zurich's is on its champion's specification. The other three are on what the tuner chose,
     since none has a champion, and each is re-measured on its first one.
   - **One first decision would have gone the other way on the measured margins: Frankfurt's.**
     Its model clears 0.006, and Zurich's promotion holds at 0.023. Frankfurt's is not re-judged;
     the 2026-10-31 retrain fits a new candidate.
   - **Amsterdam's margin is wider than the placeholder,** which was meant to be a safe upper
     bound. Its first model scored below zero, so no decision would have been different.
   - **The runbook carries the European ingest times** ([runbook](../runbook.md)), and the headroom
     with seven markets is above: research 76.5% and processing 70.4% of the 2 GiB cap.
   - **The values take effect when the pipeline image is rebuilt,** which has to happen before the
     2026-10-31 retrain at 15:00 SAST.
   - **The shadow run is unaffected.** Its verdict reads only XNYS and XJSE, whose settings did not
     change.

   Evidence: `~/quantpulse-experiments/m13-europe/phase5/`.

## Risks

| Risk | Mitigation |
|---|---|
| Phase 0 moves a number in a frozen market | Row-for-row fingerprint before and after, as for London; the shadow verdict depends on it |
| Seven markets outgrow the cap anyway | Phase 0's measurement decides before anything is backfilled; raising the cap is the fallback |
| A listing quoted in another currency | `quantpulse backfill` refuses it before storing a bar |
| A spin-off or merger Yahoo does not credit | Found in the [Kronos replication](../findings/kronos-fresh-stocks.md#what-the-data-held-found-while-checking-it): Holcim −48% on 2025-06-16 (Amrize), Sulzer −35% in 2021 (medmix), Stellantis +95% in 2021 (the merger). The unit repair catches only ×100 glitches. Phase 3 lists every one-day move beyond −25% or +35% and checks each against the company's filings before features are computed. The same scan of the live markets (2026-10-23) found dividends the larger risk: the JSE and London credit them at a hundredth. One name in each of the four markets credits in full, but run the [dividend check](../findings/uncredited-corporate-actions.md#proposed-checks-where-bars-arrive) on every name before the backfill |
| The weekly retrain no longer fits the laptop's Saturday window | Saturday's three-market duration is read first; seven markets roughly double it |
| A post-midnight drift retrain blocks a session's retry | Found 2026-10-24 ([finding](../findings/partial-cross-sections.md#why-nothing-fixes-it-afterwards)): the catch-up counts a session as used by any training run created that local day, and Europe's clocks pass midnight before the 01:05 SAST drift retrain, as London's does. Fixed 2026-10-24: a run has used a session only if the session's bars were stored before it |
| Placeholder margins promote a lucky challenger | The placeholder is the widest measured margin, and phase 5 measures each before the first challenger. Measured 2026-10-28: Amsterdam's, 0.031, is wider, but its first model scored below zero, so nothing was promoted on it |
| English Wikipedia is a weak attention signal for a mid cap | The ownership-free markets already rely on it; it is a feature, not a gate |
| The Kronos replication uses three of these markets | It reads prices from its own file, never the database; onboarding starts after it has been read |

## Out of scope

- Options, short interest and filings for these markets: no free source.
- Currency conversion or a combined European book: each book is one market and one currency.
- Canada, Asia-Pacific and the rest: the next waves, each after this one's headroom reading.
