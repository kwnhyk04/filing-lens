"""Answer post-validation: citations must quote their source, and amounts must match.

Pure functions without I/O; the answer pipeline (build step 6) and the evals call them.
"""

import re
import unicodedata
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

# Scale words, and the abbreviations models write: $4.2B, $4.2bn, 4,213M, 350K, 1.2T.
SCALES = {
    **dict.fromkeys(("thousand", "k"), 10**3),
    **dict.fromkeys(("million", "m"), 10**6),
    **dict.fromkeys(("billion", "b", "bn"), 10**9),
    **dict.fromkeys(("trillion", "t"), 10**12),
}
TOLERANCE = Decimal("0.005")  # numeric exact match counts within 0.5% (docs/context.md)
# Curly, low-9 and reversed quotes: U+2018 to U+201B single, U+201C to U+201F double.
STRAIGHT_QUOTES = {code: "'" if code < 0x201C else '"' for code in range(0x2018, 0x2020)}
# After whitespace and "$" are dropped and letters lowered: -1,234 or (1,234), then a scale.
AMOUNT = re.compile(
    r"-?\(?(?P<number>\d[\d,]*(?:\.\d+)?)\)?"
    r"(?P<scale>(?:thousand|million|billion|trillion)s?|bn|[kmbt])?\)?"
)
SCALE_WORD = r"(?:thousand|million|billion|trillion)s?|bn"
# Amounts in answer text: money ($4.2B, $416.2 billion, $(1,234)), numbers with a scale word,
# percentages, and numbers with thousands separators. Years and small counts are not amounts.
AMOUNT_IN_TEXT = re.compile(
    rf"-?\(?\$\s?\(?\d[\d,]*(?:\.\d+)?\)?(?:\s?(?:{SCALE_WORD}|[kmbt])\b)?"
    rf"|\b\d[\d,]*(?:\.\d+)?\s?(?:{SCALE_WORD})\b"
    r"|(?P<percent>\b\d+(?:\.\d+)?)\s?(?:%|percent\b)"
    r"|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b",
    re.IGNORECASE,
)
NUMBER = re.compile(rf"\d[\d,]*(?:\.\d+)?(?:\s?(?:{SCALE_WORD})\b)?", re.IGNORECASE)
# The model cites its source ids: [C2], [F1][C3] or [C2, C4].
MARKER = re.compile(r"\[\s*([CF]\d+(?:\s*,\s*[CF]\d+)*)\s*\]")
# Any other bracket holding a digit, such as [12] for C12 or [D1], names no source (x18).
STRAY = re.compile(r"\[[^\[\]]*\d[^\[\]]*\]")
# A sentence ends at . ! or ? (markers before it) when whitespace and a capital, digit or $ follow.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9$\"'(])")
# A period that may only close an abbreviation: initials (U.S., e.g., N.A.) or Inc., Corp., Co.
ABBREVIATION = re.compile(r"\b(?:(?:[A-Za-z]\.){2,}|(?:Inc|Corp|Co|No|etc)\.)$")
# Words that start sentences but seldom follow an abbreviation inside one ("the U.S. The rest").
STARTER = re.compile(
    r"(?:A|An|And|As|At|But|By|For|From|He|However|In|It|Its|On|Our|She|That|The|Their|There"
    r"|These|They|This|Those|To|We)\b"
)
TABLE_SCALES = (1, 10**3, 10**6, 10**9)  # a quoted table row may be in thousands or millions
PERCENT_SCALES = (1, 100)  # 16.2% against a fact of 0.162


class Cited(Protocol):
    """What the check reads from a citation, such as filinglens_api.schemas.Citation."""

    chunk_id: str | None
    fact_id: str | None
    quote: str


def _normalize(text: str) -> str:
    """NFKC (no-break spaces become spaces), straight quotes, single spaces; words stay exact."""
    return " ".join(unicodedata.normalize("NFKC", text).translate(STRAIGHT_QUOTES).split())


