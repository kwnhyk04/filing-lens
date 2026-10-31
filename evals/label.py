"""Label by hand, one passage at a time, in the terminal.

    make audit    # blind sample of Claude-labeled passages, then review of every disagreement
    make label    # every pooled passage not labeled yet (the first labeling pass)
    uv run --env-file .env python -m evals.label crosscheck  # v2: the judge labels the sample

Keys, no Enter needed in a Windows console (elsewhere type the letter and Enter): y yes, n no,
b back, x flag the question as bad, q quit (Ctrl+C too). Each key is appended to labels.jsonl at
once, so a later run resumes where this one stopped. Blind screens never show Claude's label.

crosscheck (v2, no human spot check; user, 2026-10-31): the judge model (LLM_JUDGE) takes the
blind pass in the user's place, one call per sample passage it has not labeled, shown what the
blind screen shows; each label goes to labels.jsonl with the model's name, and the run ends with
make audit's agreement numbers. A model's labels measure agreement only (golden.final_labels).
"""

import asyncio
import io
import json
import random
import re
import shutil
import sys
import textwrap
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from evals.calls import Cache, Recorded, Stop, patiently
from evals.golden import (
    AI_LABELS,
    AUDIT,
    ROOT,
    USER_LABELS,
    VERSION,
    audit_stats,
    blind_labels,
    labels,
    read_jsonl,
    read_manifest,
    write_jsonl,
)
from filinglens_llm.providers import Completion, Provider

AUDIT_SIZE, AUDIT_MIN_GOLD = 50, 20  # v2 (plan, 2026-10-26); v1 drew 60 (user, 2026-10-16)
FIRST_GUESS_S = 9.0  # seconds per passage until this run has its own pace
IDLE_S = 120.0  # a longer gap is a break, not labeling time
BOLD, DIM, RESET, CLEAR = "\x1b[1m", "\x1b[2m", "\x1b[0m", "\x1b[2J\x1b[H"
STOPWORDS = {
    "what", "which", "where", "when", "does", "about", "their", "with", "from", "that", "this",
    "have", "much", "many", "make", "came", "says", "describe", "most", "main", "were",
}  # fmt: skip
KEYS = f"""Textual questions: press {BOLD}y{RESET} when the passage by itself states all or part of
the answer (gold), {BOLD}n{RESET} otherwise. Several passages may be gold; judge each on its own.
A passage is gold only if it answers the question as asked, qualifier included.

Absent questions (asking for something the filing should not contain): press {BOLD}y{RESET} only
if the passage does answer the question, {BOLD}n{RESET} if it does not.

{BOLD}b{RESET} goes back one passage, {BOLD}x{RESET} flags a bad or unclear question (it gets
replaced, and its remaining passages are skipped), {BOLD}q{RESET} quits. Every key is saved."""
LABEL_GUIDE = f"""{BOLD}Labeling the golden set{RESET}

Each screen shows a question and one passage from the company's latest 10-K.

{KEYS}

Press any key to start, q to quit."""
AUDIT_GUIDE = f"""{BOLD}Auditing Claude's labels{RESET}

First, a blind sample of {AUDIT_SIZE} passages: label each exactly as in make label (Claude's label
is hidden). Then a review of every passage where your label and Claude's differ, with Claude's
reason: there you make the final call. The run ends with agreement and Cohen's kappa.

{KEYS}

Press any key to start, q to quit."""
# The cross-check's labeler gets KEYS's rule, the eval card's with the qualifier clause, and only
# what the blind screen shows (cross_prompt): never Claude's label or reason.
CROSS_SYSTEM = """\
You label passages from SEC 10-K filings for a retrieval test set. Judge each passage by itself,
never with outside knowledge.

Textual questions: the passage is gold when by itself it states all or part of the answer.
Several passages may be gold; judge each on its own. A passage is gold only if it answers the
question as asked, qualifier included.

Absent questions (asking for something the filing should not contain): the passage is gold only
if it does answer the question.

Reply with JSON only: gold, true or false, and why, in one short sentence."""
CROSS_SCHEMA = {
    "type": "object",
    "properties": {"gold": {"type": "boolean"}, "why": {"type": "string"}},
    "required": ["gold", "why"],
    "additionalProperties": False,
}
CROSS_MAX_TOKENS = 1024  # the JSON plus gpt-oss's short reasoning


