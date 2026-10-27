# Glossary

Every term the dashboard shows and the API returns, in plain words. Generated from
[configs/glossary.yaml](../configs/glossary.yaml) by `make glossary` — edit that file,
not this one. The dashboard shows the same text when you hover a label.

## Active

`active` · Whether the ticker is still tracked. Inactive tickers keep their history but get no new
data.

## Activist holder — 13D filer

`activist_holder` · Whether any of those holders filed a 13D, which a holder must use if it may seek
to influence the company rather than hold passively.

## Against it

`against_points` · Points in the evidence that lean towards a negative view of the stock.

## Alarm level overall

`share_threshold` · The share of model inputs that must drift before the model is retrained early.

## Alarm level per input

`psi_threshold` · The shift from training above which one model input counts as drifted.

## Alerts

`alerts` · Recent pipeline failures, newest first.

## All days

`overall` · The figures over the whole history.

## As of

`as_of` · The newest day the figures cover.

## Ask

`ask` · The lowest price a seller is asking, per share. Buying costs you the ask.

## Attention vs usual

`attention_ratio` · The past week's views divided by the usual level.

**How to read it:** 1 is normal. This page calls 3 or more unusual. Attention tends to rise with a
big move rather than before it.

## Available

`available` · Whether an illustration could be built — it needs a strong enough forecast and enough
quoted strikes.

## Average daily return

`avg_daily_return` · The mean gain or loss per trading day.

## Average next-day return

`avg_next_day_return` · How the stocks in that forecast group did on the following day, on average.

**How to read it:** If the ranking works, group 1 should do best and group 5 worst.

## Average priced-in swings — average IV

`avg_iv` · The mean implied volatility across the contracts in the group.

## Average share traded per day — mean turnover

`mean_turnover` · How much of the book is replaced on an average day.

**How to read it:** Higher means more trading costs.

## Below the high — drawdown

`drawdown` · How far the book sits below its highest value so far.

## Benchmark

`benchmark` · The index fund the market's results are compared with — SPY for the NYSE, STX40.JO for
the JSE.

## Bid

`bid` · The highest price a buyer is offering, per share. Selling gets you the bid.

## Book

`variant` · Which version of the paper book — daily rebalancing, monthly rebalancing, or long only.
Each differs from the daily book in exactly one way.

## Book value — equity

`equity` · The paper book's value, starting at 1.0. 1.10 means it is up 10%.

## Books

`books` · One entry per version of the paper book.

## Bought strike

`long_strike` · The strike of the option bought, nearest the stock's price when the spread opened.

## Breakeven price

`breakeven` · The stock price at expiry where the structure neither gains nor loses.

## Buy or sell

`action` · Whether the leg is bought or sold.

## Call contracts open — call open interest

`call_oi` · How many call contracts are open on the stock.

## Call hedging expiring within a month

`call_gamma_near_share` · The share of the call hedging exposure in contracts that expire within 30
days, where it is most concentrated.

## Call hedging per 1% move — call dollar gamma

`call_gamma_usd_1pct` · The stock a dealer would buy per 1% rise if dealers had sold every listed
call — the gamma-squeeze channel.

**How to read it:** An upper bound. Public data does not show who holds which side.

## Call hedging vs normal trading

`call_gamma_share_of_adv` · The call hedging per 1% move, as a share of a normal day's dollar
trading.

**How to read it:** Higher means hedging could move the price more.

## Call or put

`option_type` · A call is the right to buy 100 shares at the strike price before expiry; a put is
the right to sell them.

## Captured on — snapshot date

`snapshot_date` · The trading day whose after-close option prices were recorded.

## Cash

`cash` · Cash and cash equivalents on the newest balance sheet.

## Cash margin — free-cash-flow margin

`fcf_margin` · Free cash flow as a share of revenue, over the same months.

**How to read it:** For banks and brokers it says little, since their operating cash moves with
their lending and trading.

## Cash yield — free-cash-flow yield

