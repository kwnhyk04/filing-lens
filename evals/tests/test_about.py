"""The about category beside the frozen golden set: its questions, its scoring, and proof that every
existing case keeps the routing it had. No model or database is touched."""

import json
from pathlib import Path
from typing import Any

import pytest

from evals import about, harness
from evals.golden import ROOT, read_jsonl
from filinglens_api import about as answers
from filinglens_core.errors import UpstreamError
from filinglens_llm import router

QUESTIONS = read_jsonl(about.QUESTIONS)
GOLDEN = read_jsonl(ROOT / "questions.jsonl")


def test_no_golden_question_sees_the_about_routes() -> None:
    """Each sends the prompt and schema it always did, so it routes as before, every refusal case
    keeps refusing, and every cached router reply still answers its key."""
    assert len(GOLDEN) == 155
    assert [q["id"] for q in GOLDEN if router.about_wording(q["question"])] == []


def test_the_category_is_new_and_leaves_the_frozen_set_as_it_was() -> None:
    golden = harness.load_golden()  # Stop(3) when a frozen file changed
    assert not {q["id"] for q in QUESTIONS} & {q["id"] for q in golden.questions}
    assert not {q["question"] for q in QUESTIONS} & {q["question"] for q in golden.questions}
    assert about.QUESTIONS.name not in golden.manifest["files"]


def test_the_category_holds_both_intents_and_both_kinds_of_near_miss() -> None:
    kinds = {q["kind"] for q in QUESTIONS}
    assert kinds == {"app", "collection", "company", "not_held", "near_filing", "near_refusal"}
    assert len({q["id"] for q in QUESTIONS}) == len(QUESTIONS)
    routes = {q["routing"]["route"] for q in QUESTIONS if q["expect"] == "own_data"}
    assert routes == {"about_app", "about_collection"}


def test_each_question_for_an_intent_reaches_the_about_routes() -> None:
    for question in QUESTIONS:
        if question["expect"] == "own_data":
            assert router.about_wording(question["question"]), question["id"]


def test_a_refusal_that_lists_the_collection_still_reads_as_an_untracked_company() -> None:
    text = answers.not_held(["Netflix"], ["AAPL"])
    record = {"answer": text, "calls": [], "top_score": None}
    assert harness.refusal_cause(record) == "router: untracked company"


def record(outcome: str, answer: str | None = None, **fields: Any) -> dict[str, Any]:
    error = about.STOPPED if outcome == "error" else None
    return {"outcome": outcome, "error": error, "answer": answer, "route_ok": True} | fields


@pytest.mark.parametrize(
    ("given", "landed"),
    [
        (record("answered", "The collection covers 30 companies"), "own_data"),
        (record("refused", "SEC filings cannot answer", top_score=None), "refuse"),
        (record("refused", "nothing relevant enough", top_score=-4.8), "filings"),  # it searched
        (record("error"), "filings"),
        (record("error", error="UpstreamError: a provider failed"), "error"),
    ],
)
def test_a_question_lands_on_its_own_data_a_refusal_or_the_filings(
    given: dict[str, Any], landed: str
) -> None:
    assert about.landed(given) == landed


def test_the_stand_in_stops_a_filing_question_with_the_error_landed_reads() -> None:
    with pytest.raises(UpstreamError) as stopped:
        about.NoAnswerModel().stream("system", "user", max_tokens=1)
    assert f"{type(stopped.value).__name__}: {stopped.value}" == about.STOPPED  # as suite.one does


def test_a_question_is_right_when_it_lands_where_it_should_and_says_what_it_should() -> None:
    question = {"id": "b04", "expect": "own_data", "says": ["30 companies", "10-K"]}
    held = "The collection covers 30 companies: AAPL. It holds 30 filings (10-K)."
    assert about.problems(question, record("answered", held)) == []
    wrong = about.problems(question, record("answered", "The collection covers 29 companies."))
    assert wrong == ["says no 30 companies", "says no 10-K"]
    assert about.problems(question, record("refused", held)) == ["landed on refuse, not own_data"]


def test_the_routes_own_miss_counts_but_a_right_landing_is_what_decides() -> None:
    """settle sends "Do you have Apple's revenue?" to the filings even if the model said about."""
    question = {"id": "b11", "expect": "filings"}
    missed = record("error", route_ok=False)
    assert about.problems(question, missed) == []
    summary = about.summary([question], [missed])
    assert summary == {"questions": 1, "landed": 1, "router_route": 0, "says": [0, 0]}


def test_a_report_keeps_each_record_and_the_summary(tmp_path: Path) -> None:
    path = about.write_report(tmp_path, {"router": "m"}, {"questions": 1}, [{"id": "b01"}])
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert path.name.endswith("-about.json") and saved["records"] == [{"id": "b01"}]
    assert saved["summary"] == {"questions": 1} and saved["config"] == {"router": "m"}