def citation_error(
    citation: Cited, chunks: Mapping[str, str], fact_ids: Collection[str]
) -> str | None:
    """Why a citation fails, or None when it holds.

    A chunk citation must quote its chunk: the quote must be a substring of the chunk text once
    both are normalized the same way (whitespace, quote style, NFKC), so a changed word, digit or
    letter case fails. A fact citation must name a fact the answer was given. `chunks` maps the
    ids of the chunks the answer was given to their text.
    """
    if citation.chunk_id is not None:
        text = chunks.get(citation.chunk_id)
        if text is None:
            return f"chunk {citation.chunk_id} is not among the answer's sources"
        quote = _normalize(citation.quote)
        if not quote:
            return "the quote is empty"
        if quote not in _normalize(text):
            return f"the quote is not in chunk {citation.chunk_id}"
        return None
    if citation.fact_id is None:
        return "the citation names no chunk and no fact"
    if citation.fact_id not in fact_ids:
        return f"fact {citation.fact_id} is not among the answer's sources"
    return None


def parse_amount(text: str, scale: str | None = None) -> Decimal:
    """An amount as a number: '$4.2 billion' and '$4.2B' are 4200000000, '(1,234)' is -1234.

    `scale` is the unit of a table's figures, such as 'millions' from '(in millions)'. A scale in
    both the text and `scale` raises ValueError, and so does anything that is not one amount,
    such as prose around it ('about $4.2B').
    """
    compact = "".join(text.split()).replace("$", "").replace("\N{MINUS SIGN}", "-").lower()
    match = AMOUNT.fullmatch(compact)
    if match is None or compact.count("(") != compact.count(")"):
        raise ValueError(f"Not an amount: {text!r}")
    if match["scale"] and scale:
        raise ValueError(f"Two scales for {text!r}: {match['scale']} and {scale}")
    word = (match["scale"] or scale or "").lower().removesuffix("s")
    if word and word not in SCALES:
        raise ValueError(f"Unknown scale: {scale!r}")
    value = Decimal(match["number"].replace(",", "")) * SCALES.get(word, 1)
    return -value if compact.startswith(("-", "(")) else value


def amounts_match(actual: Decimal, expected: Decimal, tolerance: Decimal = TOLERANCE) -> bool:
    """Whether `actual` is within `tolerance` (0.5%) of `expected`; the signs must agree."""
    return abs(actual - expected) <= tolerance * abs(expected)


def find_amounts(text: str) -> list[tuple[Decimal, bool]]:
    """Each amount in answer text ("about $4.2B", "4,213 million", "12.5%") with whether it is a
    percentage; parse_amount reads each one."""
    found: list[tuple[Decimal, bool]] = []
    for match in AMOUNT_IN_TEXT.finditer(text):
        if match["percent"]:
            found.append((Decimal(match["percent"]), True))
            continue
        try:
            found.append((parse_amount(match[0]), False))
        except ValueError:
            continue
    return found


def numbers_in(text: str) -> list[Decimal]:
    """Every number in a quote, a scale word applied, as evidence for the answer's amounts."""
    numbers: list[Decimal] = []
    for match in NUMBER.finditer(text):
        try:
            numbers.append(parse_amount(match[0]))
        except ValueError:
            continue
    return numbers


def supported(amount: Decimal, percent: bool, evidence: Collection[Decimal]) -> bool:
    """Whether an amount matches a number of its evidence within 0.5%, at some scale.

    Signs are ignored: "a net loss of $1.2 billion" reports a NetIncomeLoss of -1.2e9.
    """
    scales = PERCENT_SCALES if percent else TABLE_SCALES
    return any(
        amounts_match(abs(amount), abs(number) * scale)
        for number in evidence
        if number
        for scale in scales
    )


def split_sentences(text: str) -> list[str]:
    """The sentences of answer text. After an abbreviation (U.S., Inc., e.g.) one ends only where
    a sentence starter follows: "the U.S. Government" stays whole, "in the U.S. The rest" splits."""
    sentences: list[str] = []
    for piece in SENTENCE_END.split(text.strip()):
        if sentences and ABBREVIATION.search(sentences[-1]) and not STARTER.match(piece):
            sentences[-1] += " " + piece
        elif piece.strip():
            sentences.append(piece)
    return sentences