`fcf_yield` · Free cash flow as a share of market value.

**How to read it:** Roughly the cash return the business makes on its price, before any growth.

## Champions

`champions` · One entry per model that has served as champion, with its live record.

## Change since previous report

`short_change` · How shares sold short changed since the previous settlement report.

## Check

`type` · Which kind of check the condition is.

## Class

`share_class` · Which class of the company's stock the stake is in, as the filing names it. A
company with several classes, such as Berkshire's A and B shares, is filed on per class.

## Class of that stake

`top_holder_class` · Which class of stock the largest stake is in. It may not be the class this
ticker trades.

## Close

`close` · The last traded price of the day, adjusted for dividends and splits.

## Closed

`exit_date` · The day the spreads were sold — the share book's next rebalance. Empty while still
open.

## Cohorts

`cohorts` · One entry per group of spreads opened on the same day.

## Configured

`configured` · Whether the market is set up in the configuration file.

## Contracts

`contracts` · One entry per option contract in the chain.

## Contracts captured

`n_contracts` · How many option contracts were recorded for the stock in the snapshot.

## Contracts open — open interest, OI

`open_interest` · How many contracts exist and have not yet been closed or exercised.

## Cost to open — net debit

`net_debit` · What the structure costs per share — the bought leg less the sold leg. A contract is
100 shares.

## Cost to open — entry debit

`entry_debit` · What the spread cost per share — the bought option at its ask, less the sold option
at its bid. A contract is 100 shares.

## Could not trade

`skipped` · Names the share book held that the options book could not, each with the reason.

## Currency

`currency` · The currency prices are quoted in.

## Currency symbol

`display_symbol` · The symbol shown in front of prices for this market.

## Current champion

`is_current` · Whether this model is the one currently making the forecasts.

## Daily return

`daily_return` · The book's gain or loss that day, after costs.

## Daily time decay — theta, Θ

`theta` · How much value the option loses per day as expiry approaches, all else equal.

## Database reachable

`database` · Whether the service could read the database.

## Date

`date` · The trading day the figures are for.

## Days

`days` · One entry per day.

## Days left — days to expiry

`days_to_expiry` · Calendar days until the option expires.

## Days to buy back — days to cover

`days_to_cover` · Shares sold short divided by average daily volume — how many days of normal
trading it would take every short seller to buy back.

**How to read it:** Higher means a rush to buy back would move the price more.

## Days to that option's expiry

`atm_days` · Calendar days until expiry for the option used for the headline implied volatility.

## Days up — win rate

`win_rate` · The share of trading days the book made money.

**How to read it:** Above 50% means more up days than down, though not necessarily more money.

## Debt to equity

`debt_to_equity` · Long-term debt divided by shareholders' equity.

**How to read it:** Higher means more borrowed against what the owners have in. Banks borrow by
design, so compare them only with banks. Empty where equity is negative, as at McDonald's after
years of buying back its shares.

## Decided

`decided` · When the decision was taken.

## Decision

`decision` · What the promotion gate decided about a candidate model — promoted to champion, or
rejected.

## Detail

`detail` · The figures behind the item's state, in words.

## Difference from the market — tracking error

`tracking_error` · How much the book's return differs from the index's, as a yearly standard
deviation.

## Drifted

`drifted` · Whether this input's shift from training is above 0.20.

## Earnings per share, 12 months — diluted EPS

`eps_ttm` · Net profit per share over the last twelve months, counting shares that options and
convertibles would add.

## Error

`error` · The failure message.

## Error band on that — alpha standard error

`alpha_std_error_annualized` · How uncertain the yearly alpha estimate is. Roughly two of these
either side of the estimate is the plausible range.

## Experiment record — MLflow run ID

`mlflow_run_id` · The training run's identifier in MLflow, the experiment tracker, where its full
details are kept.

## Expiries

`expiries` · The expiry dates captured for the stock.

## Expiry

`expiry` · The last day the option can be used. After it, the option is worth only what it pays out.