def enable_ansi() -> None:
    """Turn on escape sequences (bold, clear screen) in a Windows console; a pipe's codec never
    fails on a character from a filing."""
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="replace")
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # standard output
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # virtual terminal processing


def read_key() -> str:
    """One key in lower case: a keypress in a Windows console, else the first letter of a line."""
    if sys.platform == "win32" and sys.stdin.isatty():
        import msvcrt

        while True:
            key = msvcrt.getwch()
            if key in ("\x00", "\xe0"):  # a function or arrow key sends a second code
                msvcrt.getwch()
                continue
            return "q" if key == "\x03" else key.lower()  # Ctrl+C
    try:
        return (input("> ").strip()[:1] or "?").lower()
    except EOFError:
        return "q"


def key_or_quit() -> str:
    try:
        return read_key()
    except KeyboardInterrupt:
        return "q"


def highlight(line: str, words: set[str]) -> str:
    if not words:
        return line
    pattern = r"\b(?:" + "|".join(map(re.escape, sorted(words))) + r")\w*"
    return re.sub(pattern, lambda found: BOLD + found[0] + RESET, line, flags=re.IGNORECASE)


def show(header: str, question: str, meta: str, body: str, prompt: str) -> None:
    words = {word.lower() for word in re.findall(r"[A-Za-z]{4,}", question)} - STOPWORDS
    width = max(40, min(shutil.get_terminal_size().columns, 110) - 2)
    lines = [CLEAR + DIM + header + RESET, "", BOLD + question + RESET, DIM + meta + RESET, ""]
    for paragraph in body.splitlines():
        lines += [highlight(line, words) for line in textwrap.wrap(paragraph, width) or [""]]
    print("\n".join([*lines, "", prompt]), flush=True)


def save(row: dict[str, Any]) -> None:
    row["at"] = datetime.now(UTC).isoformat(timespec="seconds")
    with USER_LABELS.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")


def save_label(qid: str, candidate: dict[str, Any], gold: bool, **extra: Any) -> None:
    keep = ("chunk_id", "accession_number", "item", "char_start", "sha256")
    save({"id": qid, **{k: candidate[k] for k in keep}, "gold": gold, **extra})


Item = tuple[str, dict[str, Any]]  # question id, pool candidate


def golden() -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    if (ROOT / "manifest.json").exists() and read_manifest()["status"] == "frozen":
        raise SystemExit(f"Golden set {VERSION} is frozen: a new label would make it v2.")
    pools = read_jsonl(ROOT / "pools.jsonl")
    if not pools:
        raise SystemExit("No pools yet: run `python -m evals.golden build` first.")
    return {row["id"]: row for row in read_jsonl(ROOT / "questions.jsonl")}, pools


def blind(items: list[Item], questions: dict[str, dict[str, Any]], title: str) -> bool:
    """Ask for a blind label on each item without one; True once none is left."""
    rows = read_jsonl(USER_LABELS)
    judged, flagged = blind_labels(rows), labels(rows)[1]
    pending = [
        n
        for n, (qid, candidate) in enumerate(items)
        if (qid, candidate["chunk_id"]) not in judged and qid not in flagged
    ]
    done: list[int] = []
    paces: list[float] = []
    started = time.perf_counter()
    while pending:
        qid, candidate = items[pending[0]]
        question = questions[qid]
        pace = sum(paces) / len(paces) if paces else FIRST_GUESS_S
        header = (
            f"{title} {pending[0] + 1} of {len(items)} · {qid} ({question['category']}) ·"
            f" {len(pending)} left, about {len(pending) * pace / 60:.0f} min"
        )
        prompt = (
            "Does this passage answer the question?  y yes  n no  b back  x flag  q quit"
            if question["category"] == "unanswerable"
            else "Gold passage?  y yes  n no  b back  x flag question  q quit"
        )
        meta = f"{question['routing']['tickers'][0]} · Item {candidate['item']}"
        show(header, question["question"], meta, candidate["text"], prompt)
        key = key_or_quit()
        now = time.perf_counter()
        if key in ("y", "n"):
            if now - started < IDLE_S:
                paces.append(now - started)
            save_label(qid, candidate, key == "y")
            done.append(pending.pop(0))
        elif key == "b" and done:
            pending.insert(0, done.pop())
        elif key == "x":
            save({"id": qid, "flag": True})
            pending = [n for n in pending if items[n][0] != qid]
        elif key == "q":
            return False
        started = now
    return True


