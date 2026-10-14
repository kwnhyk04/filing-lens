from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.form_type import FormType, check_form_type

T = TypeVar("T", bound="FilingFailure")


@_attrs_define
class FilingFailure:
    """
    Attributes:
        accession_number (str):
        cik (int): SEC Central Index Key.
        form_type (FormType):
        error (str):
        attempts (int):
        failed_at (datetime.datetime):
    """

    accession_number: str
    cik: int
    form_type: FormType
    error: str
    attempts: int
    failed_at: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        accession_number = self.accession_number

        cik = self.cik

        form_type: str = self.form_type

        error = self.error

        attempts = self.attempts

        failed_at = self.failed_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "accession_number": accession_number,
                "cik": cik,
                "form_type": form_type,
                "error": error,
                "attempts": attempts,
                "failed_at": failed_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        accession_number = d.pop("accession_number")

        cik = d.pop("cik")

        form_type = check_form_type(d.pop("form_type"))

        error = d.pop("error")

        attempts = d.pop("attempts")

        failed_at = datetime.datetime.fromisoformat(d.pop("failed_at"))

        filing_failure = cls(
            accession_number=accession_number,
            cik=cik,
            form_type=form_type,
            error=error,
            attempts=attempts,
            failed_at=failed_at,
        )

        filing_failure.additional_properties = d
        return filing_failure

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
