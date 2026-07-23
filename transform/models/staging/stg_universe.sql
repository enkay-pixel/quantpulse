select
    ticker,
    name,
    asset_type,
    exchange,
    active,
    added_at
from {{ source('market', 'universe') }}
