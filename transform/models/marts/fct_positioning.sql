-- Where the GameStop mechanics would be loaded (ADR 0007): per ticker and snapshot day, the dealer
-- hedging exposure from listed options against how much the stock normally trades, and the short
-- interest known that day. It measures fuel, not timing — a loaded name can stay loaded for months.
--
-- Gamma as a share of average dollar volume is the readable form: "if dealers had sold every call,
-- a 1% rise would make them buy this share of a normal day's trading". It is an upper bound, since
-- many calls are sold by customers, not dealers.
--
-- Short interest is joined as of `known_from`, never by settlement date, so no day shows a figure
-- that was not yet public. Average volume uses the 20 sessions ending on the snapshot day, and is
-- null until a ticker has 20, or when that day's bar is missing.
--
-- Covers the model's universe and the research watchlist; `followed_by` says which.
with gamma as (
    select
        snapshot_date,
        ticker,
        max(spot) as spot,
        sum(call_oi) as call_oi,
        sum(put_oi) as put_oi,
        sum(call_gamma_usd_1pct) as call_gamma_usd_1pct,
        sum(put_gamma_usd_1pct) as put_gamma_usd_1pct,
        sum(call_gamma_usd_1pct_30d) as call_gamma_usd_1pct_30d
    from {{ ref('fct_gamma_by_strike') }}
    group by snapshot_date, ticker
),

dollar_volume as (
    select
        ticker,
        date,
        avg(close * volume) over w as adv_usd_20d,
        count(*) over w as sessions
    from (
        select ticker, date, close, volume from {{ ref('stg_prices') }}
        union all
        select ticker, date, close, volume from {{ ref('stg_watchlist_prices') }}
    ) as bars
    window w as (partition by ticker order by date rows between 19 preceding and current row)
)

select
    g.ticker,
    u.exchange,
    u.asset_type,
    u.followed_by,
    g.snapshot_date,
    g.spot,
    g.call_oi,
    g.put_oi,
    g.call_gamma_usd_1pct,
    g.put_gamma_usd_1pct,
    g.call_gamma_usd_1pct_30d / nullif(g.call_gamma_usd_1pct, 0) as call_gamma_near_share,
    case when v.sessions >= 20 then v.adv_usd_20d end as adv_usd_20d,
    g.call_gamma_usd_1pct / nullif(case when v.sessions >= 20 then v.adv_usd_20d end, 0)
        as call_gamma_share_of_adv,
    g.put_gamma_usd_1pct / nullif(case when v.sessions >= 20 then v.adv_usd_20d end, 0)
        as put_gamma_share_of_adv,
    s.settlement_date as short_settlement_date,
    s.known_from as short_known_from,
    s.shares_short,
    s.short_pct_float,
    s.days_to_cover,
    s.shares_short::float / nullif(s.shares_short_prior, 0) - 1 as short_change
from gamma as g
inner join {{ ref('stg_research_names') }} as u on g.ticker = u.ticker
left join dollar_volume as v on g.ticker = v.ticker and g.snapshot_date = v.date
left join lateral (
    select
        settlement_date,
        known_from,
        shares_short,
        shares_short_prior,
        short_pct_float,
        days_to_cover
    from {{ ref('stg_short_interest') }} as si
    where si.ticker = g.ticker and si.known_from <= g.snapshot_date
    order by si.settlement_date desc
    limit 1
) as s on true
