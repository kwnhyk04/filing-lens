from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.answer import Answer


T = TypeVar("T", bound="AnswerCompleted")


@_attrs_define
class AnswerCompleted:
    """
    Attributes:
        type_ (Literal['completed']):  Default: 'completed'.
        answer (Answer):
    """

    answer: Answer
    type_: Literal["completed"] = "completed"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        answer = self.answer.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
                "answer": answer,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.answer import Answer  # noqa: PLC0415

        d = dict(src_dict)
        type_ = cast(Literal["completed"], d.pop("type"))
        if type_ != "completed":
            raise ValueError(f"type must match const 'completed', got '{type_}'")

        answer = Answer.from_dict(d.pop("answer"))

        answer_completed = cls(
            type_=type_,
            answer=answer,
        )

        answer_completed.additional_properties = d
        return answer_completed

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
