"""Answer post-validation: citations must quote their source, and amounts must match.

Pure functions without I/O; the answer pipeline (build step 6) and the evals call them.
"""

import itertools
import re
import unicodedata
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

# Scale words, and the abbreviations models write: $4.2B, $4.2bn, 4,213M, 350K, 1.2T. Decimal
# powers keep an amount's last stated digit in its exponent: $4.1 billion is 4.1E+9, read to 1E+8.
SCALES = {
    **dict.fromkeys(("thousand", "k"), Decimal("1E3")),
    **dict.fromkeys(("million", "m"), Decimal("1E6")),
    **dict.fromkeys(("billion", "b", "bn"), Decimal("1E9")),
    **dict.fromkeys(("trillion", "t"), Decimal("1E12")),
}
TOLERANCE = Decimal("0.005")  # numeric exact match counts within 0.5% (docs/context.md)
MINUS = "-\N{MINUS SIGN}"
# Curly, low-9 and reversed quotes: U+2018 to U+201B single, U+201C to U+201F double.
STRAIGHT_QUOTES = {code: "'" if code < 0x201C else '"' for code in range(0x2018, 0x2020)}
# The currency an amount may carry. A letter after it keeps it: "51.32 USDT" is no amount.
CURRENCY = re.compile(r"\$|usd(?![a-z])")
# With whitespace and the currency dropped and letters lowered: -1,234 or (1,234), then a scale.
AMOUNT = re.compile(
    r"-?\(?(?P<number>\d[\d,]*(?:\.\d+)?)\)?"
    r"(?P<scale>(?:thousand|million|billion|trillion)s?|bn|[kmbt])?\)?"
)
SCALE_WORD = r"(?:thousand|million|billion|trillion)s?|bn"
# Amounts in answer text: money ($4.2B, $416.2 billion, $(1,234), USD 51.32, 51.32 USD), numbers
# with a scale word, percentages, and numbers with thousands separators. Years and small counts
# are not amounts: "2025 USD" is a year, and "2025, USD" keeps its comma out of the number.
AMOUNT_IN_TEXT = re.compile(
    rf"[{MINUS}]?\(?(?:\$|\bUSD)\s?\(?\d[\d,]*(?:\.\d+)?\)?(?:\s?(?:{SCALE_WORD}|[kmbt])\b)?"
    rf"|\b(?!(?:19|20)\d\d\s?USD)\d(?:[\d,]*\d)?(?:\.\d+)?(?:\s?(?:{SCALE_WORD}|[kmbt]))?\s?USD\b"
    rf"|\b\d[\d,]*(?:\.\d+)?\s?(?:{SCALE_WORD})\b"
    r"|(?P<percent>\b\d+(?:\.\d+)?)\s?(?:%|percent\b)"
    r"|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b",
    re.IGNORECASE,
)
NUMBER = re.compile(rf"\d[\d,]*(?:\.\d+)?(?P<scale>\s?(?:{SCALE_WORD})\b|[kmbt]\b)?", re.IGNORECASE)
# A NUMBER that is a bare year, 1900 to 2099, which keeps a comma after it: "in 2025, sales". A
# date, not a figure; "$2025" is money.
YEAR = re.compile(r"(?<!\$)(?:19|20)\d\d,?")
MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
)
# A date's numbers back nothing: "as of December 31, 2025" must not hold "$31 billion".
DATE = re.compile(
    rf"\b{MONTH}\s+\d{{1,2}}\b(?:,?\s+(?:19|20)\d\d\b)?"
    rf"|\b\d{{1,2}}\s+{MONTH}(?:,?\s+(?:19|20)\d\d\b)?"
    r"|\b(?:19|20)\d\d-\d\d-\d\d\b|\b\d{1,2}/\d{1,2}/(?:19|20)?\d\d\b",
    re.IGNORECASE,
)
# A table's unit as filings state it: "(in millions)", "$ in thousands", "Millions of dollars", or
# "Millions | 2025 | 2024" heading a table; "millions of customers" and "(millions of pounds)" not.
DOLLARS = r"(?:u\.?s\.?\s+)?dollars\b"
STATED = re.compile(
    rf"(?:\bin\s+(?:u\.?s\.?\s+)?|\$\s*|\(\s*|^\s*)(thousand|million|billion)s\b(?!\s+of\s+(?!{DOLLARS}))"
    rf"|\b(thousand|million|billion)s\s+of\s+{DOLLARS}",
    re.IGNORECASE | re.MULTILINE,
)
# "5.7 | %" and "(1) | %" from a table, and "5.7%" and "5.7 percent" in prose.
PERCENT_MARK = re.compile(r"\s*\)?\s*(?:\|\s*)?(?:%|percent\b)", re.IGNORECASE)
# The number ends a table's cell, the quote, or a cell or row a quote joined to the next with
# spaces ("385 Accounts receivable", "584,060 $ 662,132", "592,353 671,907"); not "1,800 stores".
CELL_END = re.compile(r"\s*\)?\s*(?:\||$|[A-Z$(\d])")
BRACKET_OPEN = re.compile(r"\(\s*(?:\|\s*)?\$?\s*(?:\|\s*)?$")  # "(1,200" or "( | $ | 1,200"
DOLLAR_SIGN = re.compile(r"\$\s*(?:\|\s*)?\(?$")  # "$1,200" or "$ | 1,200"
PER_SHARE = re.compile(
    r"\bper\s+(?:\w+\s+){0,3}shares?\b|\bEPS\b|/\s*shares?\b|\b(?:a|each)\s+share\b", re.IGNORECASE
)
# A row that reports a result, where brackets mean a loss; elsewhere they mean a cost or an outflow.
RESULT_ROW = re.compile(r"\b(?:income(?!\s+tax)|earnings|profit)\b", re.IGNORECASE)
# Words that say a figure is a loss or negative, anywhere in a sentence.
LOSS = re.compile(
    r"\b(?:loss(?:es)?|lost|deficits?|negative|shortfall|outflows?|expenses?|used\s+in)\b",
    re.IGNORECASE,
)
# What may stand between a result's name and its amount: "net loss of about $1.2 billion".
LEADS_TO = (
    r"(?:\s+(?:of|was|were|is|at|totaled|totaling|reached))?"
    r"(?:\s+(?:about|approximately|nearly|roughly|around))?[\s$(|]*$"
)
NAMED_GAIN = re.compile(
    rf"\b(?:net income|net earnings|operating income|profits?|earned|gains?){LEADS_TO}",
    re.IGNORECASE,
)
NAMED_LOSS = re.compile(rf"\b(?:loss(?:es)?|lost|deficits?){LEADS_TO}", re.IGNORECASE)
# The model cites its source ids: [C2], [F1][C3], [C2, C4], or a calculation's [K1].
MARKER = re.compile(r"\[\s*([CFK]\d+(?:\s*,\s*[CFK]\d+)*)\s*\]")
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
# Comparison and direction words: such a sentence states each cited fact's figure (c02, test).
COMPARES = re.compile(
    r"\b(?:higher|lower|more|less|greater|larger|smaller|bigger|than|exceed\w*|increas\w*"
    r"|decreas\w*|ris(?:e|es|en|ing)|rose|fell|fall(?:s|en|ing)?|gr[eo]w\w*|declin\w*)\b",
    re.IGNORECASE,
)
# Words of change over time, which a sentence citing one company's two years must use rightly.
ROSE = r"increas\w*|ris(?:e|es|en|ing)|rose|gr[eo]w\w*"
FELL = r"decreas\w*|declin\w*|fell|fall(?:s|en|ing)?|drop\w*"
RISES = re.compile(rf"\b(?:{ROSE}|up)\b", re.IGNORECASE)
FALLS = re.compile(rf"\b(?:{FELL}|down)\b", re.IGNORECASE)
# The same beside a number, which is what a passage's direction word must be to count: "increased
# by 5%", "a 5% decline". Without "up" and "down", which say nothing there: "up to $5 billion".
GOES_TO = r"(?:\s+(?:by|of|to|about|approximately|nearly|roughly|around|some))*[\s$(]*$"
FOLLOWS = r"(?:\s*(?:%|percent\b))?\s*"
ROSE_TO = re.compile(rf"\b(?:{ROSE}){GOES_TO}", re.IGNORECASE)
FELL_TO = re.compile(rf"\b(?:{FELL}){GOES_TO}", re.IGNORECASE)
ROSE_AFTER = re.compile(rf"{FOLLOWS}(?:{ROSE})\b", re.IGNORECASE)
FELL_AFTER = re.compile(rf"{FOLLOWS}(?:{FELL})\b", re.IGNORECASE)
# A sentence on what the sources leave out, which only filing text can back. The words of saved
# drafts: other wording gets through, so the check is a floor, not a proof.
SILENT = re.compile(
    r"\b(?:sources?|filings?|facts?|figures?|excerpts?|passages?|documents?|data|information)\b.*?"
    r"\b(?:do|does|did)(?:\s+not|n\W?t)\b"
    r"|\bnot\s+(?:\w+\s+)?(?:stated|given|provided|mentioned|disclosed|specified|shown|available)\b"
    r"|\bcannot\s+be\s+\w+\s+from\b"
    r"|\bno\s+(?:\w+\s+){0,2}(?:information|details?|data|mention|explanation|breakdown)\b",
    re.IGNORECASE,
)
ABSENT = "it says what the sources do not state; say only what they show"
UNSTATED = "it compares figures without stating those of "
# Which way a comparison goes, beside a calculation's result: the rise and fall words do not read
# these, since "lower" may be right of the other year or company. Used only to keep a citation.
MORE = re.compile(r"\b(?:higher|more|greater|larger|bigger|above|exceed\w*)\b", re.IGNORECASE)
LESS = re.compile(r"\b(?:lower|less|smaller|fewer|below)\b", re.IGNORECASE)
WINDOW = 40  # characters before a number that may name it
ABOUT = r"(?:(?:about|approximately|nearly|roughly|around)\s+)?"
FROM = re.compile(rf"\bfrom\s+{ABOUT}\(?$", re.IGNORECASE)
TO = re.compile(rf"\bto\s+{ABOUT}\(?$", re.IGNORECASE)
UNITS = {"thousand": 10**3, "million": 10**6, "billion": 10**9}


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
    """An amount as a number: '$4.2 billion' and '$4.2B' are 4200000000, '(1,234)' is -1234, and
    '51.32 USD' and 'USD 51.32' are 51.32.

    `scale` is the unit of a table's figures, such as 'millions' from '(in millions)'. A scale in
    both the text and `scale` raises ValueError, and so does anything that is not one amount,
    such as prose around it ('about $4.2B'). The exponent is the last digit stated: 4.2E+9.
    """
    compact = CURRENCY.sub("", "".join(text.split()).lower()).replace("\N{MINUS SIGN}", "-")
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


