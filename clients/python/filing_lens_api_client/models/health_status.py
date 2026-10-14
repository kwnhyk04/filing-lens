from typing import Literal

HealthStatus = Literal["ok", "unavailable"]

HEALTH_STATUS_VALUES: set[HealthStatus] = {
    "ok",
    "unavailable",
}


def check_health_status(value: str) -> HealthStatus:
    if value in HEALTH_STATUS_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {HEALTH_STATUS_VALUES!r}")
