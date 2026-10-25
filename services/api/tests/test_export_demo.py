"""The demo export (scripts/export_demo.py): its answers and its mislabel guard, no database."""

import json
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


SNAPSHOT = json.loads((export_demo.ROOT / "web/demo/snapshot.json").read_text("utf-8"))
CHUNKS = {c["id"]: c for c in SNAPSHOT["sources"]["chunks"]}
FACTS = {f["id"]: f for f in SNAPSHOT["sources"]["facts"]}


def test_a_saved_answer_reads_as_the_run_routed_it() -> None:
    record = export_demo.records()["c12"]
    reading = export_demo.reading_of(record["routing"], {"TSLA": "Tesla, Inc."})
    assert reading == {
        "route": "comparison",
        "companies": [{"ticker": "TSLA", "name": "Tesla, Inc."}],
        "other_companies": [],
        "fiscal_years": [2025, 2024],
        "fiscal_period": None,
        "metric": "net_income",
    }


def test_a_saved_answer_checks_each_amount_with_the_pipelines_own_check() -> None:
    records = export_demo.records()
    c12 = export_demo.answer_of(records["c12"])
    checks = export_demo.checks_of(c12, CHUNKS, FACTS)
    assert [(c["text"], c["citation"], c["source_value"]) for c in checks] == [
        ("3,794,000,000", 1, "3,794,000,000"),
        ("7,091,000,000", 2, "7,091,000,000"),
        ("$3,855 million", 3, "3,855"),
        ("$7,153 million", 3, "7,153"),
        ("$3,794 million", 4, "3,794"),
        ("$7,091 million", 4, "7,091"),
    ]
    assert export_demo.checks_of(export_demo.answer_of(records["o02"]), CHUNKS, FACTS) == []


def test_an_amount_no_cited_source_holds_stops_the_export() -> None:
    n01 = export_demo.answer_of(export_demo.records()["n01"])
    n01["answer"] = n01["answer"].replace("416,161,000,000", "999,000,000")
    with pytest.raises(SystemExit, match="does not hold"):
        export_demo.checks_of(n01, CHUNKS, FACTS)


def test_the_snapshot_is_written_with_lf_line_endings_on_every_platform(tmp_path: Path) -> None:
    out = tmp_path / "snapshot.json"
    export_demo.write_snapshot({"answers": []}, out)
    assert out.read_bytes() == b'{\n  "answers": []\n}\n'
