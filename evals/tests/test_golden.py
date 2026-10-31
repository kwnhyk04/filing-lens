"""Golden v2's build, audit, cross-check and freeze, on synthetic rows: no database, no model."""

import asyncio
import hashlib
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any

import pytest

from evals import golden, label
from evals.calls import Cache
from evals.golden import read_jsonl, write_jsonl
from filinglens_llm.providers import Completion


def chunk(chunk_id: str, item: str, start: int, text: str) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "accession_number": "0000000001-26-000001",
        "item": item,
        "char_start": start,
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "text": text,
    }


def test_rekey_keeps_passages_by_text_and_replaces_changed_ones_by_overlap() -> None:
    kept, moved = chunk("a", "1", 0, "alpha"), chunk("b", "15", 100, "beta")
    changed = chunk("c", "15", 200, "gamma delta epsilon")  # characters 200 to 219
    new = [
        chunk("a", "1", 0, "alpha"),
        chunk("b3", "8", 500, "beta"),  # the same words again, further on
        chunk("b2", "7", 100, "beta"),
        chunk("c1", "7", 190, "x" * 12),  # 190 to 202: overlaps the start
        chunk("c2", "7", 215, "y" * 30),  # 215 to 245: overlaps the end
        chunk("d", "7", 219, "z" * 10),  # starts where the changed passage ended
    ]
    pairs, replacements = golden.rekey([kept, moved, changed], new)
    assert [(old["chunk_id"], found["chunk_id"]) for old, found in pairs] == [
        ("a", "a"),
        ("b", "b2"),
    ]
    assert [found["chunk_id"] for found in replacements] == ["c1", "c2"]


def test_v1_questions_come_frozen_into_dev_and_a_rebuild_that_differs_stops() -> None:
    frozen = [{"id": "n01", "question": "q", "facts": [1], "split": "test", "ci": True}]
    built = [{"id": "n01", "question": "q", "facts": [1]}, {"id": "n41"}]
    rows = golden.with_v1(built, frozen)
    assert rows == [frozen[0] | {"split": "dev"}, {"id": "n41", "split": "test", "ci": False}]
    with pytest.raises(SystemExit, match="n01"):
        golden.with_v1([{"id": "n01", "question": "q", "facts": [2]}], frozen)


def test_a_v1_pool_keeps_its_final_labels_and_joins_the_rebuilt_pool() -> None:
    gone = chunk("c", "14", 200, "gamma delta epsilon")
    old = {"id": "x09", "candidates": [chunk("b", "15", 100, "beta"), gone]}
    new = [chunk("b2", "7", 100, "beta"), chunk("c1", "7", 190, "x" * 12)]
    final = {("x09", "b"): True, ("x09", "c"): True}
    kept, carried = golden.carry("x09", old, new, final, human={("x09", "b")})
    assert [
        (row["chunk_id"], row["item"], row["gold"], row["labeler"], row["v1_chunk_id"])
        for row in carried
    ] == [("b2", "7", True, "human", "b")]  # c's text is gone: c1 is labeled again
    rebuilt = {
        "id": "x09",
        "candidates": [chunk("b2", "7", 100, "beta") | {"found_by": ["vector"]}],
    }
    pooled = golden.merged(rebuilt, kept)
    assert {c["chunk_id"]: c["found_by"] for c in pooled["candidates"]} == {
        "b2": ["v1", "vector"],
        "c1": ["v1 changed"],
    }


def test_a_v1_gold_passage_with_no_successor_stops_the_build() -> None:
    old = {"id": "x19", "candidates": [chunk("p", "8", 100, "a pointer to the statements")]}
    new = [chunk("q", "8", 500, "elsewhere")]  # nothing holds or overlaps p's characters now
    with pytest.raises(SystemExit, match="x19"):
        golden.carry("x19", old, new, {("x19", "p"): True}, human=set())
    assert golden.carry("x19", old, new, {("x19", "p"): False}, human=set()) == ([], [])


