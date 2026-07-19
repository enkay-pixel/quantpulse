select
    ticker,
    date,
    open,
    high,
    low,
    close,
    volume,
    source,
    ingested_at
from {{ source('market', 'prices') }}