def _balanced(written: str) -> str:
    """An amount as matched, without a bracket that closes or opens past it: "(USD 51.32 per
    share)" matches "(USD 51.32", which parse_amount refuses, and the amount went unchecked."""
    return written if written.count("(") == written.count(")") else written.strip("()")


def _named(text: str, start: int) -> int:
    """What the words before a number name it: 1 a gain ("net income of"), -1 a loss, else 0."""
    before = text[max(start - WINDOW, 0) : start]
    return bool(NAMED_GAIN.search(before)) - bool(NAMED_LOSS.search(before))


def _went(text: str, start: int, end: int) -> int:
    """Which way the words beside a number say it went: 1 up, -1 down, else 0."""
    before = text[max(start - WINDOW, 0) : start]
    up = ROSE_TO.search(before) or ROSE_AFTER.match(text, end)
    down = FELL_TO.search(before) or FELL_AFTER.match(text, end)
    return bool(up) - bool(down)


@dataclass(frozen=True)
class Amount:
    """An amount of a sentence, as it stands there."""

    text: str  # as written, without a bracket that closes past it
    value: Decimal
    percent: bool
    start: int
    end: int
    marked: bool  # a minus or brackets on it
    named: int  # _named
    went: int  # _went

    @property
    def money(self) -> bool:
        return CURRENCY.search(self.text.lower()) is not None


