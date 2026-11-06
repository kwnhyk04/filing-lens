"""Golden v2's labels on the re-parsed chunks: exact where the text held, by overlap where it moved,
and a person's call where neither is sure. On synthetic rows, then on the frozen files."""

import hashlib
from typing import Any

from evals import carry, golden

ACCESSION = "0000320193-25-000079"
BODY = " ".join(f"word{n}" for n in range(200))


def chunk(chunk_id: str, text: str, start: int = 0) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "cik": 320193,
        "accession_number": ACCESSION,
        "item": "7",
        "char_start": start,
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "found_by": ["v1"],
        "text": text,
    }


def test_unchanged_text_carries_exactly_to_the_nearest_copy() -> None:
    old = chunk("old", BODY, 100)
    far, near = chunk("far", BODY, 9_000), chunk("near", BODY, 150)
    placed = carry.place(old, [far, near, chunk("other", "something else")])
    assert (placed.how, [t.chunk["chunk_id"] for t in placed.targets]) == ("exact", ["near"])
    assert placed.targets[0].score == 1.0


def test_a_table_split_by_the_old_parser_maps_to_its_joined_row_with_its_score() -> None:
    old = chunk("old", "Net sales\n1,234\n2,345\nCost of sales\n987\n" + BODY)
    new = chunk("new", "Net sales | 1,234 | 2,345 | 12\nCost of sales | 987 | 34\n" + BODY)
    placed = carry.place(old, [new, chunk("other", "Unrelated passage about rail cars.")])
    assert placed.how == "overlap"
    [target] = placed.targets
    assert target.chunk["chunk_id"] == "new" and target.score == 1.0


def test_a_passage_split_across_two_chunks_goes_to_review_with_both_candidates() -> None:
    words = BODY.split()
    first, second = " ".join(words[:110]), " ".join(words[90:])
    placed = carry.place(chunk("old", BODY), [chunk("a", first), chunk("b", second)])
    assert placed.how == "review"
    assert {t.chunk["chunk_id"] for t in placed.targets} == {"a", "b"}
    assert all(t.score < carry.CONFIDENT for t in placed.targets)


def test_two_chunks_that_both_hold_a_passage_are_a_review_not_a_coin_toss() -> None:
    placed = carry.place(chunk("old", BODY), [chunk("a", BODY + " x"), chunk("b", BODY + " y")])
    assert placed.how == "review"


def test_a_passage_nothing_resembles_goes_to_review_and_stays_listed() -> None:
    placed = carry.place(chunk("old", BODY), [chunk("a", "A passage about something else.")])
    assert placed.how == "review"


def pool(*candidates: dict[str, Any]) -> dict[str, Any]:
    return {"id": "x01", "candidates": list(candidates)}


def origin(*rows: tuple[str, bool]) -> dict[tuple[str, str], dict[str, Any]]:
    return {("x01", c): {"gold": g, "labeler": "claude", "why": "because"} for c, g in rows}


def test_every_label_lands_in_the_carried_rows_or_the_review_list() -> None:
    table = " ".join(f"cell{n}" for n in range(100))
    kept, moved = chunk("kept", BODY), chunk("moved", f"Net sales\n1,234\n{table}")
    new = [
        chunk("kept-new", BODY, 40),
        chunk("moved-new", f"Net sales | 1,234\n{table}", 900),
    ]
    gone = chunk("gone", "A passage the new parse has no match for at all.")
    labels = origin(("kept", True), ("moved", False), ("gone", True))
    result = carry.question(pool(kept, moved, gone), labels, [*new, chunk("z", "Unrelated.", 7)])
    assert {(r["chunk_id"], r["gold"], r["how"]) for r in result.rows} == {
        ("kept-new", True, "exact"),
        ("moved-new", False, "overlap"),
    }
    assert [r["v2_chunk_id"] for r in result.review] == ["gone"]
    assert result.review[0]["gold"] is True and result.review[0]["why"] == "because"
    assert {c["chunk_id"] for c in result.candidates} == {"kept-new", "moved-new"}
    assert {r["v2_chunk_id"] for r in result.remaps} == {"moved"}  # exact ones need no remap line


def test_two_passages_on_one_chunk_with_one_label_become_one_row() -> None:
    a, b = chunk("a", BODY[:900]), chunk("b", BODY[:900] + " tail")
    new = chunk("new", BODY[:900] + " tail more words")
    result = carry.question(pool(a, b), origin(("a", False), ("b", False)), [new])
    assert [r["chunk_id"] for r in result.rows] == ["new"]
    assert len(result.remaps) == 2 and not result.review


def test_a_gold_and_a_not_gold_passage_on_one_chunk_go_to_review_unlabeled() -> None:
    a, b = chunk("a", BODY[:900]), chunk("b", BODY[:900] + " tail")
    new = chunk("new", BODY[:900] + " tail more words")
    result = carry.question(pool(a, b), origin(("a", True), ("b", False)), [new])
    assert result.rows == [] and result.candidates == []
    assert {r["v2_chunk_id"] for r in result.review} == {"a", "b"}
    assert {r["reason"] for r in result.review} == {carry.CONFLICT}


def test_v3_changes_no_question_and_accounts_for_every_v2_label() -> None:
    v2, v3 = carry.V2, golden.ROOT
    assert v3.name == "v3"
    assert (v3 / "questions.jsonl").read_bytes() == (v2 / "questions.jsonl").read_bytes()
    pooled = sum(len(p["candidates"]) for p in golden.read_jsonl(v2 / "pools.jsonl"))
    moved = golden.read_jsonl(v3 / "remaps.jsonl") + golden.read_jsonl(v3 / "exact.jsonl")
    review = golden.read_jsonl(v3 / "review.jsonl")
    assert len({(r["id"], r["v2_chunk_id"]) for r in moved + review}) == pooled
    assert not {(r["id"], r["v2_chunk_id"]) for r in moved} & {
        (r["id"], r["v2_chunk_id"]) for r in review
    }
