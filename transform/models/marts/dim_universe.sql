-- Universe members with price-coverage metadata.
select
    u.ticker,
    u.exchange,
    u.asset_type,
    u.active,
    min(p.date) as first_price_date,
    max(p.date) as last_price_date,
    count(p.date) as n_bars
from {{ ref('stg_universe') }} as u
left join {{ ref('stg_prices') }} as p
    on u.ticker = p.ticker
group by u.ticker, u.exchange, u.asset_type, u.active