## Figures through

`through` · The end of the newest period the company's filed figures cover.

## Filed

`filed` · The day the filing reached the SEC and became public.

## Filing

`form` · Which disclosure it is. 13D is for a holder that may seek influence, 13G for a passive one;
/A marks an amendment.

## Findings

`findings` · Measurements this project has made, each with its question and what came back.

## Followed by

`followed_by` · Who follows the name. "model" means it is in the model's universe; "watchlist" means
only the research pages follow it.

**How to read it:** A watchlist name never feeds the model, its forecasts or the paper books.

## Forecast group — signal quintile

`signal_quintile` · Each day the stocks are split into five equal groups by the model's forecast. 1
holds the strongest forecasts, 5 the weakest.

## Forecasts up to

`latest_prediction_date` · The newest trading day with model forecasts.

## Free cash flow

`free_cash_flow` · Cash from running the business less what was spent on equipment and buildings,
over twelve months or the last fiscal year.

**How to read it:** For banks and brokers it says little, since their operating cash moves with
their lending and trading.

## Free cash flow through

`free_cash_flow_through` · The end of the period the free cash flow covers.

## From

`start_date` · The first trading day included.

## Growth compares

`revenue_growth_basis` · Which periods the growth compares, this fiscal year so far or whole fiscal
years.

## Has option data

`has_options` · Whether free option chains exist for this market. Only the NYSE has them.

## High

`high` · The highest traded price of the day.

## History

`history` · One entry per capture day.

## Holder

`filer` · Who filed the stake disclosure, as named on it.

## Holders over 5% (`holders_over_5pct`)

`holders_over_5pct` · How many holders' latest Schedule 13D or 13G filing still reports 5% or more
of the stock.

## Holders over 5% (`holders`)

`holders` · The holders whose latest 13D or 13G still reports 5% or more, largest first.

## How fast that changes — gamma, Γ

`gamma` · How much the delta changes for a $1 move in the stock.

**How to read it:** Highest near the strike and close to expiry — where hedgers must trade the most.

## ID

`id` · An identifier for this item.

## In its favour

`for_points` · Points in the evidence that lean towards a positive view of the stock.

**How to read it:** Each is a reading of evidence, not a reason to buy.

## In short

`summary` · The brief in one paragraph, how many points lean each way and how many risks to raise.

## Index fund value

`benchmark_equity` · What buying the market's index fund and holding it would be worth, on the same
scale as the book.

## Inputs drifted

`share_drifted` · The share of the 13 model inputs whose shift from training is above 0.20.

**How to read it:** At 30% or more, the model is retrained early.

## Insider

`owner` · The person or entity who traded, as named on the Form 4.

## Insider trades

`trades` · Open-market trades by the company's insiders, newest first.

## Insiders bought, 90 days

`bought_usd_90d` · The dollar value of the company's stock its insiders bought on the open market in
the past 90 days, from their Form 4 filings.

**How to read it:** Buying with one's own money is rarer than selling and is the more telling of the
two. Zero is normal.

## Insiders buying

`buyers_90d` · How many different insiders bought on the open market in the past 90 days.

**How to read it:** Several insiders buying at once is read as more telling than one.

## Insiders selling

`sellers_90d` · How many different insiders sold on the open market in the past 90 days.

## Insiders sold, 90 days

`sold_usd_90d` · The dollar value of the company's stock its insiders sold on the open market in the
past 90 days.

**How to read it:** Most insider selling is routine, to diversify or pay tax, and much of it is
planned months ahead. Selling alone says little.

## Job

`job_name` · Which scheduled pipeline job failed.

## Kind

`asset_type` · Whether the ticker is a company's stock or a fund (ETF) that holds many stocks.

## Largest holder

`top_holder` · The holder with the largest stake among those over 5%, as named on its filing.

## Largest stake

`top_holder_percent` · That holder's stake as a share of the stock outstanding, as reported on its
latest filing.

