# ADR 0008: Options as a second instrument — a paper book that expresses the stock signal as spreads

**Status**: accepted · **Date**: 2026-10-16

## Context

The platform's paper books hold shares. The owner asked whether options could join them, as a
separate branch, using the same data or new data and models.

What the data allows decides the shape:

- **No options history exists to train on.** Free historical chains do not exist, so the only
  history is the platform's own nightly capture, which held 60 snapshot days on 2026-10-16. A
  standing decision (`options-descriptive-only`) already defers IV-rank and IV-change signals to
  about 250 days, because findings on samples this small reversed within a week.
- **The JSE has no free option chains.** Anything here is NYSE only.
- **A rule-based book needs no training.** Expressing the existing stock signal in options asks a
  question the data can answer as it accrues: *does holding the signal through options beat
  holding the shares, after realistic costs?*

## Decision

1. **A paper options book, separate from the share books.** It has its own module
   (`options/book.py`), its own tables (`option_book_positions`, `option_book_daily`), its own
   Dagster job (`options_book_job`, after the evening processing run) and its own section on the
   Options tab. It is never a model input, and it cannot change the share books, the live record
   or the shadow run.
2. **It varies exactly one dimension from the 21-session share book: the instrument.** Each
   cohort opens on that book's rebalance dates, on the same names, read from its stored positions
   rather than recomputed. Long names get a bull call spread and short names a bear put spread,
   using the strike rule the Options tab already illustrates (long leg nearest the money, short leg
   about 10% further out). The expiry is the first one on or after the next rebalance, and each
   cohort closes at that rebalance, so both books hold for the same window.
3. **Prices are pessimistic, on quotes a trader could deal at.** Buying pays the ask and selling
   receives the bid, at entry and at exit, with commission at $0.65 per contract per leg each way.
   A quote counts only if it is *sound*: a real bid below the ask, and a gap of at most 25% of the
   midpoint or $0.25. A strike is traded only if its quote is sound and at least 10 contracts are
   open; if the preferred strike fails, the nearest one that passes is used, and a name with no
   two is skipped with that reason. On a day a leg's quote is missing or unsound, it is valued at
   its last sound quote, and the row says "last quote". A spread that expires before the exit
   settles at intrinsic on its expiry.
4. **Sizing is a convention, stated rather than optimized.** Each cohort risks 10% of the book's
   equity, split equally across its spreads. A debit spread cannot lose more than its debit, so a
   cohort cannot lose more than 10%. Results scale with that number. Return on premium, per
   spread, is reported beside the equity curve because it does not depend on it.
5. **Replay and live are kept apart.** The rules were fixed before any options P&L was looked at.
   Cohorts opened before 2026-10-19 are replay, and later ones are live. If the rules change, the
   live date moves with them, so a rebuild can never rewrite evidence filed as live.
6. **Models come later, in their own lineage.** Options models — IV change, return on a structure
   — wait for the standing decision's reopen point and the shadow verdict. Then they get their own
   champion, gate and shadow, like the stock model.

## How the price rules were settled

The first version paid the ask and received the bid on any quote, and valued a missing contract at
intrinsic. Run over the replay on 2026-10-17, two data-quality problems made its marks meaningless,
so the rules were revised before the live date. The revision was made on the quotes, not on the
returns.

- **After-hours quotes on thin strikes are often stale or absurd.** The MA 585 put showed 2.50 bid
  and 10.00 asked with five contracts open, and 16% of contracts had no bid at all. Paying such an
  ask books a loss no trade would take. Hence the soundness and open-interest tests.
- **A strike drifts out of the captured band.** AMD fell from $594 to $529, so the sold 655 call
  moved more than 20% out of the money, which the nightly capture does not keep. Valuing that spread
  at intrinsic called a month-dated position worthless while its bought call was still bid at 12.65.
  Hence the last sound quote.
- **The exchanges' market-maker width table was measured and not used.** It accepts 41% of these
  after-hours quotes, which are wider than trading-hours markets. The combined rule above accepts
  84% of quotes that have a bid, measured on three snapshot days.

## Consequences

- An options track record starts accruing beside the share books. The replay has three cohorts:
  2026-08-12 could not trade at all, because no chains were captured on 2026-08-11 to 08-13;
  2026-09-11 closed at +1.0% of the book against +2.0% for the same names as shares; and
  2026-10-12 is still open.
- **Capturing the contracts the book holds** would remove most "last quote" marks, since a held
  strike would then never leave the snapshot. It is the natural next change to the capture.
- **Daily-expiry ETFs (SPY, QQQ, IWM) are skipped.** The capture keeps each ticker's nearest 10
  expiries, which for them is two weeks, so none reaches the next rebalance. Each skip is named.
  Widening the capture would fix this; it was offered and not chosen.
- **Fractional contracts are allowed** on paper. A real book would round, which matters most on
  expensive names.
- **Early assignment of an American short leg is ignored.** It is rare outside dividends and deep
  in-the-money calls, and the short leg here starts out of the money.
- A cohort is about a month, so it takes years, not weeks, before the book separates from noise.
  The page states that beside every number. As everywhere else, it assesses evidence; it does not
  advise.
