-- Every name the research branch covers, and who follows it: the model's universe, or the
-- watchlist (ADR 0007). The two cannot overlap — the watchlist sync refuses a universe ticker —
-- so a ticker appears once.
select
    ticker,
    exchange,
    asset_type,
    'model' as followed_by
from {{ ref('stg_universe') }}

union all

select
    ticker,
    exchange,
    asset_type,
    'watchlist' as followed_by
from {{ ref('stg_watchlist') }}
