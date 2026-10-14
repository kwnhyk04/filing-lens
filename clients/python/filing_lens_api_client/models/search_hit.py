from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.filing import Filing


T = TypeVar("T", bound="SearchHit")


@_attrs_define
class SearchHit:
    """
    Attributes:
        chunk_id (str):
        score (float):
        text (str):
        section (str):
        filing (Filing):
    """

    chunk_id: str
    score: float
    text: str
    section: str
    filing: Filing
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        chunk_id = self.chunk_id

        score = self.score

        text = self.text

        section = self.section

        filing = self.filing.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "chunk_id": chunk_id,
                "score": score,
                "text": text,
                "section": section,
                "filing": filing,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.filing import Filing  # noqa: PLC0415

        d = dict(src_dict)
        chunk_id = d.pop("chunk_id")

        score = d.pop("score")

        text = d.pop("text")

        section = d.pop("section")

        filing = Filing.from_dict(d.pop("filing"))

        search_hit = cls(
            chunk_id=chunk_id,
            score=score,
            text=text,
            section=section,
            filing=filing,
        )

        search_hit.additional_properties = d
        return search_hit

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