class Source(Protocol):
    """What the check reads from an answer's source: a chunk (text) or a fact (value)."""

    @property
    def chunk_id(self) -> str | None: ...

    @property
    def fact_id(self) -> str | None: ...

    @property
    def text(self) -> str: ...

    @property
    def value(self) -> Decimal | None: ...


@dataclass
class Quoted:
    """A Cited: one marker's source ids and quote."""

    chunk_id: str | None
    fact_id: str | None
    quote: str


def cited(text: str) -> list[str]:
    """The source ids a text cites, in order, each once."""
    ids: list[str] = []
    for marker in MARKER.finditer(text):
        ids += [alias for alias in re.split(r"\s*,\s*", marker[1]) if alias not in ids]
    return ids


def check_sentence(
    sentence: str, quotes: Mapping[str, Sequence[str]], sources: Mapping[str, Source]
) -> str | None:
    """Why a sentence of an answer fails, or None when it holds.

    It must cite at least one source id, such as [C2], and hold no other bracketed marker such as
    [12]; a cited chunk needs a quote under Sources that passes citation_error; and each amount
    in the sentence must match a cited fact's value or a number in a passing quote. `quotes` maps
    source ids to the quotes given for them; `sources` maps the ids the model was given (F1, C2)
    to the sources.
    """
    if stray := STRAY.search(MARKER.sub("", sentence)):  # shown, it would cite nothing
        return f"{stray[0]} is not one of the sources"
    aliases = cited(sentence)
    if not aliases:
        return "it cites no source"
    chunks = {s.chunk_id: s.text for s in sources.values() if s.chunk_id is not None}
    fact_ids = {s.fact_id for s in sources.values() if s.fact_id is not None}
    evidence: list[Decimal] = []
    for alias in aliases:
        source = sources.get(alias)
        if source is None:
            return f"[{alias}] is not one of the sources"
        if source.value is not None:  # a fact: its value is the evidence
            evidence.append(source.value)
            continue
        given = quotes.get(alias, [])
        good = [
            q
            for q in given
            if citation_error(Quoted(source.chunk_id, None, q), chunks, fact_ids) is None
        ]
        if not good:
            return (
                f"[{alias}] has no quote under Sources"
                if not given
                else f"[{alias}] the quote is not in chunk {source.chunk_id}"
            )
        evidence += [number for quote in good for number in numbers_in(quote)]
    for amount, percent in find_amounts(MARKER.sub("", sentence)):
        if not supported(amount, percent, evidence):
            shown = f"{amount.normalize():,f}{'%' if percent else ''}"
            return f"the amount {shown} is not in the sources it cites"
    return None


@dataclass(frozen=True)
class Figure:
    """An amount of a sentence that holds, as written, with the cited source whose number it is."""

    text: str  # as the sentence writes it, such as "$416.2 billion" or "56%"
    alias: str  # the source id that holds it, such as F1 or C2
    number: Decimal  # that source's number: a fact's value, or a number in a quote of it


def figures(
    sentence: str, quotes: Mapping[str, Sequence[str]], sources: Mapping[str, Source]
) -> list[Figure]:
    """Each amount of a sentence that check_sentence passed, with the first cited source holding it.

    The evidence and the match are check_sentence's (a fact's value, or the numbers of a chunk's
    passing quotes, matched by supported); an amount that no cited source holds is left out.
    """
    chunks = {s.chunk_id: s.text for s in sources.values() if s.chunk_id is not None}
    evidence: list[tuple[str, Decimal]] = []
    for alias in cited(sentence):
        source = sources.get(alias)
        if source is None:
            continue
        if source.value is not None:
            evidence.append((alias, source.value))
            continue
        for quote in quotes.get(alias, []):
            if citation_error(Quoted(source.chunk_id, None, quote), chunks, ()) is None:
                evidence += [(alias, number) for number in numbers_in(quote)]
    found: list[Figure] = []
    for match in AMOUNT_IN_TEXT.finditer(MARKER.sub("", sentence)):
        percent = match["percent"] is not None
        try:
            amount = Decimal(match["percent"]) if percent else parse_amount(match[0])
        except ValueError:
            continue
        holder = next(((a, n) for a, n in evidence if supported(amount, percent, [n])), None)
        if holder is not None:
            found.append(Figure(match[0], *holder))
    return found
