from typing import Literal

FormType = Literal["10-K", "10-Q"]

FORM_TYPE_VALUES: set[FormType] = {
    "10-K",
    "10-Q",
}


def check_form_type(value: str) -> FormType:
    if value in FORM_TYPE_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {FORM_TYPE_VALUES!r}")
