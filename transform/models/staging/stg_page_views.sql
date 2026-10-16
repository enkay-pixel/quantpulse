-- Daily Wikipedia views per stock article (research branch, ADR 0007). A day the API did not
-- publish is absent, not zero.
select
    ticker,
    date,
    article,
    views
from {{ source('market', 'page_views') }}
