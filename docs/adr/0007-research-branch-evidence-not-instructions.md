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
