"""The demo export (scripts/export_demo.py): its answers and its mislabel guard, no database."""

from pathlib import Path
from typing import Any

import export_demo
import pytest

from filinglens_api.schemas import Answer

JPM = "0001628280-26-008131"
CITED = [{"id": "x99", "answer": {"citations": [{"chunk_id": "c1", "fact_id": None}]}}]


def test_each_pick_is_a_valid_answer_and_refused_records_cite_nothing() -> None:
    records = export_demo.records()
    answers = [export_demo.answer_of(records[pick]) for pick in export_demo.PICKS]
    assert [answer["refused"] for answer in answers] == [False] * 6 + [True] * 2
    for answer in answers:
        Answer.model_validate(answer)
        assert answer["usage"]["cost_usd"] == 0
        if answer["refused"]:
            assert answer["citations"] == []


def chunk(item: str) -> dict[str, Any]:
    return {"id": "c1", "section": {"item": item}, "filing": {"accessionNumber": JPM}}


def test_the_guard_stops_on_a_chunk_inside_jpms_item_15_and_names_the_record() -> None:
    with pytest.raises(SystemExit, match="x99 cites chunk c1"):
        export_demo.check_labels(CITED, [chunk("15")])


def test_the_guard_passes_a_chunk_from_jpms_item_1a() -> None:
    export_demo.check_labels(CITED, [chunk("1A")])


def test_the_snapshot_is_written_with_lf_line_endings_on_every_platform(tmp_path: Path) -> None:
    out = tmp_path / "snapshot.json"
    export_demo.write_snapshot({"answers": []}, out)
    assert out.read_bytes() == b'{\n  "answers": []\n}\n'
