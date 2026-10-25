from typing import Literal

ReadingRoute = Literal["comparison", "numeric", "out_of_scope", "textual"]

READING_ROUTE_VALUES: set[ReadingRoute] = {
    "comparison",
    "numeric",
    "out_of_scope",
    "textual",
}


def check_reading_route(value: str) -> ReadingRoute:
    if value in READING_ROUTE_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {READING_ROUTE_VALUES!r}")