def audit_sample(pools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The blind sample, drawn once with a fixed seed and kept in audit.jsonl.

    Passages Claude labeled in this version (never one carried from v1) that the user has not
    labeled yet: one Claude-gold and one other passage from each question, more Claude-gold ones
    until AUDIT_MIN_GOLD, then any, round robin over the questions in a shuffled order; shown
    grouped by question.
    """
    if AUDIT.exists():
        return read_jsonl(AUDIT)
    claude = labels(read_jsonl(AI_LABELS))[0]
    judged, flagged = labels(read_jsonl(USER_LABELS))
    rng = random.Random(f"{VERSION}:audit")  # noqa: S311 - a sample, not security
    free: dict[str, list[str]] = {}
    for pool in pools:
        ids = sorted(
            c["chunk_id"]
            for c in pool["candidates"]
            if (pool["id"], c["chunk_id"]) in claude and (pool["id"], c["chunk_id"]) not in judged
        )
        rng.shuffle(ids)
        if ids and pool["id"] not in flagged:
            free[pool["id"]] = ids
    qids = list(free)
    rng.shuffle(qids)
    picks: list[tuple[str, str]] = []

    def one_each(want: bool | None, stop: Callable[[], bool]) -> bool:
        took = False
        for qid in qids:
            match = next((c for c in free[qid] if want is None or claude[qid, c] == want), None)
            if match is not None and not stop():
                free[qid].remove(match)
                picks.append((qid, match))
                took = True
        return took

    def full() -> bool:
        return len(picks) >= AUDIT_SIZE

    def enough_gold() -> bool:
        return full() or sum(claude[pick] for pick in picks) >= AUDIT_MIN_GOLD

    one_each(True, full)
    one_each(False, full)
    while not enough_gold() and one_each(True, enough_gold):
        pass
    while not full() and one_each(None, full):
        pass
    order = {pool["id"]: n for n, pool in enumerate(pools)}
    picks.sort(key=lambda pick: order[pick[0]])  # stable: draw order within a question
    sample = [{"id": qid, "chunk_id": chunk_id} for qid, chunk_id in picks]
    write_jsonl(AUDIT, sample)
    return sample


def said(gold: bool) -> str:
    return "gold" if gold else "not gold"


def review(questions: dict[str, dict[str, Any]], candidates: dict[tuple[str, str], Any]) -> bool:
    """The final call on every passage where the user's blind label and Claude's differ."""
    ai_rows = read_jsonl(AI_LABELS)
    claude = labels(ai_rows)[0]
    why = {(row["id"], row["chunk_id"]): row.get("why", "") for row in ai_rows}
    rows = read_jsonl(USER_LABELS)
    mine = blind_labels(rows)
    differ = [key for key in mine if key in claude and mine[key] != claude[key]]
    reviewed = {(row["id"], row["chunk_id"]) for row in rows if row.get("step") == "review"}
    pending = [key for key in differ if key not in reviewed]
    done: list[tuple[str, str]] = []
    while pending:
        key = pending[0]
        qid = key[0]
        question, candidate = questions[qid], candidates[key]
        header = (
            f"Review {differ.index(key) + 1} of {len(differ)} · {qid} ({question['category']}) ·"
            " your blind label and Claude's differ"
        )
        prompt = (
            f"You said {BOLD}{said(mine[key])}{RESET}; Claude said"
            f" {BOLD}{said(claude[key])}{RESET}: {why[key]}"
            "\nFinal call?  y gold  n not gold  b back  q quit"
        )
        meta = f"{question['routing']['tickers'][0]} · Item {candidate['item']}"
        show(header, question["question"], meta, candidate["text"], prompt)
        pressed = key_or_quit()
        if pressed in ("y", "n"):
            save_label(qid, candidate, pressed == "y", step="review")
            done.append(pending.pop(0))
        elif pressed == "b" and done:
            pending.insert(0, done.pop())
        elif pressed == "q":
            return False
    return True


def report() -> None:
    stats = audit_stats()
    low, high = stats["kappa_ci"]
    settled = (
        f"{stats['reviewed']} reviewed, {stats['review_as_claude']} settled on Claude's label"
        if stats["blind_labeler"] == "human"
        else "a model's labels get no review, so Claude's stand"
    )
    print(
        f"\nBlind labels ({stats['blind_labeler']}) against Claude's, before review:"
        f" {stats['passages']} passages ({stats['claude_gold']} Claude-gold,"
        f" {stats['blind_gold']} gold in the blind labels)."
        f" Agreement {stats['agreement']:.1%}, Cohen's kappa {stats['kappa']:.2f}"
        f" (95% CI {low:.2f} to {high:.2f}, bootstrap)."
        f"\nDisagreements {stats['disagreements']}: {settled}.",
        flush=True,
    )


def cross_prompt(question: dict[str, Any], candidate: dict[str, Any]) -> str:
    """What the blind screen shows, for a model: the question and its kind, the company and the
    item, the passage, and the screen's question."""
    absent = question["category"] == "unanswerable"
    return "\n".join(
        [
            f"Question ({'absent' if absent else 'textual'}): {question['question']}",
            f"{question['routing']['tickers'][0]} · Item {candidate['item']}",
            "",
            candidate["text"],
            "",
            "Does this passage answer the question?" if absent else "Is this passage gold?",
        ]
    )


async def cross_labels(model: Provider, cache: Cache) -> None:
    """make audit's blind pass with a model in the user's place: its label of each sample passage
    it has not labeled yet, saved as the user's would be, with its name and reason."""
    questions, pools = golden()
    candidates = {(p["id"], c["chunk_id"]): c for p in pools for c in p["candidates"]}
    done = blind_labels(read_jsonl(USER_LABELS))
    for pick in audit_sample(pools):
        key = (pick["id"], pick["chunk_id"])
        if key in done:
            continue
        context = {"question": pick["id"], "passage": pick["chunk_id"]}
        recorded = Recorded(model, "label", cache, context, [])
        prompt = cross_prompt(questions[pick["id"]], candidates[key])

        async def ask(recorded: Recorded = recorded, prompt: str = prompt) -> Completion:
            return await recorded.complete(
                CROSS_SYSTEM, prompt, max_tokens=CROSS_MAX_TOKENS, schema=CROSS_SCHEMA
            )

        text = (await patiently(ask)).text
        try:
            reply = json.loads(text)
            gold, why = reply["gold"], str(reply["why"])
            if not isinstance(gold, bool):
                raise TypeError("gold is not true or false")
        except (ValueError, KeyError, TypeError) as exc:
            unread = f"{pick['id']} {pick['chunk_id'][:8]}: unreadable reply ({exc})."
            raise SystemExit(unread) from exc
        save_label(pick["id"], candidates[key], gold, labeler=model.name, why=why)


def cross_check() -> None:
    """The judge model (LLM_JUDGE) labels the blind sample, then make audit's agreement numbers."""
    import httpx

    from evals.harness import CACHE, EvalSettings
    from filinglens_core.settings import load_settings
    from filinglens_llm.providers import TIMEOUT, provider
    from filinglens_telemetry import configure_logging

    settings = load_settings(EvalSettings)
    configure_logging("label", "WARNING")

    async def run() -> None:
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            model = provider(settings.llm_judge, settings, http)
            await cross_labels(model, Cache(CACHE / "calls.jsonl"))

    try:
        asyncio.run(run())
    except Stop as stop:
        raise SystemExit(f"{stop} The labels so far are saved; rerun to finish.") from None
    report()


def audit() -> None:
    questions, pools = golden()
    candidates = {(p["id"], c["chunk_id"]): c for p in pools for c in p["candidates"]}
    sample = audit_sample(pools)
    items = [(pick["id"], candidates[pick["id"], pick["chunk_id"]]) for pick in sample]
    print(AUDIT_GUIDE, flush=True)
    if key_or_quit() == "q" or not blind(items, questions, "Audit passage"):
        mine = blind_labels(read_jsonl(USER_LABELS))
        left = sum((pick["id"], pick["chunk_id"]) not in mine for pick in sample)
        print(f"\nStopped: {left} of {len(items)} blind passages left. make audit resumes here.")
        return
    report()
    if not review(questions, candidates):
        print("\nStopped during the review. make audit resumes there.")
        return
    report()
    print("The audit is complete: tell Claude.")


def label_all() -> None:
    questions, pools = golden()
    items = [(pool["id"], candidate) for pool in pools for candidate in pool["candidates"]]
    print(LABEL_GUIDE, flush=True)
    if key_or_quit() != "q" and blind(items, questions, "Passage"):
        print("Every pooled passage is labeled.")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    enable_ansi()
    if command == "audit":
        audit()
    elif command == "label":
        label_all()
    elif command == "crosscheck":
        cross_check()
    else:
        raise SystemExit("usage: python -m evals.label audit|label|crosscheck")