## Last traded price

`last_price` · The price of the most recent trade in the contract.

## Latest close

`latest_close` · The most recent closing price.

## Latest forecast — 21-day signal

`latest_score` · The model's most recent predicted 21-day return for the stock.

## Latest insider trade

`last_trade_date` · The date of the newest open-market trade by an insider.

## Latest options capture

`latest_snapshot_date` · The newest day with captured option prices.

## Legs

`legs` · The individual contracts the structure is made of.

## Link

`url` · Where to read the full write-up.

## Live since

`live_since` · The day the market's first champion model was promoted. Everything from here is
genuinely out-of-sample.

## Live window

`live_window` · The first and last trading day of the live record.

## Long-term debt

`long_term_debt` · Borrowing due after more than a year, on the newest balance sheet.

## Low

`low` · The lowest traded price of the day.

## Market — exchange

`exchange` · Which stock exchange the figures belong to. XNYS is the New York Stock Exchange, XJSE
the Johannesburg Stock Exchange, XLON the London Stock Exchange.

## Market code

`code` · The exchange's standard four-letter code, such as XNYS or XJSE.

## Market name

`display_name` · The market's plain name, by the city it trades in, such as New York or
Johannesburg.

## Market value — market capitalization

`market_cap` · The share price times the shares outstanding.

**How to read it:** Empty where the company reports no current count for all its shares together, as
with several share classes.

## Measure

`fact` · What the line measures.

## Measurements

`metrics` · The candidate's scores on the data it was tested on, such as ranking accuracy and Sharpe
ratio.

## Memory in use

`memory_rss_bytes` · How much memory the service is using, in bytes.

## Memory limit

`memory_limit_bytes` · The most memory the service is allowed, in bytes.

## Midpoint price — mid

`mid` · Halfway between the bid and the ask — a fair-value estimate. Real trades pay more to buy and
get less to sell.

## Model input — feature

`feature` · One of the 13 measurements the model reads for each stock each day.

## Model inputs

`features` · One entry per model input, with its shift from training.

## Model inputs up to

`latest_feature_date` · The newest trading day with computed model inputs.

## Model price — theoretical value

`theo_value` · The option's value from the Black-Scholes formula using its implied volatility.

## Model version

`model_version` · Which trained model made the forecast. Each retraining that passes the gate gets a
new version number.

## Model's forecast, next month — 21-day signal (`score`)

`score` · The return the model predicts for the stock over the next 21 trading days (about a month).
Only the ranking across stocks is used — the top ones are bought and the bottom ones sold short on
paper.

**How to read it:** Higher means the model expects the stock to do better than the others. It is a
research output, not advice.

## Model's forecast, next month — 21-day signal (`signal`)

`signal` · The model's predicted return for this stock over the next 21 trading days.

**How to read it:** Higher means the model expects the stock to do better than the others.

## Monthly share book value

`share_equity` · The monthly-rebalanced share book's value on the same scale as the options book,
both starting at 1.0 on the options book's first day.

## Monthly-rebalanced book value

`horizon_equity` · The same signal traded only every 21 days instead of daily, on the same scale.

## Most it can lose — max loss

`max_loss` · The largest loss per share. For a debit spread this is what it cost.

## Most it can make — max profit

`max_profit` · The largest gain per share, if the stock moves past the sold strike by expiry.

## Moves together with the market — correlation

`correlation` · How closely the book's daily moves line up with the market's, from -1 to 1.

## Moves with the market — beta

`beta` · How much the book tends to move when the market's index moves 1%.

**How to read it:** 0 means it does not follow the market at all, which is the design here; 1 means
it moves one-for-one.

## Name

`name` · The company's name, where the universe file records it.

## Names

`names` · The names on the research watchlist, both markets.

## Net margin

`net_margin` · Net profit as a share of revenue, over the same months.

**How to read it:** One-off gains can lift it far above the operating margin, as with Alphabet in
2026.

## Net profit, 12 months

