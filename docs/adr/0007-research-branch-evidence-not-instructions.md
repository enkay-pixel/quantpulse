# ADR 0007: A research branch beside the model — evidence for decisions, never instructions

**Status**: accepted · **Date**: 2026-10-16

**In short:** A separate research area for forming a view of an investment — short interest, option
hedging, public attention — that assesses evidence, never says what to buy or sell, and never feeds
the model.

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
- Ownership and insider activity, from SEC EDGAR filings: Forms 4, 13F and 13D/G (free). Forms 4
  and 13D/G built; see the amendment below.
- Fundamentals, from EDGAR's XBRL company facts (free). Built; see the amendment below.
- The advisor brief (built; see the amendment below): one page per holding or idea, covering the
  evidence, the case for and against,
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

## Amendment, 2026-10-17: the research watchlist

**Names beyond the model's universe get the same measures.** `configs/watchlist.yaml` lists names to
follow, each with a sentence on why. GameStop and AMC start it, as the two 2021 squeeze names to
compare against. Each name gets:

- Daily bars in `watchlist_prices`, refetched in full each evening so a split lands. Nothing trains
  on them, so the rule that fixes a trained-on day (ADR 0006) does not apply.
- A nightly chain in `watchlist_option_quotes`, in the universe's band, behind the same post-close
  gate. This was the extension's precondition: the universe's capture covers its own names only.
- Its short interest and page views, in the existing research tables.

**Kept out of the model by construction.** The model's tables keep their foreign key to the
universe, so a watchlist name cannot reach them, and the sync refuses a name that is in the
universe, so no ticker is followed twice. The capture has its own table, so the universe's
completeness checks and the options book read only the model's names. `watchlist_job` runs on its
own, weekday evenings after the close.

**Marked everywhere it appears.** The marts read both sources through one list of research names,
and every row says who follows it, the model or the watchlist. The Positioning tab tags watchlist
names and lists each with its reason.

## Amendment, 2026-10-17: ownership filings from SEC EDGAR

**Two kinds of filing, US stocks only.** Company insiders (directors, officers, over-10% owners)
must report each trade on Form 4 within two business days, and anyone holding over 5% must disclose
it on Schedule 13D (if they may seek influence) or 13G (if passive). Both come from EDGAR, free,
for the universe's US stocks and the watchlist's. A JSE company files with no US regulator, so the
section does not show there.

- **Open-market trades only count as buying and selling.** Grants, option exercises and shares
  withheld for tax are pay mechanics. Most insider selling is routine, and much of it is planned
  months ahead under Rule 10b5-1; the filer's own answer to that question is stored and shown.
  Buying with one's own money on the open market is the rarer act, and the page reads it that way.
- **Stakes come from the structured schedules only**, in use since December 2024. Older 13D/G
  filings are free text, and a percentage read from prose would be wrong too often to show. A
  holder's latest filing decides: an amendment under 5% is an exit.
- **13F fund holdings are left out.** Finding one stock's holders means reading every fund
  manager's filing each quarter, thousands of documents, for a figure 45 days stale.

**A company's filing list is not only about the company.** Probed on 2026-10-17, GameStop's list
held its own 13D on a stake in another company, and NVIDIA's held 13Gs on its stakes in others;
read naively, each company would appear as its own largest holder. A filing is kept only when the
issuer it names is the company whose list it came from. Every filing read is logged with its
outcome, so none is fetched twice.

**A stake is in one class of stock.** Checked against the live page the same day, Berkshire showed
Warren Buffett at 38.2%: his filing reports 38.2% of Class A, while the universe tracks Class B.
Each stake now carries the class its filing names, and the page and the brief show it beside the
percentage wherever a company has more than one.

**EDGAR asks every automated caller for a contact**, and refuses requests without one. The contact
is a local setting, `QUANTPULSE_SEC_CONTACT`, kept out of the repository because it is public; the
fetch fails by name when it is missing, rather than collecting refusals.

**What it showed first:** GameStop's chief executive, Ryan Cohen, bought about $130M of its stock
on the open market in the two years to October 2026: about $11M in April 2025, $22M in January
2026 and about $100M from September, while his reported stake rose from 8.3% on 3 September to
9.1% on 13 October. That is the kind of evidence this branch exists to show, beside its limit: an
insider's buying says what they chose to do, not what the stock will do.

## Amendment, 2026-10-17: the advisor brief

**One page per stock, to take to a licensed advisor.** The Brief tab, and
`GET /research/brief/{ticker}`, set out for any name in the universe or on the watchlist:

