# ADR 0007: A research branch beside the model — evidence for decisions, never instructions

**Status**: accepted · **Date**: 2026-10-16

## Context

Until now the platform has asked one question: does a model that ranks 50 US and 29 JSE stocks
have skill? The owner wants a second use from the same stack: to form an informed view of an
investment, including situations like GameStop in January 2021, and to take that view to a
licensed financial advisor.

That episode had three parts, and only one of them is measurable in advance from free data:

- **Fuel** — short interest above 100% of GameStop's float, and heavy buying of short-dated calls.
  Both are published or derivable: short interest from the exchanges' twice-monthly reports, call
  open interest and its gamma from the option chains this project already captures.
- **The spark** — attention arriving all at once. Hard to measure in advance, and not attempted here.
- **The mechanics** — short sellers buying to cover, and dealers who had sold calls buying stock to
  hedge as the price rose. Each pushes the price in the direction that forces more of both.

Four existing constraints apply:

- The shadow-run freeze ([ADR 0006](0006-price-data-is-filled-not-rewritten.md),
  [findings](../findings/shadow-run.md)): until its verdict is read, nothing may change what a past
  retrain trained on — features, training code, or the data and universe it used.
- [ADR 0004](0004-no-llm-question-answering-layer.md): explanations are deterministic verdict
  functions over stored figures, never a language model's prose.
- Zero cost: free data only.
- The platform is decision support. It presents evidence; it does not advise trades.

## Decision

1. **A research branch, separate from the model.** It has its own package
   (`quantpulse.research`), its own tables and its own dashboard tab. Its data is never a model
   input: not before the shadow verdict is read, and after it only through a pre-registered
   measurement ([measurement.md](../measurement.md)) showing that it adds skill. Its tables do not
   reference the model's `universe` table, so a ticker can be researched without entering the
   training universe. The first page covers the same 50 US names, because their option chains are
   already captured.
2. **Assessments, not instructions.** The branch says what the evidence shows and how strong it is:
   "short interest is high by the commonly cited bands", or "if dealers sold these calls, a 1% rise
   means buying this share of a day's volume". It never says what to buy, sell or hold, or how much,
   for anyone. The step from evidence to action belongs to a licensed advisor who knows the owner's
   circumstances, and the branch's eventual brief is written to be taken to one. "Not investment
   advice" stays on every page.
3. **Deterministic.** Every sentence comes from a tested function over stored figures, as
   everywhere else in the dashboard (ADR 0004). No language model writes opinions.
4. **Measured where possible, labelled where not.**
   - Positioning measures fuel, not timing. A loaded name can stay loaded for months.
   - Which side of an option's open interest a dealer holds is not public. Calls and puts are
     reported separately, as the exposure *if dealers were on the other side of all of it*. They are
     never netted under an assumed sign: the common convention (customers sell calls and buy puts)
     was exactly backwards for GameStop.
   - Short interest arrives with a lag. Each value is keyed by the date it was first seen, never
     back-dated to its settlement date, so history never shows a figure before it was public.
   - ETFs are reported apart from stocks. New units can be created on demand, so the squeeze
     mechanics do not apply to them the same way.

**First instance: the positioning page.**

- `short_interest`: shares short, days to cover and share of float, per settlement, from yfinance.
  Insert-only, fetched each weekday morning by `research_job`.
- `fct_positioning`: per ticker and snapshot day, the dollar gamma of calls and of puts per 1% move,
  both as a share of the 20-session average dollar volume; open interest; the near-term share of the
  call gamma; and the short interest as known that day.
- A Positioning tab, US only, because the option chains are.

**Possible extensions, each its own decision:**

- A research watchlist beyond the model's universe, such as names with high short interest. This
  needs its own chain capture.
- Attention, from the Wikipedia pageviews API (free).
- Ownership and insider activity, from SEC EDGAR filings: Forms 4, 13F and 13D/G (free).
- Fundamentals, from EDGAR's XBRL company facts (free).
- The advisor brief: one page per holding or idea, covering the evidence, the case for and against,
  the risks, and questions to ask.

## Consequences

- The owner can see, across the tracked names, where the GameStop mechanics would be loaded today —
  including that none of the large caps is anywhere near that range, which is itself a finding.
- The option chains gain a second consumer, so a poor capture night now affects two pages.
- Lagged figures resting on assumptions can be over-read. Each one is shown beside its limit
  rather than in a footnote.
- Nothing in the branch can change the live record, the paper books or the shadow run.

## Amendment, 2026-10-16: the JSE, and attention

**The JSE gets attention, not squeeze fuel.** Probed on 2026-10-16, Yahoo returns no short
interest and no option chains for JSE stocks (Naspers, FirstRand, Anglo American, Standard Bank),
so the Positioning page's squeeze measures cannot be computed for that market. The page now shows
on both markets: the squeeze sections where the data exists, and a plain statement where it does
not.

**Attention is the second instance, and the first that covers both markets.** `page_views` holds
each stock's daily English Wikipedia views (titles in `configs/attention.yaml`, 40 NYSE and 28 JSE
stocks), backfilled to 2018 and fetched each weekday morning by `research_job`. `fct_attention`
sets the past week's mean against the median of the 90 days before it.

- **Why Wikipedia.** It was the only source tried that is free, needs no key, has daily history
  and covers JSE companies:
  - Google Trends' official API is still an application-only alpha, and its unofficial client was
    archived in 2025.
  - GDELT's news-volume API answered every request from here with HTTP 429, including a single
    request after a minute's silence.
  - Reddit mention counters cover US retail chatter only, and appear to offer a current snapshot
    rather than history.
  - Stocktwits data is reachable only by scraping.
- **Titles must be canonical.** The API counts the exact title and not its redirects, so a
  redirect returns a small, plausible, wrong number. Each run resolves the titles first and skips,
  by name, any that is a redirect, a disambiguation page or missing.
- **Dual-listed companies** (BHP, Anglo American, British American Tobacco, Prosus) draw attention
  from every market they trade in, not from the JSE alone.
- **A renamed article's history starts at the rename.** Views before it stay under the old title:
  Meta Platforms from 2021-10-28, TFG Limited from 2023-11-15, Clicks from 2025-04-27. Earlier days
  are absent rather than zero, and a ratio needs 60 baseline days, so a fresh rename shows no ratio
  instead of a false spike.

**What attention showed for GameStop, on this page's own definition** (measured 2026-10-16):

| Date (2021) | Close, before the 2022 4-for-1 split | Attention ratio |
|---|---|---|
| 12 January | $19.95 | — |
| 22 January | $65.01 | 2.1× |
| 25 January | $76.79 | 4.9× |
| 27 January | $347.51 | 21× |
| 28 January | $193.60 | 42× |

Attention crossed 3× only after the price had more than tripled, and peaked with it. On this
evidence, attention confirms a move rather than warning of one. The page says so beside every
reading, and no claim that it leads returns is made without a pre-registered test.
