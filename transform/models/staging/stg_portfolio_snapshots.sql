select
    date,
    equity,
    daily_return,
    gross_exposure,
    net_exposure,
    turnover,
    model_version
from {{ source('market', 'portfolio_snapshots') }}