`net_income_ttm` · The bottom line after everything, including one-off gains and losses such as
revaluing stakes in other companies.

**How to read it:** It can swing on items that say little about the business. Operating profit is
the steadier read.

## Normal day's trading — average dollar volume

`adv_usd_20d` · The average dollar value traded per day over the last 20 trading days.

## Not advice

`disclaimer` · What the brief is and is not.

## Note

`note` · A remark recorded with the item.

## Open

`open` · The first traded price of the day.

## Opened

`opened` · The day the spreads were bought — a rebalance day of the monthly share book.

## Operating margin

`operating_margin` · Operating profit as a share of revenue, over the same months.

**How to read it:** Compare it with the company's own past and with similar companies, not across
industries.

## Operating profit, 12 months

`operating_income_ttm` · Revenue less the costs of running the business, before interest, tax and
one-off gains.

## Options book return

`options_return` · What the cohort's spreads made or lost, as a share of the options book's value
when they were bought.

**How to read it:** Each cohort risks a fixed tenth of the book, so this scales with that choice;
compare return on premium too.

## Outcome

`outcome` · What the evidence showed, including results later withdrawn.

## Page views

`views` · How many times the company's Wikipedia article was read that day.

## Past 3 months' return — mom_63, momentum

`mom_63` · The stock's change over the last 63 trading days.

## Past 3 months' return, ranked — mom_63_cs_rank

`mom_63_cs_rank` · Where the stock's past-3-month return ranks among all stocks in its market that
day, from 0 to 1.

## Past 3 months' swings — vol_63

`vol_63` · How much the stock's daily returns varied over the last 63 trading days.

## Past month's return — ret_21

`ret_21` · The stock's change over the last 21 trading days.

## Past month's return, ranked — ret_21_cs_rank

`ret_21_cs_rank` · Where the stock's past-month return ranks among all stocks in its market that
day, from 0 to 1.

## Past month's swings — vol_21

`vol_21` · How much the stock's daily returns varied over the last 21 trading days.

## Past week's return — ret_5

`ret_5` · The stock's change over the last 5 trading days.

## Past week's return, ranked — ret_5_cs_rank

`ret_5_cs_rank` · Where the stock's past-week return ranks among all stocks in its market that day,
from 0 to 1.

## Phase

`phase` · Replay means figures from before the model went live, which it may have been fitted on — a
description of the fit, not evidence. Live means genuinely out-of-sample.

**How to read it:** Judge only the live phase.

## Phases

`phases` · One entry per phase — the replay and the live record.

## Planned — 10b5-1

`planned` · Whether the insider said the trade was made under a plan set in advance. Blank on
filings older than that question.

## Planned in advance — 10b5-1 share

`planned_sold_share_90d` · The share of that selling, by value, the filers said was made under a
trading plan set months in advance (Rule 10b5-1).

**How to read it:** Planned sales are scheduled before the insider knows what the quarter holds, so
they say less than unplanned ones.

## Points

`points` · One entry per trading day.

## Price (`price`)

`price` · The leg's price per share, at the midpoint where quotable. A contract is 100 shares.

## Price (`trade_price`)

`trade_price` · The price per share the insider reported for the trade.

## Price divisor

`display_divisor` · What stored prices are divided by before display. The JSE stores prices in
cents, so its divisor is 100.

## Price to earnings — P/E

`pe_ratio` · The share price divided by earnings per share over the last twelve months.

**How to read it:** How many years of current profit the price pays for. Empty when earnings are
negative.

## Price to sales

`price_to_sales` · Market value divided by revenue over the last twelve months.

## Price vs 1-month average, ranked — ma_ratio_21_cs_rank

`ma_ratio_21_cs_rank` · Where the stock's distance from its 1-month average ranks among all stocks
in its market that day, from 0 to 1.

## Price vs its 1-month average — ma_ratio_21

`ma_ratio_21` · How far the price sits above or below its average over the last 21 trading days.

