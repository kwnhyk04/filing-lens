from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.reading_fiscal_period_type_0 import ReadingFiscalPeriodType0, check_reading_fiscal_period_type_0
from ..models.reading_route import ReadingRoute, check_reading_route

if TYPE_CHECKING:
    from ..models.read_company import ReadCompany


T = TypeVar("T", bound="Reading")


@_attrs_define
class Reading:
    """How the router read the question; the answer used this reading.

    Attributes:
        route (ReadingRoute):
        companies (list[ReadCompany]): Tracked companies the question names.
        other_companies (list[str]): Companies the question names that FilingLens does not track.
        fiscal_years (list[int]):
        fiscal_period (None | ReadingFiscalPeriodType0):
        metric (None | str): The figure asked for, such as revenue; null if none.
    """

    route: ReadingRoute
    companies: list[ReadCompany]
    other_companies: list[str]
    fiscal_years: list[int]
    fiscal_period: None | ReadingFiscalPeriodType0
    metric: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        route: str = self.route

        companies = []
        for companies_item_data in self.companies:
            companies_item = companies_item_data.to_dict()
            companies.append(companies_item)

        other_companies = self.other_companies

        fiscal_years = self.fiscal_years

        fiscal_period: None | str
        if isinstance(self.fiscal_period, str):
            fiscal_period = self.fiscal_period
        else:
            fiscal_period = self.fiscal_period

        metric: None | str
        metric = self.metric

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "route": route,
                "companies": companies,
                "other_companies": other_companies,
                "fiscal_years": fiscal_years,
                "fiscal_period": fiscal_period,
                "metric": metric,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.read_company import ReadCompany  # noqa: PLC0415

        d = dict(src_dict)
        route = check_reading_route(d.pop("route"))

        companies = []
        _companies = d.pop("companies")
        for companies_item_data in _companies:
            companies_item = ReadCompany.from_dict(companies_item_data)

            companies.append(companies_item)

        other_companies = cast(list[str], d.pop("other_companies"))

        fiscal_years = cast(list[int], d.pop("fiscal_years"))

        def _parse_fiscal_period(data: object) -> None | ReadingFiscalPeriodType0:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                fiscal_period_type_0 = check_reading_fiscal_period_type_0(data)

                return fiscal_period_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ReadingFiscalPeriodType0, data)

        fiscal_period = _parse_fiscal_period(d.pop("fiscal_period"))

        def _parse_metric(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        metric = _parse_metric(d.pop("metric"))

        reading = cls(
            route=route,
            companies=companies,
            other_companies=other_companies,
            fiscal_years=fiscal_years,
            fiscal_period=fiscal_period,
            metric=metric,
        )

        reading.additional_properties = d
        return reading

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
