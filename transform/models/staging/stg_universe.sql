select
    ticker,
    name,
    asset_type,
    active,
    added_at
from {{ source('market', 'universe') }}
