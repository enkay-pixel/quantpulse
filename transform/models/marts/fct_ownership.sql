-- Who inside each company is trading its stock, and who holds over 5% of it (ADR 0007): one row per
-- US stock the research pages cover, as of the newest filing stored. Anchored to that date rather
-- than today, so the output depends on the data alone.
--
-- Trades come from fct_insider_trades (open-market only) and holders from fct_large_holders. Most
-- insider selling is planned in advance or routine; buying on the open market with one's own money
-- is rarer. `planned_sold_share_90d` is the share of sales, by value, the filers said were made
-- under a plan set in advance (Rule 10b5-1), among filings that say either way.
with anchor as (
    select greatest(
        (select max(filed) from {{ ref('stg_insider_transactions') }}),
        (select max(filed) from {{ ref('stg_holder_filings') }})
    ) as as_of
),

covered as (
    select ticker from {{ ref('stg_insider_transactions') }}
    union
    select ticker from {{ ref('stg_holder_filings') }}
),

trades as (
    select
        t.ticker,
        sum(t.value_usd) filter (where t.trade = 'bought') as bought_usd_90d,
        sum(t.value_usd) filter (where t.trade = 'sold') as sold_usd_90d,
        count(distinct t.owner) filter (where t.trade = 'bought') as buyers_90d,
        count(distinct t.owner) filter (where t.trade = 'sold') as sellers_90d,
        sum(t.value_usd) filter (where t.trade = 'sold' and t.planned)
        / nullif(sum(t.value_usd) filter (where t.trade = 'sold' and t.planned is not null), 0)
            as planned_sold_share_90d,
        max(t.transaction_date) as last_trade_date
    from {{ ref('fct_insider_trades') }} as t
    cross join anchor as a
    where t.transaction_date > a.as_of - 90
    group by t.ticker
),

holders as (
    select
        ticker,
        count(*) as holders_over_5pct,
        bool_or(is_13d) as activist_holder,
        (array_agg(filer order by percent desc))[1] as top_holder,
        max(percent) as top_holder_percent
    from {{ ref('fct_large_holders') }}
    group by ticker
)

select
    c.ticker,
    r.exchange,
    r.followed_by,
    a.as_of,
    coalesce(t.bought_usd_90d, 0) as bought_usd_90d,
    coalesce(t.sold_usd_90d, 0) as sold_usd_90d,
    coalesce(t.buyers_90d, 0) as buyers_90d,
    coalesce(t.sellers_90d, 0) as sellers_90d,
    t.planned_sold_share_90d,
    t.last_trade_date,
    coalesce(h.holders_over_5pct, 0) as holders_over_5pct,
    coalesce(h.activist_holder, false) as activist_holder,
    h.top_holder,
    h.top_holder_percent
from covered as c
inner join {{ ref('stg_research_names') }} as r on c.ticker = r.ticker
cross join anchor as a
left join trades as t on c.ticker = t.ticker
left join holders as h on c.ticker = h.ticker
