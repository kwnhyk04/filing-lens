"""Filing text and item sections from a 10-K's or 10-Q's (inline XBRL) HTML.

The text has one line per block element. A table row becomes one line, its cells joined by " | ",
so tables lose their layout (a known limit, docs/memory.md). Items are found by their headings: the
table of contents lists them first, in rising order, so item lines up to the first step back
(where the body starts over at Item 1) are skipped. Each item's section starts at its first heading
after that and runs to the next item's heading; the last one runs to the end of the document.
Running page headers ("Item 1A" atop each page) come after their item's heading and change nothing.
A heading whose item reads "Not applicable" still counts as found. Titles are the form's own.
Some 10-Ks keep MD&A or the statements in a separate financial section inside a later item, and
their Items 7 or 8 only point there (JPM, CVX, NVDA, PLD): that section's own headings take the
items, and the pointers keep no range, so each item is still one range.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from html.parser import HTMLParser
from itertools import accumulate

from filinglens_core.errors import FilingLensError

BLOCK_TAGS = frozenset(
    {
        *("address", "article", "blockquote", "br", "center", "dd", "div", "dl", "dt", "h1"),
        *("h2", "h3", "h4", "h5", "h6", "hr", "li", "ol", "p", "pre", "section", "table"),
        *("tbody", "tfoot", "thead", "tr", "ul"),
    }
)
CELL_TAGS = frozenset({"td", "th"})
HIDDEN_TAGS = frozenset({"head", "script", "style", "ix:header"})
VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param"}
    | {"source", "track", "wbr"}
)
CELL = "\x1f"  # marks a cell boundary until lines are cleaned
INVISIBLE: dict[int, None] = dict.fromkeys((0x200B, 0x200C, 0x200D, 0xFEFF))  # zero-width
NOISE = re.compile(r"\d{1,3}|[ivxlc]{1,6}|table of contents", re.IGNORECASE)  # page furniture

# Item titles as the forms give them, in item order; 10-Q keys carry their part.
TITLES = {
    "10-K": {
        "1": "Business",
        "1A": "Risk Factors",
        "1B": "Unresolved Staff Comments",
        "1C": "Cybersecurity",
        "2": "Properties",
        "3": "Legal Proceedings",
        "4": "Mine Safety Disclosures",
        "5": "Market for Registrant's Common Equity, Related Stockholder Matters and Issuer"
        " Purchases of Equity Securities",
        "6": "[Reserved]",
        "7": "Management's Discussion and Analysis of Financial Condition and Results of"
        " Operations",
        "7A": "Quantitative and Qualitative Disclosures About Market Risk",
        "8": "Financial Statements and Supplementary Data",
        "9": "Changes in and Disagreements with Accountants on Accounting and Financial Disclosure",
        "9A": "Controls and Procedures",
        "9B": "Other Information",
        "9C": "Disclosure Regarding Foreign Jurisdictions that Prevent Inspections",
        "10": "Directors, Executive Officers and Corporate Governance",
        "11": "Executive Compensation",
        "12": "Security Ownership of Certain Beneficial Owners and Management and Related"
        " Stockholder Matters",
        "13": "Certain Relationships and Related Transactions, and Director Independence",
        "14": "Principal Accountant Fees and Services",
        "15": "Exhibits and Financial Statement Schedules",
        "16": "Form 10-K Summary",
    },
    "10-Q": {
        "I-1": "Financial Statements",
        "I-2": "Management's Discussion and Analysis of Financial Condition and Results of"
        " Operations",
        "I-3": "Quantitative and Qualitative Disclosures About Market Risk",
        "I-4": "Controls and Procedures",
        "II-1": "Legal Proceedings",
        "II-1A": "Risk Factors",
        "II-2": "Unregistered Sales of Equity Securities and Use of Proceeds",
        "II-3": "Defaults Upon Senior Securities",
        "II-4": "Mine Safety Disclosures",
        "II-5": "Other Information",
        "II-6": "Exhibits",
    },
}
REQUIRED = {"10-K": ("1", "1A", "7", "7A", "8"), "10-Q": ("I-1", "I-2", "I-3", "II-1A")}
MAX_HEADING = 200  # characters; a longer line is prose that mentions an item
CONTENTS_MIN = 4  # rising item rows before a step back that make a table of contents

HEADING = re.compile(  # "(" stops it: a cover page's "Part III (Items 10-14)" is no heading
    r"(?:part\s+(?P<part>iv|i{1,3})\b[^\w(]*)?"
    r"items?\s*(?P<item>\d{1,2}(?:\s?[a-c])?)\b"
    r"(?:\s*\.?\s*(?:,|and|&)\s*(?P<also>\d{1,2}(?:\s?[a-c])?)\b)?",  # "Items 1 and 2"
    re.IGNORECASE,
)
PART = re.compile(r"part\s+(iv|i{1,3})\b", re.IGNORECASE)
POINTER_MAX = 2_000  # characters: an Item 7 or 8 this short only points to the content
APOSTROPHE = "['\N{RIGHT SINGLE QUOTATION MARK}]"
# Whole lines that open a separate financial section's MD&A and statements, in item order; a
# contents row ("...analysis:", "...Firm (PCAOB ID: 238)") never matches a whole line.
OPENS = {
    "7": re.compile(
        rf"management{APOSTROPHE}s discussion and analysis"
        r"(?: of financial condition and results of operations)?\.?",
        re.IGNORECASE,
    ),
    "8": re.compile(
        r"(?:report of independent registered public accounting firm"
        rf"|management{APOSTROPHE}s responsibility for (?:the )?(?:consolidated )?financial"
        r" statements)\.?",
        re.IGNORECASE,
    ),
}


class ParseError(FilingLensError):
    """The document has no section that parse can use; retrying cannot change that."""

    code = "unparseable"


@dataclass(frozen=True)
class Section:
    item: str  # 10-K: "1A"; 10-Q: "II-1A" (part and item)
    title: str
    start: int  # offsets in Parsed.text
    end: int


@dataclass(frozen=True)
class Parsed:
    text: str
    sections: list[Section]
    missing: list[str]  # required items without a heading, in item order


@dataclass(frozen=True)
class _Heading:
    line: int
    key: str
    also: str | None  # the second item of a combined heading, such as "Items 1 and 2"


class _Text(HTMLParser):
    """Collects text: block tags break lines, cells are marked, hidden elements are dropped."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden: str | None = None  # tag of the hidden element being skipped
        self._depth = 0  # how deep that tag nests inside itself

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._hidden is not None:
            self._depth += tag == self._hidden
        elif tag in VOID_TAGS:  # no end tag follows, so it can open nothing
            if tag in BLOCK_TAGS:
                self.parts.append("\n")
        elif tag in HIDDEN_TAGS or "display:none" in "".join(
            (dict(attrs).get("style") or "").lower().split()
        ):
            self._hidden, self._depth = tag, 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in CELL_TAGS:
            self.parts.append(CELL)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._hidden is None and tag in BLOCK_TAGS:  # <br/>; an empty <div/> holds nothing
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._hidden is not None:
            if tag == self._hidden:
                self._depth -= 1
                if not self._depth:
                    self._hidden = None
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._hidden is None:
            self.parts.append(data)