- the evidence: price history, the model's rank and its live record, short interest, option hedging,
  attention, ownership filings and any paper options position;
- the points that lean in its favour and against it;
- the risks worth raising, the questions only an advisor who knows the reader can answer, and
  what the page cannot know.

It prints on its own, without the dashboard.

**Fixed rules, not generated prose.** Each point comes from a named threshold in
`research/brief.py` — the model's top or bottom fifth, short interest over 10% of the float,
attention at three times usual, volatility over 50% a year — so the same evidence always reads the
same way, and a reader can trace every sentence to a number. ADR 0004 already rules out a language
model answering questions about the data; a brief written by one would be that, in another form.

**The boundary is tested on the text.** A unit test composes briefs from evidence that triggers
every rule, and fails if any sentence tells the reader to buy, sell or hold. The model's own
standing is always stated beside its rank: while its live record cannot be told apart from luck,
the brief says so among its limits and asks the advisor how much weight a model's view should
carry.

## Amendment, 2026-10-17: fundamentals from SEC XBRL

**Each company's own figures, US stocks only.** Every 10-K and 10-Q is filed with its statements
tagged in XBRL, and EDGAR serves a company's tagged facts as one document. `financial_facts` keeps
revenue, operating and net profit, diluted earnings per share, operating cash flow, capital
spending, and the balance sheet's assets, liabilities, equity, cash and long-term debt, from 2016.
Each figure is kept as reported, one row per filing, so a restatement sits beside the original.
`fct_fundamentals` turns them into the last twelve months per company, with margins, growth and,
where they can be trusted, price ratios. They show on a Fundamentals tab and in the advisor brief.

**Where the naive version goes wrong.** Probed on six companies the same day:

- **Companies change tags.** Apple's revenue left `Revenues` in 2018 for the contract-revenue tag;
  Alphabet's went the other way in 2025. The tag a company used most recently wins.
- **Two tags in one statement can mean different things.** Berkshire files its total revenue as
  `Revenues` and a part of it under the contract-revenue tag. Both tie on recency, and an unbroken
  tie picked either, period by period: its twelve-month revenue read $260B on one build and $323B
  on the next. The tie now goes to the broadest tag, and it reads $385B every time.
- **Twelve months needs arithmetic.** The trailing figure is the last fiscal year plus this year so
  far less the same months a year earlier, the standard method and the only one available for cash
  flow, which is filed year to date.
- **Banks tag revenue net of interest.** JPMorgan files `Revenues` only yearly, and its quarters
  under `RevenuesNetOfInterestExpense`; Wells Fargo and Goldman Sachs use only the latter. Before
  that tag was read, JPMorgan's net margin divided twelve months of profit to June by the calendar
  year's revenue. The tag is read now, and every ratio uses figures over the same months anyway —
  twelve months against twelve months, or fiscal year against fiscal year — so a line a company
  files only yearly cannot do it again.
- **Profit under other names.** Caterpillar, Mastercard and Broadcom file net profit as
  `ProfitLoss` or as profit available to common shareholders, so those are read too, the latter
  first where both are filed.
- **A dropped tag leaves stale figures.** Wells Fargo's last `Revenues` was for 2020, and its
  twelve-month revenue read 2020's beside 2026 profit. A line whose newest year ends more than 400
  days before the company's newest figures is now left out.
- **Negative equity.** McDonald's equity is below zero after years of buying back its shares, and
  debt to equity read −39. It is left empty when equity is not positive.
- **Exxon cannot be built from this source.** Its annual figures are not in EDGAR's facts document,
  only some quarters, so its row stays empty rather than guessed.
- **Net profit can mislead.** Alphabet's second quarter of 2026 shows $112B of net profit on $120B of
  revenue, from revaluing stakes it holds. The page leads with operating margin and says so.
- **Market value needs a current whole-company share count.** Alphabet reports none, and
  Berkshire's dates from 2011, both because of several share classes. Market value, price to
  sales and cash yield are left empty unless a count within 18 months of the newest statement
  exists; price to earnings uses earnings per share and stands without one.
- **The facts document can lag a filing.** Coca-Cola's 10-Q of 29 July 2026 was absent from it in
  October. A company is fetched again when it files a new statement, and a statement the document
  lacks is retried weekly, so a lagging company costs a few MB a week, not every morning.

The brief gains the twelve-month revenue and its growth, operating margin, free cash flow, price
to earnings, and cash against long-term debt. Revenue growth of 10% or more leans in a stock's
favour and a fall leans against; a loss, or negative free cash flow, is a risk to raise.
