from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AnswerRequest")


@_attrs_define
class AnswerRequest:
    """
    Attributes:
        question (str):
        company_ids (list[int] | None | Unset): Only use these companies (CIKs).
        fiscal_years (list[int] | None | Unset):
    """

    question: str
    company_ids: list[int] | None | Unset = UNSET
    fiscal_years: list[int] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        question = self.question

        company_ids: list[int] | None | Unset
        if isinstance(self.company_ids, Unset):
            company_ids = UNSET
        elif isinstance(self.company_ids, list):
            company_ids = self.company_ids

        else:
            company_ids = self.company_ids

        fiscal_years: list[int] | None | Unset
        if isinstance(self.fiscal_years, Unset):
            fiscal_years = UNSET
        elif isinstance(self.fiscal_years, list):
            fiscal_years = self.fiscal_years

        else:
            fiscal_years = self.fiscal_years

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "question": question,
            }
        )
        if company_ids is not UNSET:
            field_dict["company_ids"] = company_ids
        if fiscal_years is not UNSET:
            field_dict["fiscal_years"] = fiscal_years

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        question = d.pop("question")

        def _parse_company_ids(data: object) -> list[int] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                company_ids_type_0 = cast(list[int], data)

                return company_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[int] | None | Unset, data)

        company_ids = _parse_company_ids(d.pop("company_ids", UNSET))

        def _parse_fiscal_years(data: object) -> list[int] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                fiscal_years_type_0 = cast(list[int], data)

                return fiscal_years_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[int] | None | Unset, data)

        fiscal_years = _parse_fiscal_years(d.pop("fiscal_years", UNSET))

        answer_request = cls(
            question=question,
            company_ids=company_ids,
            fiscal_years=fiscal_years,
        )

        answer_request.additional_properties = d
        return answer_request

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
