from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.calculation import Calculation


T = TypeVar("T", bound="Citation")


@_attrs_define
class Citation:
    """Exactly one source: chunk_id for filing text, fact_id for an XBRL fact, calculation for
    arithmetic on two cited facts (its quote holds the values, difference and change).

        Attributes:
            chunk_id (None | str):
            fact_id (None | str):
            calculation (Calculation | None):
            quote (str):
            filing_url (str):
    """

    chunk_id: None | str
    fact_id: None | str
    calculation: Calculation | None
    quote: str
    filing_url: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.calculation import Calculation  # noqa: PLC0415

        chunk_id: None | str
        chunk_id = self.chunk_id

        fact_id: None | str
        fact_id = self.fact_id

        calculation: dict[str, Any] | None
        if isinstance(self.calculation, Calculation):
            calculation = self.calculation.to_dict()
        else:
            calculation = self.calculation

        quote = self.quote

        filing_url = self.filing_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "chunk_id": chunk_id,
                "fact_id": fact_id,
                "calculation": calculation,
                "quote": quote,
                "filing_url": filing_url,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.calculation import Calculation  # noqa: PLC0415

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

        def _parse_calculation(data: object) -> Calculation | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                calculation_type_0 = Calculation.from_dict(data)

                return calculation_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(Calculation | None, data)

        calculation = _parse_calculation(d.pop("calculation"))

        quote = d.pop("quote")

        filing_url = d.pop("filing_url")

        citation = cls(
            chunk_id=chunk_id,
            fact_id=fact_id,
            calculation=calculation,
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
