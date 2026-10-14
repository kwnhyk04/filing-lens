from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.problem import Problem


T = TypeVar("T", bound="AnswerFailed")


@_attrs_define
class AnswerFailed:
    """
    Attributes:
        type_ (Literal['failed']):  Default: 'failed'.
        problem (Problem): RFC 9457 problem details (application/problem+json). Absent members are omitted.
    """

    problem: Problem
    type_: Literal["failed"] = "failed"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        problem = self.problem.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
                "problem": problem,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.problem import Problem  # noqa: PLC0415

        d = dict(src_dict)
        type_ = cast(Literal["failed"], d.pop("type"))
        if type_ != "failed":
            raise ValueError(f"type must match const 'failed', got '{type_}'")

        problem = Problem.from_dict(d.pop("problem"))

        answer_failed = cls(
            type_=type_,
            problem=problem,
        )

        answer_failed.additional_properties = d
        return answer_failed

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