def decode(document: bytes) -> str:
    """EDGAR documents are UTF-8, or Windows-1252 in older filings."""
    try:
        return document.decode("utf-8")
    except UnicodeDecodeError:
        return document.decode("cp1252", errors="replace")


def text_lines(html: str) -> list[str]:
    """The document's text, one block per line, without empty lines and page furniture."""
    parser = _Text()
    parser.feed(html)
    parser.close()
    lines: list[str] = []
    for raw in "".join(parser.parts).translate(INVISIBLE).split("\n"):
        cells = (" ".join(cell.split()) for cell in raw.split(CELL))
        line = " | ".join(cell for cell in cells if cell)
        if line and not NOISE.fullmatch(line):
            lines.append(line)
    return lines


def parse_filing(html: str, form: str) -> Parsed:
    """Split a 10-K or 10-Q into item sections; raises ParseError when no required item is found."""
    kind = "10-K" if form.startswith("10-K") else "10-Q" if form.startswith("10-Q") else None
    if kind is None:
        raise ParseError(f"Cannot parse form {form}: only 10-K and 10-Q.")
    lines = text_lines(html)
    titles = TITLES[kind]
    headings = _headings(lines, kind)
    chosen: dict[str, _Heading] = {}
    for heading in headings[_contents_length(headings, list(titles)) :]:
        chosen.setdefault(heading.key, heading)  # the first heading of each item in the body
    found = set(chosen) | {h.also for h in chosen.values() if h.also}
    required = REQUIRED[kind]
    if not found.intersection(required):
        raise ParseError(f"No required item found; looked for items {', '.join(required)}.")

    text = "\n".join(lines)
    starts = list(accumulate((len(line) + 1 for line in lines), initial=0))
    ordered = sorted(chosen.values(), key=lambda h: h.line)
    sections: list[Section] = []
    for heading, following in zip(ordered, [*ordered[1:], None], strict=True):
        start = starts[heading.line]
        end = starts[following.line] - 1 if following else len(text)
        title = titles[heading.key] + (f"; {titles[heading.also]}" if heading.also else "")
        sections.append(Section(heading.key, title, start, start + len(text[start:end].rstrip())))
    if kind == "10-K":
        sections = _financial_section(sections, lines, starts, text, titles)
    return Parsed(text, sections, [item for item in required if item not in found])