## Price vs its 3-month average — ma_ratio_63

`ma_ratio_63` · How far the price sits above or below its average over the last 63 trading days.

## Priced-in minus actual — volatility risk premium

`premium` · Implied volatility less what then happened, in percentage points.

**How to read it:** Positive means options were priced for more movement than arrived.

## Priced-in swings — implied volatility, IV

`implied_volatility` · How much movement the option's price assumes, as a yearly percentage.

**How to read it:** Higher means the market expects bigger moves, which makes options dearer.

## Priced-in swings — implied volatility

`implied` · What option prices assumed about the stock's movement over the next month, averaged
across stocks.

## Priced-in swings by expiry — term structure

`term_structure` · Implied volatility for each expiry, near to far.

## Priced-in swings, near the price — at-the-money IV

`atm_iv` · Implied volatility of the option closest to the current price, about a month out — the
market's headline volatility estimate for the stock.

## Prices up to

`latest_price_date` · The newest trading day with prices.

## Put contracts open — put open interest

`put_oi` · How many put contracts are open on the stock.

## Put hedging per 1% move — put dollar gamma

`put_gamma_usd_1pct` · The stock a dealer would sell per 1% fall if dealers had sold every listed
put.

**How to read it:** An upper bound, for the same reason.

## Put hedging vs normal trading

`put_gamma_share_of_adv` · The put hedging per 1% move, as a share of a normal day's dollar trading.

## Puts per call — put/call ratio

`put_call_ratio` · Open put contracts divided by open call contracts.

**How to read it:** Above 1 means more protection or bearish bets than bullish ones.

## Question

`question` · What the investigation set out to answer.

## Questions for your advisor

`questions` · Questions the evidence raises that only someone who knows your circumstances can
answer.

## Rank

`rank` · The stock's position when every stock in the market is sorted by the model's forecast. 1 is
the strongest.

## Ranking accuracy — holdout IC

`holdout_ic` · How closely the model's ordering of stocks matched the order they actually performed
in, measured on recent data it was not trained on (a rank correlation).

**How to read it:** 0 is no better than chance and 1 is perfect. For ranking stocks a month ahead,
around 0.05 is already useful.

## Recent days

`recent` · The figures over roughly the last 30 trading days.

## Recorded

`created_at` · When the row was written.

## Reopen conditions

`conditions` · The checks that would bring the decision back for review, each evaluated on the
current record.

## Return beyond the market, per day — daily alpha

`alpha_daily` · The book's average daily return left over once the part explained by the market is
removed.

## Return beyond the market, per year — alpha

`alpha_annualized` · The book's yearly return left over once the part explained by the market is
removed — the part the signal earned.

**How to read it:** Only meaningful beside its error band. A figure inside its own error band cannot
be told from zero.

## Return on what was paid — return on premium

`return_on_premium` · What a spread made or lost, as a share of what it cost to open, commissions
included.

**How to read it:** -100% is the most a spread can lose. It does not depend on how much of the book
was risked.

## Return over the index per unit of difference — information ratio

`information_ratio` · The book's return above the index, divided by how differently it moves.

**How to read it:** A market-neutral book scores badly on this by construction while the index
rises; read alpha instead.

## Return per unit of risk — Sharpe ratio

`sharpe` · Yearly return divided by yearly swings. It says how much return the book earned for the
ups and downs it went through.

**How to read it:** Above 1 is good, around 0 means no reward for the risk, below 0 lost money.
Withheld under 20 trading days, where it is noise.

## Return per unit of risk, past 3 months — rolling 63-day Sharpe

`rolling_sharpe_63d` · The Sharpe ratio over the most recent 63 trading days, recomputed each day.

## Return per unit of risk, test period — holdout Sharpe

`holdout_sharpe` · The Sharpe ratio a paper book following the model earned on the test period.

**How to read it:** Higher is better; below 0 lost money.

## Revenue growth

