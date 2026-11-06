"""Golden v3: golden v2's questions and labels on the re-parsed corpus. v2 stays as it was.

    uv run --env-file .env python -m evals.carry   # dev database, re-parsed; no model call

The parser fix of 2026-11-06 moved nearly every chunk id, so each v2 passage gets a new home in its
filing. Unchanged text carries over exactly (place: the same sha256, the nearest copy). Changed text
goes to the one chunk that holds at least CONFIDENT of its words, ahead of any other by MARGIN, and
remaps.jsonl keeps the score. Anything else goes to review.jsonl for a person: it keeps its v2 label
there, stays out of the metrics, and nothing guesses for it. questions.jsonl is an exact copy.
"""

import asyncio
import json
import re
import shutil
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from evals.golden import (
    KEEP,
    ROOT,
    VERSION,
    _filing_chunks,  # pyright: ignore[reportPrivateUsage]
    _nearest,  # pyright: ignore[reportPrivateUsage]
    read_jsonl,
    sha256,
    write_jsonl,
    write_manifest,
)

V2 = ROOT.parent / "v2"
CONFIDENT = 0.90  # share of a passage's words one chunk must hold
MARGIN = 0.25  # ahead of the next chunk: chunks overlap by 64 tokens, about a sixth of each
LISTED = 3  # candidates a review row names
CONFLICT = "a gold and a not-gold passage landed on one chunk"
NOT_SURE = "no chunk holds it confidently"
WORD = re.compile(r"[a-z0-9$%][a-z0-9$%.,'-]*")


def words(text: str) -> Counter[str]:
    """The words of a passage, cells and lines aside: a split row and its joined row read alike."""
    return Counter(word.rstrip(".,'-") for word in WORD.findall(text.lower()))


def overlap(old: Counter[str], new: Counter[str]) -> float:
    """The share of the old passage's words that the new chunk holds."""
    return sum((old & new).values()) / max(sum(old.values()), 1)


@dataclass(frozen=True)
class Target:
    chunk: dict[str, Any]
    score: float


@dataclass(frozen=True)
class Placed:
    how: str  # exact, overlap or review
    targets: list[Target]


def place(old: dict[str, Any], chunks: list[dict[str, Any]]) -> Placed:
    """Where a passage lands among its filing's chunks."""
    same = [found for found in chunks if found["sha256"] == old["sha256"]]
    if same:
        return Placed("exact", [Target(_nearest(same, old["char_start"]), 1.0)])
    passage = words(old["text"])
    scored = sorted(
        (Target(found, overlap(passage, words(found["text"]))) for found in chunks),
        key=lambda target: (-target.score, abs(target.chunk["char_start"] - old["char_start"])),
    )
    if scored:
        best, *rest = scored
        if best.score >= CONFIDENT and (not rest or best.score - rest[0].score >= MARGIN):
            return Placed("overlap", [best])
    return Placed("review", [target for target in scored[:LISTED] if target.score > 0])


@dataclass
class Carried:
    """One question on the new chunks: its pool, its labels, and what a person must decide."""

    candidates: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    rows: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    exact: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    remaps: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    review: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])


def _review(
    qid: str, old: dict[str, Any], label: dict[str, Any], reason: str, placed: Placed
) -> dict[str, Any]:
    return {
        "id": qid,
        "v2_chunk_id": old["chunk_id"],
        "gold": label["gold"],
        "labeler": label.get("labeler"),
        "why": label.get("why"),
        "reason": reason,
        "accession_number": old["accession_number"],
        "item": old["item"],
        "text": old["text"],
        "candidates": [
            {
                "chunk_id": target.chunk["chunk_id"],
                "item": target.chunk["item"],
                "score": round(target.score, 3),
                "text": target.chunk["text"],
            }
            for target in placed.targets
        ],
    }