def _amounts(text: str) -> list[Amount]:
    """Each amount in answer text; parse_amount reads each one."""
    found: list[Amount] = []
    for match in AMOUNT_IN_TEXT.finditer(text):
        written, (start, end) = _balanced(match[0]), match.span()
        percent = bool(match["percent"])
        try:
            value = Decimal(match["percent"]) if percent else parse_amount(written)
        except ValueError:
            continue
        marked = "(" in match[0] or match[0][0] in MINUS or text[start - 1 : start] in ("(", "-")
        found.append(
            Amount(
                written,
                value,
                percent,
                start,
                end,
                marked,
                _named(text, start),
                _went(text, start, end),
            )
        )
    return found


def find_amounts(text: str) -> list[tuple[Decimal, bool]]:
    """Each amount in answer text ("about $4.2B", "4,213 million", "12.5%", "51.32 USD") with
    whether it is a percentage."""
    return [(amount.value, amount.percent) for amount in _amounts(text)]


def numbers_in(text: str) -> list[Decimal]:
    """Every number in a quote, a scale word applied, as evidence for the answer's amounts. A bare
    year is none: at a table's scale 2025 would back "$2 billion" (review, 2026-11-04)."""
    numbers: list[Decimal] = []
    for match in NUMBER.finditer(text):
        if YEAR.fullmatch(text, *match.span()):
            continue
        try:
            numbers.append(parse_amount(match[0]))
        except ValueError:
            continue
    return numbers


