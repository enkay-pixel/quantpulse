-- One value per company, line and period (ADR 0007): the figure as most recently filed, so a
-- restatement replaces the original. Where several tags report the same line, the tag the company
-- has used most recently wins, so a company that moved from one revenue tag to another reads its
-- current one for every period both cover.
--
-- A company can file two of them in the same statement for different things: Berkshire tags its
-- total revenue `Revenues` and a part of it with the contract-revenue tag. That ties on recency,
-- and an unbroken tie picks either, period by period, mixing the total with the part. The tie goes
-- to a fixed order, the broadest tag first.
with facts as (
    select * from {{ ref('stg_financial_facts') }}
    where line is not null
),

tag_recency as (
    select ticker, line, concept, max(filed) as last_used
    from facts
    group by ticker, line, concept
),

ranked as (
    select
        f.ticker,
        f.line,
        f.concept,
        f.period_start,
        f.period_end,
        f.duration_days,
        f.value,
        f.filed,
        row_number() over (
            partition by f.ticker, f.line, f.period_end, f.duration_days
            order by
                t.last_used desc,
                case f.concept
                    when 'Revenues' then 1
                    when 'RevenueFromContractWithCustomerExcludingAssessedTax' then 2
                    when 'RevenueFromContractWithCustomerIncludingAssessedTax' then 3
                    when 'SalesRevenueNet' then 4
                    when 'RevenuesNetOfInterestExpense' then 5
                    when 'NetIncomeLoss' then 1
                    when 'NetIncomeLossAvailableToCommonStockholdersBasic' then 2
                    when 'ProfitLoss' then 3
                    when 'LongTermDebt' then 1
                    when 'LongTermDebtNoncurrent' then 2
                    when 'PaymentsToAcquirePropertyPlantAndEquipment' then 1
                    when 'PaymentsToAcquireProductiveAssets' then 2
                    else 9
                end,
                f.filed desc,
                f.accession desc
        ) as pick
    from facts as f
    inner join tag_recency as t
        on f.ticker = t.ticker and f.line = t.line and f.concept = t.concept
)

select ticker, line, concept, period_start, period_end, duration_days, value, filed
from ranked
where pick = 1
