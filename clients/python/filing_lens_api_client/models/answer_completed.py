from __future__ import annotations

import datetime
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
        stored_at (datetime.datetime | None): When this sign-in got this answer earlier, for an answer from earlier (no
            model call made); null for a new answer.
    """

    answer: Answer
    stored_at: datetime.datetime | None
    type_: Literal["completed"] = "completed"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        answer = self.answer.to_dict()

        stored_at: None | str
        if isinstance(self.stored_at, datetime.datetime):
            stored_at = self.stored_at.isoformat()
        else:
            stored_at = self.stored_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
                "answer": answer,
                "stored_at": stored_at,
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

        def _parse_stored_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                stored_at_type_0 = datetime.datetime.fromisoformat(data)

                return stored_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        stored_at = _parse_stored_at(d.pop("stored_at"))

        answer_completed = cls(
            type_=type_,
            answer=answer,
            stored_at=stored_at,
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
