-- The research watchlist (ADR 0007): names the research branch follows that the model does not.
-- Synced from configs/watchlist.yaml; never joined to anything the model reads.
select
    ticker,
    exchange,
    asset_type,
    why,
    wikipedia,
    added_at
from {{ source('market', 'watchlist') }}
