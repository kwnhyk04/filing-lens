from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="FilingCounts")


@_attrs_define
class FilingCounts:
    """How many of the job's filings are in each status.

    Attributes:
        pending (int):
        running (int):
        succeeded (int):
        failed (int):
        skipped (int): Already ingested by an earlier job.
    """

    pending: int
    running: int
    succeeded: int
    failed: int
    skipped: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        pending = self.pending

        running = self.running

        succeeded = self.succeeded

        failed = self.failed

        skipped = self.skipped

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "pending": pending,
                "running": running,
                "succeeded": succeeded,
                "failed": failed,
                "skipped": skipped,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        pending = d.pop("pending")

        running = d.pop("running")

        succeeded = d.pop("succeeded")

        failed = d.pop("failed")

        skipped = d.pop("skipped")

        filing_counts = cls(
            pending=pending,
            running=running,
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
        )

        filing_counts.additional_properties = d
        return filing_counts

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
