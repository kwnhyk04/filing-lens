from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.citation import Citation
    from ..models.figure_check import FigureCheck
    from ..models.reading import Reading
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
        reading (None | Reading): How the router read the question; null if it was not read.
        checks (list[FigureCheck]): Each amount in the answer with the cited source that holds it. Validation removes a
            sentence with an amount no cited source holds, so every listed amount matched.
    """

    answer: str
    citations: list[Citation]
    degraded: bool
    usage: Usage
    warnings: list[str]
    reading: None | Reading
    checks: list[FigureCheck]
    refused: bool = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.reading import Reading  # noqa: PLC0415

        answer = self.answer

        citations = []
        for citations_item_data in self.citations:
            citations_item = citations_item_data.to_dict()
            citations.append(citations_item)

        degraded = self.degraded

        usage = self.usage.to_dict()

        refused = self.refused

        warnings = self.warnings

        reading: dict[str, Any] | None
        if isinstance(self.reading, Reading):
            reading = self.reading.to_dict()
        else:
            reading = self.reading

        checks = []
        for checks_item_data in self.checks:
            checks_item = checks_item_data.to_dict()
            checks.append(checks_item)

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
                "reading": reading,
                "checks": checks,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.citation import Citation  # noqa: PLC0415
        from ..models.figure_check import FigureCheck  # noqa: PLC0415
        from ..models.reading import Reading  # noqa: PLC0415
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

        def _parse_reading(data: object) -> None | Reading:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                reading_type_0 = Reading.from_dict(data)

                return reading_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Reading, data)

        reading = _parse_reading(d.pop("reading"))

        checks = []
        _checks = d.pop("checks")
        for checks_item_data in _checks:
            checks_item = FigureCheck.from_dict(checks_item_data)

            checks.append(checks_item)

        answer = cls(
            answer=answer,
            citations=citations,
            degraded=degraded,
            usage=usage,
            refused=refused,
            warnings=warnings,
            reading=reading,
            checks=checks,
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
