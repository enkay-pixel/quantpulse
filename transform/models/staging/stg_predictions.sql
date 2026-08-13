-- One score per (ticker, date): when several model versions scored the same date,
-- keep the newest version's score.
--
-- Cast before ordering. `model_version` is varchar (MLflow's own type), and a string sort
-- puts '9' above '10' — so from version 10 onward "newest" would silently select an older
-- model, and the paper book would be driven by a champion that had already been replaced.
-- Retrains add a version per market per week; XJSE was at 5 on 2026-08-13, so this had
-- roughly five weeks left to run. The cast raises on a non-numeric version rather than
-- mis-ordering it, which is the right way round for a column that decides which model the
-- evidence comes from.
with ranked as (
    select
        ticker,
        date,
        model_version,
        score,
        row_number() over (
            partition by ticker, date
            order by cast(model_version as integer) desc
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
