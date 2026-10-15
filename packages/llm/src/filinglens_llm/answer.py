"""The answer prompt and its reply format: text citing source ids, then a Sources block of quotes.

    Apple's net sales were $416.2 billion in fiscal 2025 [F1]. Services grew [C3].

    Sources:
    [F1] "416,161,000,000 USD"
    [C3] "Services net sales increased due to higher advertising"

Readers get the ids renumbered [1], [2]... in order of first use, the same way while streaming
and in the validated answer, so both read alike when validation changes nothing.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from filinglens_llm.validate import (
    MARKER,
    Quoted,
    check_sentence,
    citation_error,
    cited,
    split_sentences,
)

INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
MAX_TOKENS = 1024
SOURCES_HEADING = re.compile(r"^[ \t*#_]*sources[ \t*_]*:?[ \t*_]*$", re.IGNORECASE | re.MULTILINE)
SOURCE_LINE = re.compile(
    r"^[ \t*-]*\[\s*(?P<alias>[CF]\d+)\s*\][ \t:|\-]*(?P<quote>.*?)[ \t]*$", re.MULTILINE
)
QUOTE_MARKS = "\"'“”‘’«»`"  # noqa: RUF001 - the quote marks models write
HOLD = 24  # characters a stream holds back: a starting "Sources:" heading or a split marker
SYSTEM = f"""\
You answer analysts' questions about companies' SEC filings, using only the sources given.
Rules:
1. State only what the sources say. Add no outside knowledge, guesses or calculations.
2. End every sentence with the ids of its sources in brackets, such as [C2] or [F1][C3], before
   the period.
3. After the answer write a line "Sources:", then one line per source you cited: [id] "quote".
   For a filing excerpt (C1, C2...) the quote is a short span copied word for word from it that
   supports your sentence. For a financial fact (F1, F2...) quote its value as listed.
4. Give figures as the sources state them, or rounded, such as $416.2 billion.
5. Answer in at most 6 sentences, without headings or lists.
6. If the sources do not answer the question, reply with only {INSUFFICIENT}."""


@dataclass(frozen=True)
class Source:
    alias: str  # the id the model cites: F1 for a fact, C1 for a chunk
    chunk_id: str | None
    fact_id: str | None
    heading: str  # company, filing, period, item
    text: str  # a chunk's text, which a quote must come from; a fact's value line
    value: Decimal | None  # a fact's value
    url: str


def user_prompt(question: str, sources: Sequence[Source], problems: Sequence[str] = ()) -> str:
    lines = [f"Question: {question}", "", "Sources:"]
    for source in sources:
        lines += [f"[{source.alias}] {source.heading}", source.text, ""]
    if problems:
        lines += ["Your last answer broke the rules:", *(f"- {problem}" for problem in problems)]
        lines.append("Answer again and follow every rule.")
    return "\n".join(lines)


@dataclass(frozen=True)
class Reply:
    text: str  # the answer, before the Sources block, still citing source ids
    quotes: dict[str, list[str]]  # source id -> the quotes given for it
    insufficient: bool


def read_reply(reply: str) -> Reply:
    heading = SOURCES_HEADING.search(reply)
    text = (reply[: heading.start()] if heading else reply).strip()
    quotes: dict[str, list[str]] = {}
    for line in SOURCE_LINE.finditer(reply[heading.end() :] if heading else ""):
        quotes.setdefault(line["alias"], []).append(line["quote"].strip().strip(QUOTE_MARKS))
    return Reply(text, quotes, text.startswith(INSUFFICIENT))


def numbered(text: str, order: dict[str, int]) -> str:
    """Replace source ids with [1], [2]... by first use; `order` keeps the numbers given so far."""

    def number(marker: re.Match[str]) -> str:
        aliases = re.split(r"\s*,\s*", marker[1])
        return "".join(f"[{order.setdefault(alias, len(order) + 1)}]" for alias in aliases)

    return MARKER.sub(number, text)


class Visible:
    """The part of a streamed reply to show as it arrives: the answer with numbered markers, never
    the Sources block. Everything shown joins up to the answer that check() keeps when every
    sentence holds; nothing shows of an INSUFFICIENT reply."""

    def __init__(self) -> None:
        self._reply = ""
        self._shown = 0
        self._order: dict[str, int] = {}

    def feed(self, text: str = "", *, final: bool = False) -> str:
        self._reply += text
        heading = SOURCES_HEADING.search(self._reply)
        if heading is not None:
            end = heading.start()
        else:
            end = len(self._reply) if final else max(0, len(self._reply) - HOLD)
        raw = self._reply[:end].strip()
        if raw.startswith(INSUFFICIENT) or (not final and INSUFFICIENT.startswith(raw)):
            return ""
        if not final and raw.rfind("[") > raw.rfind("]"):  # a marker still arriving
            raw = raw[: raw.rfind("[")].rstrip()
        answer = numbered(raw, self._order)
        new, self._shown = answer[self._shown :], len(answer)
        return new


@dataclass(frozen=True)
class Checked:
    text: str  # the answer with numbered markers; the reply's own text when every sentence holds
    citations: list[tuple[str, str]]  # (source id, quote) for [1], [2]... in order
    problems: list[str]  # one per failed sentence, quoting it
    removed: int  # sentences dropped because they failed


def check(reply: Reply, sources: Mapping[str, Source]) -> Checked:
    """Validate each sentence, drop the failures, and number the remaining citations 1, 2, 3."""
    kept: list[str] = []
    problems: list[str] = []
    for sentence in split_sentences(reply.text):
        problem = check_sentence(sentence, reply.quotes, sources)
        if problem is None:
            kept.append(sentence)
        else:
            problems.append(f'"{sentence}": {problem}')
    text = reply.text if not problems else " ".join(kept)
    chunks = {s.chunk_id: s.text for s in sources.values() if s.chunk_id is not None}
    citations: list[tuple[str, str]] = []
    for alias in cited(text):
        source = sources[alias]
        if source.chunk_id is None:  # a fact: its value line is the quote
            citations.append((alias, source.text))
            continue
        good = [
            quote
            for quote in reply.quotes.get(alias, [])
            if citation_error(Quoted(source.chunk_id, None, quote), chunks, ()) is None
        ]
        citations.append((alias, good[0]))
    return Checked(numbered(text, {}), citations, problems, removed=len(problems))
