-- Several paper books share this table (see quantpulse.ml.portfolio.BOOKS). The evidence
-- marts describe the live daily book of each market, so the variant is pinned here rather
-- than letting every downstream mart double-count every book. Exchange is NOT pinned:
-- markets are compared side by side, books are not.
select
    date,
    exchange,
    variant,
    equity,
    daily_return,
    gross_exposure,
    net_exposure,
    turnover,
    model_version
from {{ source('market', 'portfolio_snapshots') }}
where variant = 'daily'
