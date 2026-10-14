from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.form_type import FormType, check_form_type

T = TypeVar("T", bound="IngestJobRequest")


@_attrs_define
class IngestJobRequest:
    """
    Attributes:
        ciks (list[int]):
        form_types (list[FormType]):
        since (datetime.date): Ingest filings filed on or after this date.
    """

    ciks: list[int]
    form_types: list[FormType]
    since: datetime.date
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        ciks = self.ciks

        form_types = []
        for form_types_item_data in self.form_types:
            form_types_item: str = form_types_item_data
            form_types.append(form_types_item)

        since = self.since.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "ciks": ciks,
                "form_types": form_types,
                "since": since,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        ciks = cast(list[int], d.pop("ciks"))

        form_types = []
        _form_types = d.pop("form_types")
        for form_types_item_data in _form_types:
            form_types_item = check_form_type(form_types_item_data)

            form_types.append(form_types_item)

        since = datetime.date.fromisoformat(d.pop("since"))

        ingest_job_request = cls(
            ciks=ciks,
            form_types=form_types,
            since=since,
        )

        ingest_job_request.additional_properties = d
        return ingest_job_request

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