`revenue_growth` · Revenue this fiscal year so far against the same months a year earlier, or the
last fiscal year against the one before when no later quarter is filed.

## Revenue, 12 months — trailing twelve months

`revenue_ttm` · What the company sold over the last twelve months it has reported, from its 10-K and
10-Q filings.

**How to read it:** Where a company files revenue only yearly, this is its last fiscal year.

## Risked per cohort

`risk_budget` · The share of the options book's value each cohort spends on its spreads — the most a
cohort can lose.

## Risks to raise

`risks` · Ways a position in the stock could hurt that are worth discussing before any decision.

## Role

`role` · The insider's relation to the company, such as chief executive, director or over-10% owner.

## Rows

`rows` · One entry per stock.

## Run

`run_id` · The failed run's identifier in Dagster, the scheduler.

## Run type

`run_type` · What the training run was — a candidate (train), a promotion, a demotion, or a shadow
fitted only for comparison.

## Same names held as shares

`shares_return` · What the monthly share book, holding the same stocks over the same window, made or
lost.

## Sensitivity to priced-in swings — vega

`vega` · How much the option's price changes for a 1-point change in implied volatility.

## Served as champion

`window` · The days this model was the champion making the live forecasts.

## Share explained by the market — R²

`r_squared` · How much of the book's ups and downs the market's moves account for.

**How to read it:** Near 0 means the book's moves are its own.

## Share of the book — weight

`weight` · How much of the book's value sits in this position. Negative means a short sale.

## Share traded — turnover

`turnover` · How much of the book was bought or sold that day, as a share of its value.

## Share-equivalent — delta, Δ

`delta` · How much the option's price moves for a $1 move in the stock — roughly how many shares,
per share of the contract, it behaves like.

**How to read it:** Calls 0 to 1, puts -1 to 0. Near ±0.5 is at the money.

## Shares

`shares_traded` · How many shares changed hands in the trade.

## Shares held

`shares_held` · The shares the holder reported owning.

## Shares sold short — short interest

`shares_short` · Shares borrowed and sold, not yet bought back. Short sellers lose as the price
rises.

## Shift from training — PSI, population stability index

`psi` · How far this input's recent values have moved away from the values the model was trained on.

**How to read it:** Under 0.10 is no real change, 0.10–0.20 a moderate shift, above 0.20 counts as
drifted.

## Short interest known from

`short_known_from` · When the short-interest figure first became available here.

## Short interest settled

`short_settlement_date` · The date the short-interest figure describes. It is published a week or
two later.

## Short, share of tradable shares — short % of float

`short_pct_float` · Shares sold short as a share of the shares available to trade.

**How to read it:** 10–20% is commonly called elevated and 20% or more high. GameStop's was above
100% in January 2021.

## Side

`side` · Long means bought, expecting a rise. Short means sold borrowed shares, expecting a fall.

## Signal strength — alpha t-statistic

`alpha_t_stat` · The alpha divided by its error band.

**How to read it:** Beyond about ±2 the result is distinguishable from luck; inside it, it is not.

## Sold strike

`short_strike` · The strike of the option sold, about 10% further out, which caps both the cost and
the payoff.

## Spreads (`spreads`)

`spreads` · How many option spreads the cohort holds.

## Spreads (`positions`)

`positions` · One entry per name in the newest cohort, including any that could not be traded.

## Stake

`percent` · The holding as a share of the stock outstanding, as the filer reported it.

## Standing decisions

`decisions` · Decisions already taken, each with the conditions named in advance that would reopen
it.

## State

`state` · For a decision — standing, reopened (a condition was met), watched elsewhere, or can't be
checked here. For a condition — armed, fired or unknown.

## Status

`status` · The item's state. For the service, whether it is working; for an options-book spread,
open, closed, or skipped because it could not be traded.

## Stock price — spot

`spot` · The stock's price when the option chain was captured, after the close.

## Stock price — underlying close

`underlying_close` · The closing price of the stock an option is written on, on the snapshot day.

## Stocks

