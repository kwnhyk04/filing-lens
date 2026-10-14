from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="Citation")


@_attrs_define
class Citation:
    """Exactly one source: chunk_id for filing text, fact_id for an XBRL fact.

    Attributes:
        chunk_id (None | str):
        fact_id (None | str):
        quote (str):
        filing_url (str):
    """

    chunk_id: None | str
    fact_id: None | str
    quote: str
    filing_url: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        chunk_id: None | str
        chunk_id = self.chunk_id

        fact_id: None | str
        fact_id = self.fact_id

        quote = self.quote

        filing_url = self.filing_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "chunk_id": chunk_id,
                "fact_id": fact_id,
                "quote": quote,
                "filing_url": filing_url,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_chunk_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        chunk_id = _parse_chunk_id(d.pop("chunk_id"))

        def _parse_fact_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        fact_id = _parse_fact_id(d.pop("fact_id"))

        quote = d.pop("quote")

        filing_url = d.pop("filing_url")

        citation = cls(
            chunk_id=chunk_id,
            fact_id=fact_id,
            quote=quote,
            filing_url=filing_url,
        )

        citation.additional_properties = d
        return citation

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
