-- Bars carry their exchange from the universe, so every downstream mart can group by
-- market without repeating the join. Inner join: a bar for a ticker that has left the
-- universe has no market to belong to.
select
    p.ticker,
    u.exchange,
    p.date,
    p.open,
    p.high,
    p.low,
    p.close,
    p.volume,
    p.source,
    p.ingested_at
from {{ source('market', 'prices') }} as p
inner join {{ source('market', 'universe') }} as u on p.ticker = u.ticker