`tickers` · How many stocks the day's average covers.

## Strike price — strike

`strike` · The price at which the option lets its holder buy (call) or sell (put) the stock.

## Strikes

`strikes` · One entry per strike price, with the hedging exposure at it.

## Structure

`structure` · The kind of option position, such as a bull call spread.

## Swings that then happened — realized volatility

`realized` · How much the stocks actually moved over the 21 trading days that followed, on the same
yearly scale.

## The evidence

`facts` · Each measure the brief draws on, with its value and how to read it.

## Ticker

`ticker` · The stock's symbol on its exchange. JSE symbols end in .JO.

## Time zone

`timezone` · The exchange's local time zone, which decides when its trading day ends.

## Title

`title` · A short name for the item.

## To

`end_date` · The last trading day included.

## Total return

`total_return` · The book's gain or loss over the whole period.

## Trade

`trade` · Whether the insider bought or sold on the open market.

## Traded on

`transaction_date` · The day the insider's trade took place.

## Trades every — rebalance interval

`rebalance_days` · How many trading days the book holds its positions before re-forming them.

## Trading activity vs usual — volume_z_21

`volume_z_21` · How unusual today's trading volume is compared with the last 21 days.

## Trading days

`n_days` · How many trading days the figures cover.

## Trained

`trained_at` · When the model was fitted.

## Usual views a day — 90-day median

`baseline_90d` · The middle value of daily page views over the 90 days before that week.

## Value (`value_usd`)

`value_usd` · Shares times price, in US dollars.

## Value (`value`)

`value` · The measure's value for this stock.

## Value now

`mark_value` · What closing the spread would raise per share — the bought option at its bid, less
buying back the sold one at its ask.

## Valued from

`mark_basis` · Quote means that day's bid and ask. Last quote means one option's quote that day was
missing or unreliable (no bid, or far too wide), so its last sound quote stands in. Intrinsic means
no sound quote was ever seen, so it is valued at what it would pay out now. Settled means it
expired.

## Valued on

`mark_date` · The day the value was taken.

## View

`direction` · Bullish expects a rise, bearish a fall, neutral no clear view.

## Views a day, past week

`views_7d` · The average daily page views over the last 7 days.

## Volume

`volume` · How many shares (or option contracts) traded that day.

## What this cannot tell you

`limits` · The gaps and delays in the evidence, and what no public data can know.

## When

`timestamp` · When it happened.

## Why

`rationale` · How the model's forecast maps to the structure, in words.

## Why it is followed

`why` · One sentence, from the watchlist file, on why the name is on the watchlist.

## Wikipedia article (`article`)

`article` · The article whose page views stand for public attention to the company.

## Wikipedia article (`wikipedia`)

`wikipedia` · The article whose page views stand for public attention to the name, if it has one.

## Worst fall — max drawdown

`max_drawdown` · The largest drop from a high point to a later low, as a share of the high.

**How to read it:** Closer to 0 is better.

## Worst fall, test period — holdout max drawdown

`holdout_max_drawdown` · The largest peak-to-trough loss of that paper book over the test period.

**How to read it:** Closer to 0 is better.

## Worth exercising now — in the money

`in_the_money` · Whether exercising the option right now would pay something — a call when the price
is above the strike, a put when below.

## Yearly cost of trading — cost drag

`annualized_cost_drag` · How much return trading costs take away per year.

**How to read it:** Lower is better.

## Yearly return — annualized return

`annualized_return` · The total return scaled to a one-year rate.

**How to read it:** Over short periods this exaggerates — a few weeks scaled up to a year is not a
rate anything has sustained.

## Yearly return before costs — annualized gross return

`annualized_gross_return` · The yearly return before trading costs are taken off.

## Yearly swings — annualized volatility

`annualized_volatility` · How much the book's value moves around, as a yearly standard deviation.

**How to read it:** Lower is calmer.

## Yesterday's return — ret_1

`ret_1` · The stock's change over the last trading day.
