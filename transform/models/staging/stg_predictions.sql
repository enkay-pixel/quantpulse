-- One score per (ticker, date): when several model versions scored the same date,
-- keep the newest version's score.
with ranked as (
    select
        ticker,
        date,
        model_version,
        score,
        row_number() over (
            partition by ticker, date
            order by model_version desc
        ) as version_rank
    from {{ source('market', 'predictions') }}
)

select
    ticker,
    date,
    model_version,
    score
from ranked
where version_rank = 1