def test_the_audit_draws_only_passages_claude_labeled_for_this_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("AI_LABELS", "AUDIT", "USER_LABELS"):
        monkeypatch.setattr(label, name, tmp_path / f"{name}.jsonl")
    pools, ai = [], []
    for q in range(30):
        qid = f"x{q:02}"
        pools.append({"id": qid, "candidates": [{"chunk_id": f"{qid}-{n}"} for n in range(6)]})
        # Passages 0 to 3 are new this version; 4 and 5 kept v1's label (carried.jsonl).
        ai += [{"id": qid, "chunk_id": f"{qid}-{n}", "gold": n == 0} for n in range(4)]
    write_jsonl(label.AI_LABELS, ai)
    sample = label.audit_sample(pools)
    assert len(sample) == 50
    assert all(int(pick["chunk_id"].rsplit("-", 1)[1]) < 4 for pick in sample)
    assert sum(pick["chunk_id"].endswith("-0") for pick in sample) >= label.AUDIT_MIN_GOLD


def use_root(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """golden's and label's files in a temporary folder."""
    for module in (golden, label):
        monkeypatch.setattr(module, "ROOT", root)
    for name in ("CARRIED", "AI_LABELS", "AUDIT", "USER_LABELS"):
        path = root / getattr(golden, name).name
        monkeypatch.setattr(golden, name, path)
        if hasattr(label, name):
            monkeypatch.setattr(label, name, path)


def claude(qid: str, n: int, gold: bool) -> dict[str, Any]:
    return {"id": qid, "chunk_id": f"{qid}-{n}", "gold": gold, "labeler": "claude", "why": "SAID"}


def blind(qid: str, n: int, gold: bool, **extra: Any) -> dict[str, Any]:
    return {"id": qid, "chunk_id": f"{qid}-{n}", "gold": gold, **extra}


def test_a_models_blind_labels_score_like_the_users_and_never_become_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_root(tmp_path, monkeypatch)
    claudes = [True, False, False, True]
    write_jsonl(golden.AI_LABELS, [claude("x01", n, gold) for n, gold in enumerate(claudes)])
    model = [True, True, False, True]  # differs on x01-1 only
    rows = [blind("x01", n, gold, labeler="fake:model") for n, gold in enumerate(model)]
    write_jsonl(golden.USER_LABELS, rows)
    stats = golden.audit_stats()
    assert stats | {"kappa": 0, "kappa_ci": 0} == {
        "blind_labeler": "fake:model",
        "passages": 4,
        "claude_gold": 2,
        "blind_gold": 3,
        "agreement": 0.75,
        "kappa": 0,
        "kappa_ci": 0,
        "disagreements": 1,
        "reviewed": 0,
        "review_as_claude": 0,
        "corrections": 0,
        "final_as_claude": 1,  # Claude's label stands: a model's label only measures
    }
    assert golden.final_labels()[0] == {("x01", f"x01-{n}"): g for n, g in enumerate(claudes)}
    write_jsonl(golden.USER_LABELS, [*rows, blind("x01", 1, True, step="review")])
    assert golden.final_labels()[0]["x01", "x01-1"] is True  # a human's call still wins


class Labeler:
    """A model that replies from a script and keeps every prompt it was sent."""

    name = "fake:model"

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.seen: list[tuple[str, str]] = []

    async def complete(
        self, system: str, user: str, *, max_tokens: int, schema: Mapping[str, Any] | None = None
    ) -> Completion:
        self.seen.append((system, user))
        return Completion(self.name, self.replies.pop(0), 10, 5, 0.5, None)

    async def stream(
        self, system: str, user: str, *, max_tokens: int
    ) -> AsyncIterator[str | Completion]:
        raise AssertionError("the cross-check never streams")
        yield ""  # an async generator, as Provider.stream is


def test_the_cross_check_labels_the_sample_blind_through_the_audit_path_and_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_root(tmp_path, monkeypatch)
    apple = {"routing": {"tickers": ["AAPL"]}}
    write_jsonl(
        tmp_path / "questions.jsonl",
        [
            {"id": "x01", "category": "textual", "question": "Where are iPhones made?"} | apple,
            {"id": "a01", "category": "unanswerable", "question": "What did Apple pay?"} | apple,
        ],
    )
    write_jsonl(
        tmp_path / "pools.jsonl",
        [
            {
                "id": "x01",
                "candidates": [chunk("x01-0", "1", 0, "Partners in Asia assemble them.")],
            },
            {"id": "a01", "candidates": [chunk("a01-0", "7", 0, "Apple bought no planet.")]},
        ],
    )
    write_jsonl(
        golden.AUDIT, [{"id": "x01", "chunk_id": "x01-0"}, {"id": "a01", "chunk_id": "a01-0"}]
    )
    write_jsonl(golden.AI_LABELS, [claude("x01", 0, False), claude("a01", 0, False)])
    model = Labeler('{"gold": true, "why": "names the partners"}', '{"gold": false, "why": "no"}')
    asyncio.run(label.cross_labels(model, Cache(tmp_path / "calls.jsonl")))
    assert [
        (r["chunk_id"], r["gold"], r["labeler"], r["why"]) for r in read_jsonl(golden.USER_LABELS)
    ] == [
        ("x01-0", True, "fake:model", "names the partners"),
        ("a01-0", False, "fake:model", "no"),
    ]
    (system, textual), (_, absent) = model.seen
    rule = "A passage is gold only if it answers the question as asked, qualifier included."
    assert rule in " ".join(system.split())  # the eval card's qualifier clause, as KEYS words it
    assert "Where are iPhones made?" in textual and "AAPL · Item 1" in textual
    assert "Partners in Asia assemble them." in textual and "Is this passage gold?" in textual
    assert "(absent)" in absent and "Does this passage answer the question?" in absent
    assert not any("SAID" in part for pair in model.seen for part in pair)  # never Claude's reason
    assert golden.audit_stats()["blind_labeler"] == "fake:model"
    asyncio.run(label.cross_labels(Labeler(), Cache(tmp_path / "calls.jsonl")))  # resumes: no call
    assert len(read_jsonl(golden.USER_LABELS)) == 2


def test_freeze_wants_each_label_in_its_pool_once_and_takes_a_models_cross_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_root(tmp_path, monkeypatch)
    write_jsonl(tmp_path / "questions.jsonl", [{"id": "x01", "category": "textual"}])
    pool = {"id": "x01", "candidates": [{"chunk_id": f"x01-{n}"} for n in range(3)]}
    write_jsonl(tmp_path / "pools.jsonl", [pool])
    write_jsonl(golden.CARRIED, [blind("x01", 0, True, labeler="human", **{"from": "v1"})])
    labeled = [claude("x01", 1, True), claude("x01", 2, False)]
    write_jsonl(
        golden.AUDIT, [{"id": "x01", "chunk_id": "x01-1"}, {"id": "x01", "chunk_id": "x01-2"}]
    )
    write_jsonl(golden.USER_LABELS, [blind("x01", n, False, labeler="fake:model") for n in (1, 2)])
    golden.write_manifest({"version": "v2", "status": "draft"})
    write_jsonl(golden.AI_LABELS, [*labeled, claude("x01", 9, False)])  # x01-9 is in no pool
    with pytest.raises(SystemExit, match="outside their pools: x01"):
        golden.freeze()
    write_jsonl(golden.AI_LABELS, [*labeled, claude("x01", 0, False)])  # x01-0 carries v1's label
    with pytest.raises(SystemExit, match="1 passages labeled both by v1"):
        golden.freeze()
    write_jsonl(golden.AI_LABELS, labeled)
    golden.freeze()  # the model's one disagreement needs no review: Claude's label stands
    manifest = golden.read_manifest()
    assert manifest["status"] == "frozen"
    assert manifest["gold"].startswith(
        "AI-labeled, cross-checked blind by a second model; no human spot check in v2."
    )
    assert (
        manifest["audit"]["blind_labeler"] == "fake:model" and "human_gold" not in manifest["audit"]
    )
    assert golden.final_labels()[0]["x01", "x01-1"] is True
