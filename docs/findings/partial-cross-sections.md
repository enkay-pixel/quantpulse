# Days scored on fewer names than had prices (2026-10-24)

**In short:** On 15 of the 147 market-days scored live so far, the model ranked fewer stocks than
it should have, because some prices came late or never came. For 6 of those days the prices
arrived after that night's run had scored the market, and nothing scores them afterwards. For
9 days the prices were never fetched, which mostly predates the retry that now asks for them
again. On London's 2026-10-22 a timing bug stopped that retry, although the vendor had the
prices. The books lost a name or two a side on most of these days. The largest case is New
York's 2026-10-23, scored on 33 of its 50 listings. No stored data was changed. All three fixes
below were built the same day, by the owner's choice.

**Status: measured 2026-10-24 on the data stored by 16:15 UTC that day, read-only; fixed the
same day** (see [Fixes](#fixes)).

## Why

On 2026-10-24 New York's bars for the 23rd arrived in four batches: 4 of 50 at 00:31 SAST, 29 at
00:59, 15 at 01:29 and 2 at 06:29. The nightly processing run starts at 01:00, so it computed
features for 33 names and scored only those. The question here is how often that happens, what it
does to the paper books, and why nothing fixes it afterwards.

## Measure

Per market and date, from the live record's start, three counts:

- the active listings with a bar;
- the listings scored;
- when scoring ran, which is the earliest prediction row for that market and date.

A date counts as scored live when its predictions were written within four days of it. A later
write is a replay, which ran once all bars had arrived. A **hole** is a listing-day with no bar
at all, inside the span of dates that listing has bars for.

## What came back

**Late bars: 6 live dates.** Each listing below had a bar, stored after that night's scoring,
and was never scored:

| market | date | listings with a bar | scored | arrived late |
|---|---|---|---|---|
| XJSE | 2026-08-11 | 29 | 28 | 1 |
| XJSE | 2026-08-12 | 29 | 28 | 1 |
| XJSE | 2026-08-13 | 29 | 28 | 1 |
| XJSE | 2026-10-12 | 29 | 24 | 5 |
| XNYS | 2026-10-12 | 50 | 47 | 3 |
| XNYS | 2026-10-23 | 50 | **33** | **17** |

**Holes: 9 live dates, 27 listing-days, none filled since:**

| market | date | listings without a bar |
|---|---|---|
| XNYS | 2026-08-04 | 7: GE, GLD, GS, JNJ, META, TSLA, VZ |
| XNYS | 2026-08-06 | 2: KO, UPS |
| XNYS | 2026-08-11 | 1: META |
| XNYS | 2026-09-24 | 3: GOOGL, PG, WMT |
| XNYS | 2026-09-29 | 4: AMZN, KO, WMT, XLF |
| XJSE | 2026-08-26 | 1: NED.JO |
| XJSE | 2026-09-04 | 1: SSW.JO |
| XJSE | 2026-09-09 | 1: IMP.JO |
| XLON | 2026-10-22 | 7: ABF.L, EXPN.L, FRES.L, HSBA.L, NG.L, NWG.L, RKT.L |

Before the live record started there were 23 more holes, 21 of them in London's history.

**What the books did.** Names per side in each market's daily book on those dates, against its
median over the live record:

| market | typical | on the affected dates |
|---|---|---|
| XNYS | 10 long / 18 short | 9/9 on 08-04, 10/10 on 08-06 and 08-11, 11/16 on 10-12, close to typical on the others |
| XJSE | 10 / 10 | 10/10 on every date, except 9/9 on 10-12 |
| XLON | 13 / 22 | **9/14 on 10-22** |

The typical counts exceed `quantile_width` because tied scores at the cut-off are all held. New
York's 2026-10-23 book row does not exist yet. It is formed on the next processing night from the
33 names scored.

## Why nothing fixes it afterwards

**Late bars are never scored.** `score_latest` fills in dates that have no predictions at all,
and re-scores only the newest feature date. A date scored for 33 names has predictions, so on the
following night it is neither pending nor the newest date. The rule exists for a good reason: a
later champion must not rewrite a day the earlier champion scored live. But it also means the
missing names on a partly-scored day are never scored.

**A second scoring pass the same night would have fixed 2026-10-23.** The newest date is always
re-scored by the champion that existed on it, so a run after 06:29 would have filled the 17
names. The book row for that date is formed only the night after, so no published row would
change.

**A hole's retry exists, but it predates most of these holes, and a timing bug blocked the one
since.**

- **The retry arrived on 2026-10-13.** Since then the catch-up sensor re-requests a session's
  missing tickers, fill-only, until a training run has used the session (#115,
  [ADR 0006](../adr/0006-price-data-is-filled-not-rewritten.md)). The New York and JSE holes
  are from August and September, and retrains had used those sessions before the retry existed.
- **The bug: a session is counted as used by any training run created that day in the market's
  time.** `catchup.latest_training_day` reads the date of the newest training run in exchange
  time.
  - London's drift retrains on 10-20, 10-21 and 10-22 were created at 01:05 SAST, which is
    00:05 in London. So each counted that day's session as used before it had traded.
  - 2026-10-22's seven missing tickers were therefore never requested again. Dagster shows only
    the scheduled ingest for that partition.
  - Asked on 2026-10-24, the vendor returned six of the seven 2026-10-22 bars. The seventh,
    Fresnillo, failed on a local cache lock, not on the vendor.
  - Saturday's retrain then used the session, so under the rule it now stays as it is.
- **The same timing would catch any market whose clock passes midnight before 01:05 SAST.**
  Today that is the JSE and London. Next it would be the four European markets in
  [M13](../plans/m13-europe-wave.md).
- **`quantpulse status` takes the same date** (`trained_through`) to say whether a gap will
  still be filled, so it inherits the bug. It lists missing prices. It does not list names that
  had prices and were never scored.

## What it does not show

- **Whether the missing names changed a book's return.** The names that arrive late are not a
  random draw: they are the vendor's delivery order. No figure here estimates what they cost.
- **That the live record is wrong.** It is what was traded on the information at hand. A day
  short of names is the truth of that night, not a reconstruction error.

## Fixes

None changes what a past retrain trained on, so each ships before the
[shadow run](shadow-run.md)'s verdict. The second changes how live books are formed, and the
owner chose it on 2026-10-24. As proposed, then built:

1. **Count a session as used only if the run could have seen it.** `latest_training_day` should
   be the newest session whose bars were stored before the run was created. That matches
   `build_dataset(known_by=...)`, and it replaces the run's local date. It is a bug fix, with a
   unit test for a run created after local midnight.
2. **Re-score the newest date once late bars land.** When a fill-only catch-up stores bars for
   the newest scored session after that night's processing run, re-run `features` and
   `predictions` only. It must not touch `option_chains`, whose off-hours snapshot overwrites
   good rows. The existing newest-date re-score then fills the missing names with the champion
   of the day, before that date's book row exists. It is bounded to the hours before the next
   session's ingest.
3. **Report a short cross-section.** An asset check on `predictions`, and a line in
   `quantpulse status`, would compare the newest date's scored names with the listings that had
   a bar. Any market short by more than one name would be reported, so the next 2026-10-23 is
   seen the morning it happens. Today neither shows it: the status report counts prices, not
   predictions.

**As built:**

- `catchup.latest_training_day` now returns the newest session with a bar stored before the
  run.
- `late_bars_rescore_sensor` runs `rescore_job` (features and predictions). It requires the
  session to be the market's newest, with no book row yet, and makes at most three passes. It
  stops once a pass has scored nothing new, which covers a listing whose features cannot be
  computed yet.
- `predictions_cover_priced_listings` allows one unscored listing.
- `quantpulse status` prints the names a session was scored without.

**What they cannot restore:**

- **London's 2026-10-22 stays without its seven bars.** Saturday's retrain used the session.
- **The earlier late-scored days keep their partial books,** because their book rows were
  formed before the late bars arrived.
- **New York's 2026-10-23 is the one case still in reach.** Its book row is formed on the next
  processing night, so the sensor fills its 17 names on the first evaluation after the deploy.
  That pass also re-scores the 33 names scored that night, because their cross-sectional ranks
  now include all 50. No book has used those scores yet.

**Verified after the deploy (2026-10-24):**

- The sensor launched one re-score at 19:13 SAST. It ran for 55 s and peaked at 1,302 MiB, 64%
  of the daemon's cap.
- New York's 2026-10-23 now has 50 predictions, all by champion v10, against 33 before.
  `predictions_cover_priced_listings` passes with none unscored.
- Prices, features, predictions and books through 2026-10-22 are identical before and after:
  `fingerprint-before-deploy.txt` and `fingerprint-after-rescore.txt` in the evidence folder.

Evidence is in `~/quantpulse-experiments/partial-cross-sections-asof-2026-10-24/`:
`per_date.sql`, `holes.sql`, `book_sides.sql` and their CSVs, `summarize.py`, `summary.txt`,
`refetch_check.py` and `.txt`, and `as_of.txt`.