def rounded(amount: Decimal, number: Decimal) -> bool:
    """Whether `number` rounded at the last digit `amount` states is `amount`: $4.1 billion for
    4,121,000,000 (n24, user rule 2026-10-27), not $4.2 billion. A half rounds either way."""
    step = Decimal(1).scaleb(int(amount.as_tuple().exponent))
    return abs(number - amount) * 2 <= step


def matches(amount: Decimal, number: Decimal) -> bool:
    """Whether an amount states `number`: within 0.5%, or `number` rounded at the amount's last
    stated digit. Signs are ignored here: "a net loss of $1.2 billion" reports a NetIncomeLoss of
    -1.2e9, and _objection reads the sign from the sentence's words.
    """
    return amounts_match(abs(amount), abs(number)) or rounded(abs(amount), abs(number))


@dataclass(frozen=True)
class Number:
    """A number a cited source holds, and what it can back. An amount must match one of its own
    kind (`percent`), and a figure takes a table's scale only as a cell of a table that states one
    (`scales`). A fact is in base units, so it takes none."""

    value: Decimal  # as the source states it, with its own scale word
    percent: bool | None = False  # None: a plain cell, which may be either
    scales: tuple[int, ...] = (1,)
    per_share: bool = False
    negative: bool = False  # a fact below 0, or a bracketed result: the sentence must say so
    named: int = 0  # _named: a gain, a loss, or neither
    went: int = 0  # _went: the way the words beside it say it went

    def backs(self, amount: Amount) -> bool:
        """Whether `amount` states this number. Money must use a stated scale: "$4,121" is no
        reading of 4,121 in a table in millions; a bare count may."""
        if not self.value or self.percent not in (None, amount.percent):
            return False
        scales = self.scales if amount.money else (1, *self.scales)
        return any(matches(amount.value, self.value * scale) for scale in scales)


def _objection(alias: str, number: Number, amount: Amount, plain: str) -> str | None:
    """Why `number` of [alias] cannot back `amount`, though the figures agree: the sentence
    (`plain`) misses that it is a per-share figure or a loss, or says the opposite of its source."""
    if number.per_share and not PER_SHARE.search(plain):
        return f"[{alias}] is a per-share figure, which the sentence does not say"
    if number.negative and not (amount.marked or LOSS.search(plain)):
        return f"[{alias}] shows a loss or a negative figure, which the sentence does not say"
    if number.named * amount.named < 0 and not amount.marked:
        said, shows = ("a loss", "a gain") if amount.named < 0 else ("a gain", "a loss")
        return f"it says {said}, but [{alias}] shows {shows}"
    if number.went * amount.went < 0:
        said, shows = ("rose", "fell") if number.went < 0 else ("fell", "rose")
        return f"it says the figure {said}, but [{alias}] says it {shows}"
    return None


def stated_scales(text: str) -> list[int]:
    """The scales a text states for its tables, in order: [1000000] for "(in millions)"."""
    return [UNITS["".join(words).lower()] for words in STATED.findall(text)]


