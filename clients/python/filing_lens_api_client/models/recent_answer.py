from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.answer import Answer


T = TypeVar("T", bound="RecentAnswer")


@_attrs_define
class RecentAnswer:
    """A question this sign-in asked, with the completed answer it got.

    Attributes:
        id (str): Stands for the question; the same question keeps its id.
        question (str): As asked.
        answered_at (datetime.datetime):
        answer (Answer):
    """

    id: str
    question: str
    answered_at: datetime.datetime
    answer: Answer
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        question = self.question

        answered_at = self.answered_at.isoformat()

        answer = self.answer.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "question": question,
                "answered_at": answered_at,
                "answer": answer,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.answer import Answer  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        question = d.pop("question")

        answered_at = datetime.datetime.fromisoformat(d.pop("answered_at"))

        answer = Answer.from_dict(d.pop("answer"))

        recent_answer = cls(
            id=id,
            question=question,
            answered_at=answered_at,
            answer=answer,
        )

        recent_answer.additional_properties = d
        return recent_answer

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
