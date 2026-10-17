-- Public attention per stock and day (ADR 0007): the past week's Wikipedia views against the
-- article's usual level, for both markets.
--
-- attention_ratio = mean daily views over the 7 days ending on `date`, divided by the median
-- daily views over the 90 days before that week. The median, so one past spike does not raise
-- "usual" for three months and hide the next one. Windows are date ranges rather than row
-- counts, so a day the API did not publish shortens a window instead of stretching it. A ratio
-- needs 60 baseline days; before that it is null.
--
-- Only the newest 400 days are computed, anchored to the newest stored day rather than today so
-- the output depends on the data alone: the page reads the latest ratio and a year of history,
-- and the full record stays in page_views for anything that needs more.
with views as (
    select ticker, date, article, views
    from {{ ref('stg_page_views') }}
),

weekly as (
    select
        ticker,
        date,
        article,
        views,
        avg(views) over (
            partition by ticker order by date range between interval '6 days' preceding and current row
        ) as views_7d
    from views
),

recent as (
    select *
    from weekly
    where date >= (select max(date) from views) - 400
),

baseline as (
    select
        r.ticker,
        r.date,
        percentile_cont(0.5) within group (order by b.views) as baseline_90d,
        count(*) as baseline_days
    from recent as r
    inner join views as b
        on b.ticker = r.ticker and b.date between r.date - 96 and r.date - 7
    group by r.ticker, r.date
)

select
    r.ticker,
    u.exchange,
    u.followed_by,
    r.date,
    r.article,
    r.views,
    r.views_7d,
    case when b.baseline_days >= 60 then b.baseline_90d end as baseline_90d,
    case when b.baseline_days >= 60 then r.views_7d / nullif(b.baseline_90d, 0) end
        as attention_ratio
from recent as r
left join baseline as b on r.ticker = b.ticker and r.date = b.date
left join {{ ref('stg_research_names') }} as u on r.ticker = u.ticker
