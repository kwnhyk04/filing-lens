from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="FigureCheck")


@_attrs_define
class FigureCheck:
    """An amount in the answer and the cited source that holds it.

    Attributes:
        text (str): The amount as the answer writes it.
        citation (int): The citation whose source holds it, from 1.
        source_value (str): The number it matched: the fact's value, or the number as the quote has it.
    """

    text: str
    citation: int
    source_value: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        text = self.text

        citation = self.citation

        source_value = self.source_value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "text": text,
                "citation": citation,
                "source_value": source_value,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        text = d.pop("text")

        citation = d.pop("citation")

        source_value = d.pop("source_value")

        figure_check = cls(
            text=text,
            citation=citation,
            source_value=source_value,
        )

        figure_check.additional_properties = d
        return figure_check

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
