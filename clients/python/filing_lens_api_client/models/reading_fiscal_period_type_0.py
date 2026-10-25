from typing import Literal

ReadingFiscalPeriodType0 = Literal["FY", "Q1", "Q2", "Q3", "Q4"]

READING_FISCAL_PERIOD_TYPE_0_VALUES: set[ReadingFiscalPeriodType0] = {
    "FY",
    "Q1",
    "Q2",
    "Q3",
    "Q4",
}


def check_reading_fiscal_period_type_0(value: str) -> ReadingFiscalPeriodType0:
    if value in READING_FISCAL_PERIOD_TYPE_0_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {READING_FISCAL_PERIOD_TYPE_0_VALUES!r}")
