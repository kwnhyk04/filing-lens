from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.citation import Citation
    from ..models.usage import Usage


T = TypeVar("T", bound="Answer")


@_attrs_define
class Answer:
    """
    Attributes:
        answer (str):
        citations (list[Citation]):
        degraded (bool): True when retrieval skipped the reranker after a timeout.
        usage (Usage):
        refused (bool): True when FilingLens declined: out of scope, a company it does not track, a fiscal year with no
            10-K yet, or no evidence relevant enough. `answer` says why. Default: False.
        warnings (list[str]): Validation notes, such as sentences removed because a citation or an amount did not check
            out. A streamed answer with warnings replaces the draft its deltas carried.
    """

    answer: str
    citations: list[Citation]
    degraded: bool
    usage: Usage
    warnings: list[str]
    refused: bool = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        answer = self.answer

        citations = []
        for citations_item_data in self.citations:
            citations_item = citations_item_data.to_dict()
            citations.append(citations_item)

        degraded = self.degraded

        usage = self.usage.to_dict()

        refused = self.refused

        warnings = self.warnings

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "answer": answer,
                "citations": citations,
                "degraded": degraded,
                "usage": usage,
                "refused": refused,
                "warnings": warnings,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.citation import Citation  # noqa: PLC0415
        from ..models.usage import Usage  # noqa: PLC0415

        d = dict(src_dict)
        answer = d.pop("answer")

        citations = []
        _citations = d.pop("citations")
        for citations_item_data in _citations:
            citations_item = Citation.from_dict(citations_item_data)

            citations.append(citations_item)

        degraded = d.pop("degraded")

        usage = Usage.from_dict(d.pop("usage"))

        refused = d.pop("refused")

        warnings = cast(list[str], d.pop("warnings"))

        answer = cls(
            answer=answer,
            citations=citations,
            degraded=degraded,
            usage=usage,
            refused=refused,
            warnings=warnings,
        )

        answer.additional_properties = d
        return answer

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