def _scales(quote: str, passage: str, unit_above: str) -> tuple[int, ...]:
    """A quoted table's scale: stated in the quote, else nearest above it in its passage, else
    above the passage in its section, else anywhere in the passage; (1,) with none."""
    lines = "\n".join(_normalize(line) for line in passage.split("\n"))
    above = stated_scales(lines[: max(lines.find(_normalize(quote)), 0)])[-1:]
    found = stated_scales(quote) or above or stated_scales(unit_above) or stated_scales(passage)
    return tuple(found) or (1,)


def read_quote(quote: str, passage: str, unit_above: str = "") -> list[Number]:
    """The numbers of a quote from `passage`, as evidence: no year and no part of a date. A cell
    takes its table's scale; a percentage, a per-share figure and a number with its own scale word
    take none. Brackets mean a loss only in a row that reports a result, elsewhere a cost."""
    scales = _scales(quote, passage, unit_above)
    dates = [match.span() for match in DATE.finditer(quote)]
    per_share = PER_SHARE.search(quote) is not None
    result = "|" in quote and RESULT_ROW.search(quote) is not None
    found: list[Number] = []
    for match in NUMBER.finditer(quote):
        start, end = match.span()
        if YEAR.fullmatch(quote, start, end) or any(a <= start < b for a, b in dates):
            continue
        try:
            value = parse_amount(match[0])
        except ValueError:
            continue
        marked = PERCENT_MARK.match(quote, end) is not None
        whole = match["scale"] is not None
        cell = CELL_END.match(quote, end) is not None and not (marked or whole or per_share)
        before = quote[max(start - WINDOW, 0) : start]
        plain = cell and DOLLAR_SIGN.search(before) is None
        found.append(
            Number(
                value,
                True if marked else None if plain else False,
                scales if cell else (1,),
                per_share and not whole,
                result and BRACKET_OPEN.search(before) is not None,
                _named(quote, start),
                _went(quote, start, end),
            )
        )
    return found


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


@dataclass(frozen=True)
class Calculation:
    """What code computed from two facts of one unit (K1), so the answer model computes nothing."""

    inputs: tuple[str, str]  # the facts' ids: the earlier year first, or the lower of two companies
    difference: Decimal  # the second minus the first
    change: Decimal | None  # the difference in percent of the first; None unless both are above 0
    over_time: bool  # one company's two years: rise and fall words must match the difference

    @property
    def figures(self) -> list[tuple[Decimal, bool]]:
        """Its own figures, each with whether it is a percent: the difference, and the change. Its
        two values are its facts', which a sentence citing it cites too."""
        return [(self.difference, False)] + ([] if self.change is None else [(self.change, True)])


class Source(Protocol):
    """What the check reads from an answer's source: a chunk (text), a fact (value) or a
    calculation."""

    @property
    def chunk_id(self) -> str | None: ...

    @property
    def fact_id(self) -> str | None: ...

    @property
    def text(self) -> str: ...

    @property
    def value(self) -> Decimal | None: ...

    @property
    def calculation(self) -> Calculation | None: ...

    @property
    def unit_above(self) -> str:
        """The unit a chunk's table states above it, in its section; the model never reads it."""
        ...


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


def _numbers(
    alias: str, source: Source, quotes: Mapping[str, Sequence[str]], chunks: Mapping[str, str]
) -> list[Number]:
    """What a cited source holds: a fact's value, a calculation's figures as stated (a change of
    6.43 never backs "$6.4 billion"), or the numbers of its quotes that pass."""
    if source.value is not None:
        value = source.value
        if source.text.endswith("pure"):  # a ratio: 16.2% against a fact of 0.162
            return [Number(value, percent=True, scales=(1, 100))]
        named = (value > 0) - (value < 0)
        per_share = source.text.endswith("/shares")
        return [Number(value, per_share=per_share, negative=value < 0, named=named)]
    if source.calculation is not None:
        return [Number(n, percent=kind) for n, kind in source.calculation.figures]
    good = [
        quote
        for quote in quotes.get(alias, [])
        if citation_error(Quoted(source.chunk_id, None, quote), chunks, ()) is None
    ]
    return [n for quote in good for n in read_quote(quote, source.text, source.unit_above)]


