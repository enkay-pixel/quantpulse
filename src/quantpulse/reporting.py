"""Thresholds that decide when a statistic is fit to publish.

These live in one place because several consumers need the same answer: the dbt marts
null unreliable ratios at source, the API serves what the marts produce, and the
dashboard renders it. A guard implemented only in the UI is a guard the API does not
have — and the API is what a notebook, a second dashboard, or a future you will read.
"""

#: Minimum observations before an annualized ratio means anything. Two days of returns
#: annualize to a precise-looking Sharpe that is entirely noise; the live NYSE phase
#: showed -54.93 on three days.
MIN_DAYS_FOR_RATIOS = 20
