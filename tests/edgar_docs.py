# ruff: noqa: E501 — XML samples keep the long element lines of the real filings.
"""Small EDGAR documents shaped like the real ones, for the ownership tests.

Trimmed from the structure of real filings (Form 4 schema X0609, Schedule 13D/13G schema X0202),
keeping only the elements the parsers read, plus enough around them to prove they find the right
ones — the default namespace on the schedules, a derivative table on the Form 4.
"""


def form4(
    *trades: tuple[str, str, float, float | None], issuer: int, planned: str | None = "1"
) -> str:
    """A Form 4 by one officer of `issuer` (its CIK): each trade is (date, code, shares, price)."""
    rows = "".join(
        f"""
        <nonDerivativeTransaction>
            <transactionDate><value>{day}</value></transactionDate>
            <transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>
            <transactionAmounts>
                <transactionShares><value>{shares}</value></transactionShares>
                {"" if price is None else f"<transactionPricePerShare><value>{price}</value></transactionPricePerShare>"}
                <transactionAcquiredDisposedCode><value>{"A" if code in "PAM" else "D"}</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
            <postTransactionAmounts><sharesOwnedFollowingTransaction><value>1000</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
        </nonDerivativeTransaction>"""
        for day, code, shares, price in trades
    )
    flag = "" if planned is None else f"<aff10b5One>{planned}</aff10b5One>"
    return f"""<?xml version="1.0"?>
<ownershipDocument>
    <documentType>4</documentType>
    <issuer><issuerCik>{issuer:010d}</issuerCik></issuer>
    <reportingOwner>
        <reportingOwnerId><rptOwnerName>Moore Daniel William</rptOwnerName></reportingOwnerId>
        <reportingOwnerRelationship>
            <isDirector>0</isDirector><isOfficer>1</isOfficer><isTenPercentOwner>0</isTenPercentOwner>
            <officerTitle>Chief Financial Officer</officerTitle>
        </reportingOwnerRelationship>
    </reportingOwner>
    {flag}
    <nonDerivativeTable>{rows}</nonDerivativeTable>
    <derivativeTable>
        <derivativeTransaction>
            <transactionDate><value>2026-10-01</value></transactionDate>
            <transactionCoding><transactionCode>M</transactionCode></transactionCoding>
            <transactionAmounts><transactionShares><value>999999</value></transactionShares></transactionAmounts>
        </derivativeTransaction>
    </derivativeTable>
</ownershipDocument>"""


def schedule13d(
    name: str,
    percent: float,
    shares: float,
    issuer: int,
    event: str = "10/13/2026",
    share_class: str = "Class A Common Stock",
) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?><edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13D" xmlns:com="http://www.sec.gov/edgar/common">
<headerData><submissionType>SCHEDULE 13D/A</submissionType></headerData>
<formData>
  <coverPageHeader><securitiesClassTitle>{share_class}</securitiesClassTitle><dateOfEvent>{event}</dateOfEvent><issuerInfo><issuerCIK>{issuer:010d}</issuerCIK><issuerName>GameStop Corp.</issuerName></issuerInfo></coverPageHeader>
  <reportingPersons><reportingPersonInfo>
    <reportingPersonName>{name}</reportingPersonName>
    <aggregateAmountOwned>{shares}</aggregateAmountOwned>
    <percentOfClass>{percent}</percentOfClass>
  </reportingPersonInfo></reportingPersons>
</formData></edgarSubmission>"""


def schedule13g(
    name: str, percent: float, shares: float, issuer: int, event: str = "03/31/2026"
) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?><edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13g" xmlns:com="http://www.sec.gov/edgar/common">
<headerData><submissionType>SCHEDULE 13G</submissionType></headerData>
<formData>
  <coverPageHeader><eventDateRequiresFilingThisStatement>{event}</eventDateRequiresFilingThisStatement><issuerInfo><issuerCik>{issuer:010d}</issuerCik></issuerInfo></coverPageHeader>
  <coverPageHeaderReportingPersonDetails>
    <reportingPersonName>{name}</reportingPersonName>
    <reportingPersonBeneficiallyOwnedAggregateNumberOfShares>{shares}</reportingPersonBeneficiallyOwnedAggregateNumberOfShares>
    <classPercent>{percent}</classPercent>
  </coverPageHeaderReportingPersonDetails>
  <coverPageHeaderReportingPersonDetails>
    <reportingPersonName>{name} Trust Company</reportingPersonName>
    <classPercent>0.4</classPercent>
  </coverPageHeaderReportingPersonDetails>
</formData></edgarSubmission>"""