def _direction(plain: str, amounts: Sequence[Amount]) -> int:
    """Which way a sentence's "from A to B" or "to B from A" goes: 1 up, -1 down, 0 no such pair."""
    for first, second in itertools.pairwise(amounts):
        before, between = plain[: first.start], plain[first.end : second.start]
        if first.percent != second.percent:
            continue
        if FROM.search(before) and re.search(r"\bto\b", between):
            low, high = abs(first.value), abs(second.value)
        elif TO.search(before) and re.search(r"\bfrom\b", between):
            low, high = abs(second.value), abs(first.value)
        else:
            continue
        return (high > low) - (high < low)
    return 0


def check_sentence(
    sentence: str, quotes: Mapping[str, Sequence[str]], sources: Mapping[str, Source]
) -> str | None:
    """Why a sentence of an answer fails, or None when it holds.

    It must cite at least one source id, such as [C2], and hold no other bracketed marker such as
    [12]; with no filing text among the sources it must not say what they leave out (SILENT); a
    cited chunk needs a quote under Sources that passes citation_error; a cited calculation (K1)
    needs both its facts cited beside it; and each amount in the sentence must match a number of
    its kind and scale that a cited source holds (Number), which the sentence must not turn
    around (_objection). `quotes` maps source ids to the quotes given for them; `sources` maps the
    ids the model was given (F1, C2, K1) to the sources.
    """
    if stray := STRAY.search(MARKER.sub("", sentence)):  # shown, it would cite nothing
        return f"{stray[0]} is not one of the sources"
    chunks = {s.chunk_id: s.text for s in sources.values() if s.chunk_id is not None}
    if not chunks and SILENT.search(sentence):  # before its citation, which would not excuse it
        return ABSENT
    aliases = cited(sentence)
    if not aliases:
        return "it cites no source"
    evidence: list[tuple[str, Number]] = []
    for alias in aliases:
        source = sources.get(alias)
        if source is None:
            return f"[{alias}] is not one of the sources"
        calculation = source.calculation
        if calculation is not None:  # every number still cites a fact
            if left := [f"[{fact}]" for fact in calculation.inputs if fact not in aliases]:
                facts = " and ".join(left)
                return f"[{alias}] is cited without {facts}, the facts it was calculated from"
        elif source.value is None:
            given = quotes.get(alias, [])
            good = [
                q
                for q in given
                if citation_error(Quoted(source.chunk_id, None, q), chunks, ()) is None
            ]
            if not good:
                return (
                    f"[{alias}] has no quote under Sources"
                    if not given
                    else f"[{alias}] the quote is not in chunk {source.chunk_id}"
                )
        evidence += [(alias, number) for number in _numbers(alias, source, quotes, chunks)]
    plain = MARKER.sub("", sentence)
    amounts = _amounts(plain)
    for amount in amounts:
        holders = [(alias, number) for alias, number in evidence if number.backs(amount)]
        if not holders:
            shown = f"{amount.value.normalize():,f}{'%' if amount.percent else ''}"
            return f"the amount {shown} is not in the sources it cites"
        objections = [_objection(alias, number, amount, plain) for alias, number in holders]
        if all(objections):
            return objections[0]
    said = bool(RISES.search(plain)) - bool(FALLS.search(plain))  # 0: neither, or both
    word = "rose" if said > 0 else "fell"
    for alias, source in sources.items():
        calculation = source.calculation
        # Cited or not, once both its facts are. Only between values above 0 (a change was
        # computed): a loss that "grew" fell.
        if (
            said
            and calculation
            and calculation.over_time
            and calculation.change is not None
            and all(fact in aliases for fact in calculation.inputs)
        ):
            shows = (calculation.difference > 0) - (calculation.difference < 0)
            if said != shows:
                change = {1: "a rise", -1: "a fall", 0: "no change"}[shows]
                return f"it says the figure {word}, but [{alias}] shows {change}"
    if said and (went := _direction(plain, amounts)) and said != went:
        return f"it says the figure {word}, but its amounts {'rise' if went > 0 else 'fall'}"
    if COMPARES.search(plain) and (missing := _unstated(plain, amounts, aliases, sources)):
        return UNSTATED + ", ".join(f"[{alias}]" for alias in missing)
    return None


