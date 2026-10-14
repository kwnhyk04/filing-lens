from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.fiscal_period import FiscalPeriod, check_fiscal_period
from ..models.form_type import FormType, check_form_type

T = TypeVar("T", bound="Filing")


@_attrs_define
class Filing:
    """
    Attributes:
        accession_number (str):
        cik (int): SEC Central Index Key.
        form_type (FormType):
        filed_on (datetime.date):
        period_end (datetime.date):
        fiscal_year (int):
        fiscal_period (FiscalPeriod):
        url (str):
    """

    accession_number: str
    cik: int
    form_type: FormType
    filed_on: datetime.date
    period_end: datetime.date
    fiscal_year: int
    fiscal_period: FiscalPeriod
    url: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        accession_number = self.accession_number

        cik = self.cik

        form_type: str = self.form_type

        filed_on = self.filed_on.isoformat()

        period_end = self.period_end.isoformat()

        fiscal_year = self.fiscal_year

        fiscal_period: str = self.fiscal_period

        url = self.url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "accession_number": accession_number,
                "cik": cik,
                "form_type": form_type,
                "filed_on": filed_on,
                "period_end": period_end,
                "fiscal_year": fiscal_year,
                "fiscal_period": fiscal_period,
                "url": url,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        accession_number = d.pop("accession_number")

        cik = d.pop("cik")

        form_type = check_form_type(d.pop("form_type"))

        filed_on = datetime.date.fromisoformat(d.pop("filed_on"))

        period_end = datetime.date.fromisoformat(d.pop("period_end"))

        fiscal_year = d.pop("fiscal_year")

        fiscal_period = check_fiscal_period(d.pop("fiscal_period"))

        url = d.pop("url")

        filing = cls(
            accession_number=accession_number,
            cik=cik,
            form_type=form_type,
            filed_on=filed_on,
            period_end=period_end,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            url=url,
        )

        filing.additional_properties = d
        return filing

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
