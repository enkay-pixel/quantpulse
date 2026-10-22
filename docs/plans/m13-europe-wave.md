# M13 — The first wave of more markets: Frankfurt, Paris, Zurich, Amsterdam

**Status: APPROVED 2026-10-22; phase 0 built and proven, deploying after 2026-10-24's
retrain.** It follows the checklist London produced
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
| When | **After Saturday 2026-10-24's retrain.** It is London's first challenger and the retrain-duration reading the runbook needs; nothing should change under it. Phase 0 deploys on 2026-10-25 at the earliest. |

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

The daemon's container is capped at 1.5 GiB. Each step runs in its own process, and every process
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

## The markets

The calendar codes and timezones below are verified. The trading hours and Roche's listing come
from this check; the margins and ceilings are placeholders until measured.

```python
XETR = Exchange(code="XETR", timezone="Europe/Berlin", close_hour=18,  # Xetra ends 17:30
                currency="EUR", benchmark="EXS1.DE", display_symbol="€", ...)
XPAR = Exchange(code="XPAR", timezone="Europe/Paris", close_hour=18,   # Euronext ends 17:30
                currency="EUR", benchmark="CAC.PA", display_symbol="€", ...)
XSWX = Exchange(code="XSWX", timezone="Europe/Zurich", close_hour=18,  # SIX ends 17:30
                currency="CHF", benchmark="CSSMI.SW", display_symbol="CHF ", ...)
XAMS = Exchange(code="XAMS", timezone="Europe/Amsterdam", close_hour=18,
                currency="EUR", benchmark="IAEX.AS", display_symbol="€", ...)
# all: has_options=False, display_divisor=1.0, quantile_width=0.25,
# ic_promotion_margin=0.027 and learning_rate_ceiling=0.02 until measured (phase 5)
```

The 0.027 placeholder is the widest margin measured on any market, so a challenger cannot be
promoted on a too-small margin before its own is measured. 0.02 is the ceiling both non-US
markets needed.

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
2. **Configure.** The four registry entries, the universe blocks (the 40 largest eligible names
   per market, checked against each index's current composition), the dbt `benchmarks` entries,
   and canonical English Wikipedia titles.
3. **Backfill and prove nothing moved.** Fingerprint the three markets, sync the universe,
   backfill all four from 2018, list the one-day moves that may be uncredited corporate actions
   (see Risks), build features, compare: the three must be identical.
4. **First champions** through the unchanged gate. Any market whose first model misses the Sharpe
   floor shows its data and research without a model. Then replay-score each market's history,
   build the marts, and read every market in the browser, prices included.
5. **Measure before the first challenger.** For each market, a margin study (about 10 minutes)
   and a learning-rate ceiling study (about 1.5 hours). They run one at a time in throwaway
   containers, about 7 hours in all, and must finish before the next Saturday retrain. Then
   update the runbook with the new ingest times and record the headroom with seven markets.

## Risks

| Risk | Mitigation |
|---|---|
| Phase 0 moves a number in a frozen market | Row-for-row fingerprint before and after, as for London; the shadow verdict depends on it |
| Seven markets outgrow the cap anyway | Phase 0's measurement decides before anything is backfilled; raising the cap is the fallback |
| A listing quoted in another currency | `quantpulse backfill` refuses it before storing a bar |
| A spin-off or merger Yahoo does not credit | Found in the [Kronos replication](../findings/kronos-fresh-stocks.md#what-the-data-held-found-while-checking-it): Holcim −48% on 2025-06-16 (Amrize), Sulzer −35% in 2021 (medmix), Stellantis +95% in 2021 (the merger). The unit repair catches only ×100 glitches. Phase 3 lists every one-day move beyond −25% or +35% and checks each against the company's filings before features are computed |
| The weekly retrain no longer fits the laptop's Saturday window | Saturday's three-market duration is read first; seven markets roughly double it |
| Placeholder margins promote a lucky challenger | The placeholder is the widest measured margin, and phase 5 measures each before the first challenger |
| English Wikipedia is a weak attention signal for a mid cap | The ownership-free markets already rely on it; it is a feature, not a gate |
| The Kronos replication uses three of these markets | It reads prices from its own file, never the database; onboarding starts after it has been read |

## Out of scope

- Options, short interest and filings for these markets: no free source.
- Currency conversion or a combined European book: each book is one market and one currency.
- Canada, Asia-Pacific and the rest: the next waves, each after this one's headroom reading.