def question(
    pooled: dict[str, Any],
    labels: dict[tuple[str, str], dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> Carried:
    """A v2 pool on the new chunks. Two passages on one chunk keep one row when they agree; a gold
    and a not-gold passage there both go to a person, since the chunk may hold either's reading."""
    qid = pooled["id"]
    placed: dict[str, tuple[dict[str, Any], Placed]] = {}
    for old in pooled["candidates"]:
        filing = [c for c in chunks if c["accession_number"] == old["accession_number"]]
        placed[old["chunk_id"]] = (old, place(old, filing))
    golds: dict[str, set[bool]] = {}
    for old_id, (_, where) in placed.items():
        if where.how != "review":
            new_id = where.targets[0].chunk["chunk_id"]
            golds.setdefault(new_id, set()).add(labels[qid, old_id]["gold"])
    result = Carried()
    written: set[str] = set()
    for old_id, (old, where) in placed.items():
        label = labels[qid, old_id]
        if where.how == "review":
            result.review.append(_review(qid, old, label, NOT_SURE, where))
            continue
        target = where.targets[0]
        new = target.chunk
        if len(golds[new["chunk_id"]]) > 1:
            result.review.append(_review(qid, old, label, CONFLICT, where))
            continue
        score = round(target.score, 3)
        line = {
            "id": qid,
            "v2_chunk_id": old_id,
            "chunk_id": new["chunk_id"],
            "gold": label["gold"],
            "how": where.how,
            "overlap": score,
            "item": new["item"],
            "v2_item": old["item"],
            "accession_number": new["accession_number"],
        }
        (result.exact if where.how == "exact" else result.remaps).append(line)
        if new["chunk_id"] in written:
            continue
        written.add(new["chunk_id"])
        result.candidates.append(new | {"found_by": old["found_by"]})
        result.rows.append(
            {
                "id": qid,
                **{key: new[key] for key in KEEP},
                "gold": label["gold"],
                "labeler": label.get("labeler"),
                "from": "v2",
                "v2_chunk_id": old_id,
                "how": where.how,
                "overlap": score,
            }
        )
    return result


def v2_labels() -> dict[tuple[str, str], dict[str, Any]]:
    """Each v2 passage's final label with who made it; the blind model's labels only measured."""
    rows = read_jsonl(V2 / "carried.jsonl") + read_jsonl(V2 / "ai_labels.jsonl")
    humans = [r for r in read_jsonl(V2 / "labels.jsonl") if r.get("labeler", "human") == "human"]
    return {(row["id"], row["chunk_id"]): row for row in rows + humans if "gold" in row}


def report(remaps: list[dict[str, Any]], exact: int, review: list[dict[str, Any]]) -> str:
    """remap-report.md: the totals, and each remap with its overlap score."""
    gold = sum(r["gold"] for r in remaps)
    lines = [
        "# Golden v3: every remap from v2, with its overlap score",
        "",
        f"{exact} passages kept their exact text. {len(remaps)} moved by overlap ({gold} gold)."
        f" {len(review)} wait for a person (review.md; {sum(r['gold'] for r in review)} gold).",
        "A score is the share of the v2 passage's words the new chunk holds. A remap needs"
        f" {CONFIDENT} and a lead of {MARGIN} over the next chunk.",
        "",
        "| Question | Gold | v2 chunk | v3 chunk | Item | Overlap |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in sorted(remaps, key=lambda row: (row["overlap"], row["id"])):
        item = r["item"] if r["item"] == r["v2_item"] else f"{r['v2_item']} to {r['item']}"
        lines.append(
            f"| {r['id']} | {'yes' if r['gold'] else 'no'} | {r['v2_chunk_id'][:12]}"
            f" | {r['chunk_id'][:12]} | {item} | {r['overlap']:.3f} |"
        )
    return "\n".join(lines) + "\n"


def review_page(review: list[dict[str, Any]], questions: dict[str, dict[str, Any]]) -> str:
    """review.md: each passage a person must place, with its v2 text and the nearest chunks."""
    lines = [
        "# Golden v3: passages for review",
        "",
        f"{len(review)} passages. Each keeps its v2 label here and stays out of the metrics.",
        "",
    ]
    for n, row in enumerate(sorted(review, key=lambda r: (not r["gold"], r["id"])), 1):
        q = questions[row["id"]]
        label = "gold" if row["gold"] else "not gold"
        passage = " ".join(row["text"].split())[:600]
        lines += [
            f"## {n}. {row['id']} ({q['split']}), v2 label: {label}",
            "",
            f"**Question:** {q['question']}",
            "",
            f"**Why here:** {row['reason']}. **Its label's reason:** {row.get('why') or 'none'}",
            "",
            f"**v2 passage** (`{row['v2_chunk_id'][:12]}`, Item {row['item']}): {passage}",
            "",
        ]
        for c in row["candidates"]:
            text = " ".join(c["text"].split())[:300]
            lines.append(f"- `{c['chunk_id'][:12]}`, Item {c['item']}, {c['score']:.3f}: {text}")
        lines += ["", "- [ ] Decision:", ""]
    return "\n".join(lines) + "\n"


async def main() -> None:
    from filinglens_core.settings import DatabaseSettings, load_settings
    from filinglens_db import make_engine

    if (ROOT / "manifest.json").exists():
        raise SystemExit(f"Golden set {VERSION} exists; it is frozen.")
    ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(V2 / "questions.jsonl", ROOT / "questions.jsonl")
    labels = v2_labels()
    engine = make_engine(load_settings(DatabaseSettings))
    pools: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    exact: list[dict[str, Any]] = []
    remaps: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    try:
        for pooled in read_jsonl(V2 / "pools.jsonl"):
            chunks = await _filing_chunks(engine, pooled) if pooled["candidates"] else []
            carried = question(pooled, labels, chunks)
            pools.append({**pooled, "candidates": carried.candidates})
            rows += carried.rows
            exact += carried.exact
            remaps += carried.remaps
            review += carried.review
    finally:
        await engine.dispose()
    for name, content in (
        ("pools.jsonl", pools),
        ("carried.jsonl", rows),
        ("exact.jsonl", exact),
        ("remaps.jsonl", remaps),
        ("review.jsonl", review),
    ):
        write_jsonl(ROOT / name, content)
    questions = {q["id"]: q for q in read_jsonl(ROOT / "questions.jsonl")}
    pages = (
        ("remap-report.md", report(remaps, len(exact), review)),
        ("review.md", review_page(review, questions)),
    )
    for name, page in pages:
        (ROOT / name).write_text(page, encoding="utf-8", newline="\n")
    manifest = json.loads((V2 / "manifest.json").read_text(encoding="utf-8"))
    files = ("questions", "pools", "carried", "exact", "remaps", "review")
    manifest |= {
        "version": VERSION,
        "carried_from": "v2",
        "frozen_on": date.today().isoformat(),
        "pending_review": len(review),
        "gold": (
            "Golden v2's labels moved to the re-parsed chunks by code: exact text, or word overlap"
            " with its score in remaps.jsonl. No new label was made, and no human spot check, as"
            f" in v2. {len(review)} passages wait in review.jsonl and stay out of the metrics."
        ),
        "files": {f"{name}.jsonl": sha256(ROOT / f"{name}.jsonl") for name in files},
    }
    write_manifest(manifest)
    print(
        f"{len(exact)} exact, {len(remaps)} by overlap, {len(review)} for review"
        f" ({sum(r['gold'] for r in review)} gold); {len(rows)} labels on"
        f" {sum(len(p['candidates']) for p in pools)} candidates."
    )


if __name__ == "__main__":
    asyncio.run(main())
