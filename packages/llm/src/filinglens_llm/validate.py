"""Answer post-validation: citations must quote their source, and amounts must match.

Pure functions without I/O; the answer pipeline (build step 6) and the evals call them.
"""

import re
import unicodedata
from collections.abc import Collection, Mapping
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
