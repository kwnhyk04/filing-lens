from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.ingest_job_status import IngestJobStatus, check_ingest_job_status

if TYPE_CHECKING:
    from ..models.failure_page import FailurePage
    from ..models.filing_counts import FilingCounts
    from ..models.ingest_job_request import IngestJobRequest


T = TypeVar("T", bound="IngestJob")


@_attrs_define
class IngestJob:
    """
    Attributes:
        job_id (UUID):
        status (IngestJobStatus):
        request (IngestJobRequest):
        created_at (datetime.datetime):
        counts (FilingCounts): How many of the job's filings are in each status.
        failures (FailurePage):
    """

    job_id: UUID
    status: IngestJobStatus
    request: IngestJobRequest
    created_at: datetime.datetime
    counts: FilingCounts
    failures: FailurePage
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        job_id = str(self.job_id)

        status: str = self.status

        request = self.request.to_dict()

        created_at = self.created_at.isoformat()

        counts = self.counts.to_dict()

        failures = self.failures.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "job_id": job_id,
                "status": status,
                "request": request,
                "created_at": created_at,
                "counts": counts,
                "failures": failures,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.failure_page import FailurePage  # noqa: PLC0415
        from ..models.filing_counts import FilingCounts  # noqa: PLC0415
        from ..models.ingest_job_request import IngestJobRequest  # noqa: PLC0415

        d = dict(src_dict)
        job_id = UUID(d.pop("job_id"))

        status = check_ingest_job_status(d.pop("status"))

        request = IngestJobRequest.from_dict(d.pop("request"))

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))

        counts = FilingCounts.from_dict(d.pop("counts"))

        failures = FailurePage.from_dict(d.pop("failures"))

        ingest_job = cls(
            job_id=job_id,
            status=status,
            request=request,
            created_at=created_at,
            counts=counts,
            failures=failures,
        )

        ingest_job.additional_properties = d
        return ingest_job

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
