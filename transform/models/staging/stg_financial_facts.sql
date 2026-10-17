-- Tagged figures from 10-K and 10-Q filings (research branch, ADR 0007), each mapped to the line
-- it reports. Several tags name the same line, and companies move between them over the years,
-- so `line` is what the marts group by and `concept` stays to say which tag a figure came from.
select
    ticker,
    case
        when concept in (
            'Revenues',
            'RevenueFromContractWithCustomerExcludingAssessedTax',
            'RevenueFromContractWithCustomerIncludingAssessedTax',
            'SalesRevenueNet'
        ) then 'revenue'
        when concept = 'OperatingIncomeLoss' then 'operating_income'
        when concept = 'NetIncomeLoss' then 'net_income'
        when concept = 'EarningsPerShareDiluted' then 'eps_diluted'
        when concept = 'NetCashProvidedByUsedInOperatingActivities' then 'operating_cash_flow'
        when concept in (
            'PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets'
        ) then 'capex'
        when concept = 'Assets' then 'assets'
        when concept = 'Liabilities' then 'liabilities'
        when concept = 'StockholdersEquity' then 'equity'
        when concept = 'CashAndCashEquivalentsAtCarryingValue' then 'cash'
        when concept in ('LongTermDebtNoncurrent', 'LongTermDebt') then 'long_term_debt'
        when concept = 'EntityCommonStockSharesOutstanding' then 'shares_outstanding'
    end as line,
    concept,
    period_start,
    period_end,
    duration_days,
    value,
    form,
    filed,
    accession
from {{ source('market', 'financial_facts') }}
