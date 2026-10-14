from typing import Literal

IngestJobStatus = Literal["failed", "partially_failed", "queued", "running", "succeeded"]

INGEST_JOB_STATUS_VALUES: set[IngestJobStatus] = {
    "failed",
    "partially_failed",
    "queued",
    "running",
    "succeeded",
}


def check_ingest_job_status(value: str) -> IngestJobStatus:
    if value in INGEST_JOB_STATUS_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {INGEST_JOB_STATUS_VALUES!r}")