def _financial_section(
    sections: list[Section],
    lines: list[str],
    starts: list[int],
    text: str,
    titles: Mapping[str, str],
) -> list[Section]:
    """Items 7 and 8 that only point elsewhere take the first opening line of theirs after the
    pointers (8 after 7's). Each runs to the next one, or to the end of the item that held it,
    which keeps its part before them; market risk inside MD&A stays in 7, and 7A as it is."""
    pointers = [s for s in sections if s.item in OPENS and s.end - s.start < POINTER_MAX]
    found: dict[str, int] = {}  # item -> offset of its opening line
    after = max((s.end for s in pointers), default=len(text))
    for item, opening in OPENS.items():
        if any(s.item == item for s in pointers):
            later = (n for n, line in enumerate(lines) if starts[n] > after)
            opened = next((n for n in later if opening.fullmatch(lines[n])), None)
            if opened is not None:
                found[item] = after = starts[opened]
    cuts = sorted((start, item) for item, start in found.items())
    split: list[Section] = []
    for section in sections:
        if section.item in found:  # a pointer whose item moved: its lines name pages, no more
            continue
        inside = [(start, item) for start, item in cuts if section.start < start < section.end]
        ends = [start for start, _ in inside] + [section.end]
        pieces = [
            (section.item, section.title, section.start),
            *((i, titles[i], s) for s, i in inside),
        ]
        for (item, title, start), end in zip(pieces, ends, strict=True):
            split.append(Section(item, title, start, start + len(text[start:end].rstrip())))
    return split


def _headings(lines: list[str], kind: str) -> list[_Heading]:
    """Every line that starts with an item of this form, in document order."""
    valid = TITLES[kind]
    part = "I"  # 10-Q items repeat across parts; a "Part II" line switches over
    headings: list[_Heading] = []
    for number, line in enumerate(lines):
        if part_line := PART.match(line):
            part = part_line.group(1).upper()
        match = HEADING.match(line) if len(line) <= MAX_HEADING else None
        if match is None:
            continue
        if kind == "10-Q":
            part = (match.group("part") or part).upper()
        prefix = f"{part}-" if kind == "10-Q" else ""
        key = prefix + match.group("item").replace(" ", "").upper()
        also = match.group("also")
        also_key = prefix + also.replace(" ", "").upper() if also else None
        if key in valid:
            headings.append(_Heading(number, key, also_key if also_key in valid else None))
    return headings


def _contents_length(headings: list[_Heading], order: list[str]) -> int:
    """How many leading headings belong to the table of contents (and anything before it).

    The contents end at the first step back in item order that follows at least CONTENTS_MIN
    rising rows, so a stray item line on the cover page cannot end them early. Without such a
    step back there is no table of contents.
    """
    rank = {key: n for n, key in enumerate(order)}
    run_start = 0
    for n in range(1, len(headings)):
        if rank[headings[n].key] < rank[headings[n - 1].key]:
            if n - run_start >= CONTENTS_MIN:
                return n
            run_start = n
    return 0
