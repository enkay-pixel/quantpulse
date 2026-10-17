-- Each covered US company's business in one row (ADR 0007): the last twelve months of revenue,
-- profit and cash flow, the newest balance sheet, and price-based ratios where they can be trusted.
--
-- Twelve months = the latest fiscal year, plus this fiscal year so far, minus the same months a
-- year earlier: the standard trailing figure, and the only one available for cash flow, which is
-- reported year-to-date. Where no later quarter is filed (banks file revenue only yearly) it is
-- the fiscal year itself, and `through` says how old it is.
--
-- Growth compares this fiscal year so far with the same months a year earlier, or the latest
-- fiscal year with the one before when no later quarter exists.
--
-- A ratio of two lines uses figures covering the same months: twelve months against twelve months
-- when both reach the same quarter, otherwise fiscal year against fiscal year. A bank that files
-- revenue only yearly would otherwise have this year's profit divided by last year's revenue.
--
-- Market value needs a share count for the whole company. A company with several share classes
-- reports none (Alphabet) or a stale one (Berkshire, 2011), so market value, price to sales and
-- free-cash-flow yield are left empty unless a count dated within 18 months of the newest
-- statement exists. Price to earnings uses earnings per share, so it stands for those too.
with lines as (
    select * from {{ ref('fct_financial_lines') }}
),

annual as (
    select distinct on (ticker, line)
        ticker, line, period_start, period_end, value
    from lines
    where duration_days between 350 and 380
    order by ticker, line, period_end desc
),

prior_annual as (
    select distinct on (a.ticker, a.line)
        a.ticker, a.line, l.value
    from annual as a
    inner join lines as l
        on a.ticker = l.ticker and a.line = l.line
        and l.duration_days between 350 and 380
        and abs(l.period_end - (a.period_end - interval '1 year')::date) <= 7
    order by a.ticker, a.line, l.period_end desc
),

ytd as (
    select distinct on (l.ticker, l.line)
        l.ticker, l.line, l.period_end, l.duration_days, l.value
    from lines as l
    inner join annual as a on l.ticker = a.ticker and l.line = a.line
    where
        l.duration_days between 80 and 290
        and l.period_start between a.period_end and a.period_end + 7
    order by l.ticker, l.line, l.period_end desc
),

prior_ytd as (
    select distinct on (y.ticker, y.line)
        y.ticker, y.line, l.value
    from ytd as y
    inner join lines as l
        on y.ticker = l.ticker and y.line = l.line
        and abs(l.duration_days - y.duration_days) <= 7
        and abs(l.period_end - (y.period_end - interval '1 year')::date) <= 7
    order by y.ticker, y.line, l.period_end desc
),

flows as (
    select
        a.ticker,
        a.line,
        case
            when y.value is not null and p.value is not null then a.value + y.value - p.value
            else a.value
        end as ttm,
        case
            when y.value is not null and p.value is not null then y.value / nullif(p.value, 0) - 1
            else a.value / nullif(pa.value, 0) - 1
        end as growth,
        case
            when y.value is not null and p.value is not null then 'year to date'
            else 'fiscal year'
        end as growth_basis,
        case when y.value is not null and p.value is not null then y.period_end else a.period_end end
            as through,
        a.value as fiscal_year_value,
        a.period_end as fiscal_year_end
    from annual as a
    left join ytd as y on a.ticker = y.ticker and a.line = y.line
    left join prior_ytd as p on a.ticker = p.ticker and a.line = p.line
    left join prior_annual as pa on a.ticker = pa.ticker and a.line = pa.line
),

balances as (
    select distinct on (ticker, line)
        ticker, line, period_end, value
    from lines
    where duration_days = 0
    order by ticker, line, period_end desc
),

newest as (
    select ticker, max(period_end) as through, max(filed) as filed
    from lines
    where line <> 'shares_outstanding'
    group by ticker
),

closes as (
    select distinct on (ticker) ticker, close
    from (
        select ticker, date, close from {{ ref('stg_prices') }}
        union all
        select ticker, date, close from {{ ref('stg_watchlist_prices') }}
    ) as bars
    order by ticker, date desc
),

wide as (
    select
        n.ticker,
        n.through,
        n.filed,
        {%- for line in ['revenue', 'operating_income', 'net_income', 'operating_cash_flow', 'capex', 'eps_diluted'] %}
        max(f.ttm) filter (where f.line = '{{ line }}') as {{ line }}_ttm,
        max(f.through) filter (where f.line = '{{ line }}') as {{ line }}_through,
        max(f.fiscal_year_value) filter (where f.line = '{{ line }}') as {{ line }}_fy,
        max(f.fiscal_year_end) filter (where f.line = '{{ line }}') as {{ line }}_fy_end,
        {%- endfor %}
        max(f.growth) filter (where f.line = 'revenue') as revenue_growth,
        max(f.growth_basis) filter (where f.line = 'revenue') as revenue_growth_basis,
        max(b.value) filter (where b.line = 'cash') as cash,
        max(b.value) filter (where b.line = 'long_term_debt') as long_term_debt,
        max(b.value) filter (where b.line = 'equity') as equity,
        max(b.value) filter (
            where b.line = 'shares_outstanding' and b.period_end >= n.through - 548
        ) as shares_outstanding
    from newest as n
    left join flows as f on n.ticker = f.ticker
    left join balances as b on n.ticker = b.ticker
    group by n.ticker, n.through, n.filed
),

-- Free cash flow from the two cash-flow lines over the same months, as for any ratio.
cash_flow as (
    select
        *,
        case
            when operating_cash_flow_through = capex_through
                then operating_cash_flow_ttm - capex_ttm
            when operating_cash_flow_fy_end = capex_fy_end then operating_cash_flow_fy - capex_fy
        end as free_cash_flow,
        case
            when operating_cash_flow_through = capex_through then operating_cash_flow_through
            when operating_cash_flow_fy_end = capex_fy_end then operating_cash_flow_fy_end
        end as free_cash_flow_through
    from wide
)

select
    w.ticker,
    r.exchange,
    r.followed_by,
    w.through,
    w.filed,
    w.revenue_ttm,
    w.revenue_growth,
    w.revenue_growth_basis,
    w.revenue_through,
    w.operating_income_ttm,
    w.net_income_ttm,
    w.operating_cash_flow_ttm,
    w.free_cash_flow,
    w.free_cash_flow_through,
    {{ matched_ratio('w', 'operating_income', 'revenue') }} as operating_margin,
    {{ matched_ratio('w', 'net_income', 'revenue') }} as net_margin,
    case
        when w.free_cash_flow_through = w.revenue_through
            then w.free_cash_flow / nullif(w.revenue_ttm, 0)
        when w.free_cash_flow_through = w.revenue_fy_end
            then w.free_cash_flow / nullif(w.revenue_fy, 0)
    end as fcf_margin,
    w.eps_diluted_ttm as eps_ttm,
    w.cash,
    w.long_term_debt,
    w.equity,
    w.long_term_debt / nullif(w.equity, 0) as debt_to_equity,
    c.close,
    c.close * w.shares_outstanding as market_cap,
    case when w.eps_diluted_ttm > 0 then c.close / w.eps_diluted_ttm end as pe_ratio,
    c.close * w.shares_outstanding / nullif(w.revenue_ttm, 0) as price_to_sales,
    w.free_cash_flow / nullif(c.close * w.shares_outstanding, 0) as fcf_yield
from cash_flow as w
inner join {{ ref('stg_research_names') }} as r on w.ticker = r.ticker
left join closes as c on w.ticker = c.ticker
