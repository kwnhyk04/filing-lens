from typing import Literal

FiscalPeriod = Literal["FY", "Q1", "Q2", "Q3", "Q4"]

FISCAL_PERIOD_VALUES: set[FiscalPeriod] = {
    "FY",
    "Q1",
    "Q2",
    "Q3",
    "Q4",
}


def check_fiscal_period(value: str) -> FiscalPeriod:
    if value in FISCAL_PERIOD_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {FISCAL_PERIOD_VALUES!r}")
