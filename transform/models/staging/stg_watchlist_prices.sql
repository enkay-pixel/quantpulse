-- Daily adjusted bars for the watchlist's current names, with their market. A removed name's bars
-- stay in the table but leave this view, as a ticker that leaves the universe leaves stg_prices.
select
    p.ticker,
    w.exchange,
    p.date,
    p.open,
    p.high,
    p.low,
    p.close,
    p.volume
from {{ source('market', 'watchlist_prices') }} as p
inner join {{ source('market', 'watchlist') }} as w on p.ticker = w.ticker
