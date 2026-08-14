-- Paper portfolio enriched with cumulative return, running drawdown, rolling
-- risk-adjusted performance, and the honest evidence boundary.
--
-- Three phases; the distinction between the last two is what makes the record honest:
--   replay     — before that market's first champion promotion. In-sample by construction.
--   backfilled — after it, but scored by a champion promoted *later than the day itself*.
--                Also in-sample: that model was trained on data including this date.
--   live       — scored by a champion that already existed. The only honest record.
--
-- 'backfilled' exists because a gap gets filled by whatever champion is current when the
-- machine comes back. Score a fortnight's outage after a retrain and those days are the
-- new model's training data, yet they would sit in the live record looking like
-- out-of-sample evidence — flattering, and invisible. Dating the phase alone cannot catch
-- it; only comparing each day against the promotion date of the model that scored it can.
--
-- Every window partitions by exchange. Without that, one market's drawdown peak and
-- rolling Sharpe would be computed across another market's history.
with promotion as (
    select
        exchange,
        min(created_at)::date as first_live_date
    from {{ ref('stg_model_runs') }}
    where decision = 'promoted'
    group by exchange
),

-- When each champion version became current for its market. A version can appear more
-- than once (retrained, re-promoted), so the earliest promotion is the honest boundary.
version_promoted as (
    select
        exchange,
        model_version,
        min(created_at)::date as promoted_on
    from {{ ref('stg_model_runs') }}
    where decision = 'promoted'
    group by exchange, model_version
),

snapshots as (
    select
        date,
        exchange,
        equity,
        daily_return,
        gross_exposure,
        net_exposure,
        turnover,
        model_version
    from {{ ref('stg_portfolio_snapshots') }}
)

select
    s.date,
    s.exchange,
    s.equity,
    s.daily_return,
    s.gross_exposure,
    s.net_exposure,
    s.turnover,
    s.model_version,
    s.equity - 1 as cumulative_return,
    s.equity / max(s.equity) over (
        partition by s.exchange order by s.date rows unbounded preceding
    ) - 1 as drawdown,
    case
        when p.first_live_date is null or s.date < p.first_live_date then 'replay'
        -- Scored by a model that did not exist on the day it scored: in-sample, however
        -- late the clock says it is.
        when vp.promoted_on is not null and s.date < vp.promoted_on then 'backfilled'
        else 'live'
    end as phase,
    case
        when
            count(*) over w63 >= 21
            and stddev_samp(s.daily_return) over w63 > 0
            then
                avg(s.daily_return) over w63
                / stddev_samp(s.daily_return) over w63
                * sqrt(252)
    end as rolling_sharpe_63d
from snapshots as s
left join promotion as p on s.exchange = p.exchange
left join version_promoted as vp
    on s.exchange = vp.exchange and s.model_version = vp.model_version
window w63 as (
    partition by s.exchange order by s.date rows between 62 preceding and current row
)