def _unstated(
    plain: str, amounts: Sequence[Amount], aliases: Sequence[str], sources: Mapping[str, Source]
) -> list[str]:
    """The cited facts a comparing sentence does not state: the judge counts one only where its
    figure is stated."""
    stated = [amount.value for amount in amounts if not amount.percent]
    stated += numbers_in(plain)  # a bare figure: 6.11 in "from 6.11 to 6.63 USD/shares"
    return [
        alias
        for alias in aliases
        if (value := sources[alias].value) is not None
        and not (value and any(matches(amount, value) for amount in stated))
    ]


def _without(sentence: str, gone: Collection[str]) -> str:
    """The sentence with the citations in `gone` taken out of its markers."""

    def keep(marker: re.Match[str]) -> str:
        left = [alias for alias in re.split(r"\s*,\s*", marker[1]) if alias not in gone]
        return f"[{', '.join(left)}]" if left else ""

    return re.sub(r"\s+([.!?,;:])", r"\1", " ".join(MARKER.sub(keep, sentence).split()))


def pruned(
    sentence: str, quotes: Mapping[str, Sequence[str]], sources: Mapping[str, Source]
) -> tuple[str, int] | None:
    """The sentence without the citations that cannot back it (no such source, or no quote that
    holds), and how many went, when the rest still holds it: x06 (dev) cited C5 and C9, and only
    C9's quote was in its chunk."""
    chunks = {s.chunk_id: s.text for s in sources.values() if s.chunk_id is not None}

    def holds(alias: str) -> bool:
        source = sources.get(alias)
        if source is None or source.chunk_id is None:
            return source is not None
        quoted = [Quoted(source.chunk_id, None, quote) for quote in quotes.get(alias, [])]
        return any(citation_error(quote, chunks, ()) is None for quote in quoted)

    aliases = cited(sentence)
    bad = [alias for alias in aliases if not holds(alias)]
    if not bad or len(bad) == len(aliases):
        return None
    text = _without(sentence, bad)
    return (text, len(bad)) if check_sentence(text, quotes, sources) is None else None


def on_calculation(
    sentence: str, quotes: Mapping[str, Sequence[str]], sources: Mapping[str, Source]
) -> tuple[str, list[str]] | None:
    """The sentence without the cited facts it does not state, and those facts, when only they
    fail it and a calculation it cites on them states the comparison: an amount its difference or
    percent backs as any number does, no minus on a rise, and no word against its direction. The
    calculation's lines hold the facts' figures (r02, c19). None for any other sentence. The caller
    must keep those facts cited elsewhere, since the calculation's citation names theirs."""
    problem = check_sentence(sentence, quotes, sources)
    if problem is None or not problem.startswith(UNSTATED):
        return None
    plain = MARKER.sub("", sentence)
    amounts = _amounts(plain)
    aliases = cited(sentence)
    gone = _unstated(plain, amounts, aliases, sources)
    said = bool(MORE.search(plain)) - bool(LESS.search(plain))  # 0: neither, or both
    for alias in aliases:
        calculation = sources[alias].calculation
        if calculation is None or not set(gone) <= set(calculation.inputs):
            continue
        shows = (calculation.difference > 0) - (calculation.difference < 0)
        numbers = _numbers(alias, sources[alias], quotes, {})
        states = any(
            number.backs(amount)
            and _objection(alias, number, amount, plain) is None
            and not (amount.marked and number.value > 0)
            for amount in amounts
            for number in numbers
        )
        if states and said * shows >= 0:
            return _without(sentence, gone), gone
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

    The evidence and the match are check_sentence's; an amount that no cited source holds is left
    out.
    """
    chunks = {s.chunk_id: s.text for s in sources.values() if s.chunk_id is not None}
    evidence = [
        (alias, number)
        for alias in cited(sentence)
        if (source := sources.get(alias)) is not None
        for number in _numbers(alias, source, quotes, chunks)
    ]
    plain = MARKER.sub("", sentence)
    found: list[Figure] = []
    for amount in _amounts(plain):
        for alias, number in evidence:
            if number.backs(amount) and _objection(alias, number, amount, plain) is None:
                found.append(Figure(amount.text, alias, number.value))
                break
    return found
