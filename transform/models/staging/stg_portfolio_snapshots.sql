-- Several paper books share this table (see quantpulse.ml.portfolio.BOOKS). The
-- evidence marts describe the live daily book, so pin the variant here rather than
-- letting every downstream mart double-count every book.
select
    date,
    variant,
    equity,
    daily_return,
    gross_exposure,
    net_exposure,
    turnover,
    model_version
from {{ source('market', 'portfolio_snapshots') }}
where variant = 'daily'
