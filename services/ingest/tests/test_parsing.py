"""parse_filing on two trimmed real 10-Ks (Apple, Freeport-McMoRan) and on small made-up filings.

The fixtures are the companies' 10-Ks from EDGAR, cut to item headings and the first blocks after
each (aapl-10k-2025.htm: 1,520,318 to 58,128 bytes; fcx-10k-2025.htm: 6,347,588 to 184,158).
"""

import gzip
import json
from pathlib import Path

import pytest

from filinglens_ingest.parsing import (
    Parsed,
    ParseError,
    Section,
    decode,
    parse_filing,
    text_lines,
)

FIXTURES = Path(__file__).with_name("fixtures")
SEC_CACHE = Path(__file__).parents[3] / ".cache" / "sec" / "Archives" / "edgar" / "data"
TEN_K_ITEMS = [
    *("1", "1A", "1B", "1C", "2", "3", "4", "5", "6", "7", "7A", "8"),
    *("9", "9A", "9B", "9C", "10", "11", "12", "13", "14", "15", "16"),
]


def page(*blocks: str) -> str:
    return f"<html><body>{''.join(blocks)}</body></html>"


def section(parsed: Parsed, item: str) -> Section:
    return next(s for s in parsed.sections if s.item == item)


def text(parsed: Parsed, item: str) -> str:
    found = section(parsed, item)
    return parsed.text[found.start : found.end]


def test_apple_10k_skips_its_contents_table_and_finds_every_item() -> None:
    parsed = parse_filing((FIXTURES / "aapl-10k-2025.htm").read_text(encoding="utf-8"), "10-K")
    assert [s.item for s in parsed.sections] == TEN_K_ITEMS
    assert parsed.missing == []
    assert section(parsed, "1A").title == "Risk Factors"
    assert text(parsed, "1A").startswith("Item 1A. Risk Factors\nThe following summarizes factors")
    # The contents table lists the items first; every section starts after it.
    assert parsed.text.index("Item 1A.") < parsed.sections[0].start


def test_freeport_10k_with_combined_items() -> None:
    parsed = parse_filing((FIXTURES / "fcx-10k-2025.htm").read_text(encoding="utf-8"), "10-K")
    items = [s.item for s in parsed.sections]
    assert {"2", "7A"}.isdisjoint(items)  # "Items 1. and 2.", "Items 7. and 7A."
    assert parsed.missing == []  # 7A counts as found through the combined heading
    assert section(parsed, "1").title == "Business; Properties"
    assert text(parsed, "7").startswith("Items 7. and 7A.")
    assert text(parsed, "1A").startswith("Item 1A. Risk Factors.\nThis report contains")


def test_contents_rows_are_skipped_and_page_headers_do_not_split_an_item() -> None:
    rows = [("1", "Business"), ("1A", "Risk Factors"), ("7", "MD&amp;A"), ("8", "Statements")]
    document = page(
        '<div style="display: none"><ix:header>Item 1A hidden fact</ix:header></div>',
        "<p>Table of Contents</p><table>",
        *(f"<tr><td>Item {i}.</td><td>{t}</td><td>{n}</td></tr>" for n, (i, t) in enumerate(rows)),
        "</table>",
        "<p>Item 1. Business</p><p>We make widgets.</p>",
        "<p>Item 1A. Risk Factors</p><p>Widgets break.</p>",
        "<p>12</p><p>Item 1A</p><p>Rates move.</p>",  # a page number, then a running header
        "<div>Item 7. Management&#8217;s Discussion</div><p>Sales grew.</p>",
        "<p>Item 8. Financial Statements</p><table><tr><td>Revenue</td><td></td><td>$</td>"
        "<td>391,035</td></tr></table>",
    )
    parsed = parse_filing(document, "10-K")
    assert [s.item for s in parsed.sections] == ["1", "1A", "7", "8"]
    assert parsed.missing == ["7A"]
    assert "hidden fact" not in parsed.text
    assert text(parsed, "1A") == "Item 1A. Risk Factors\nWidgets break.\nItem 1A\nRates move."
    assert text(parsed, "8") == "Item 8. Financial Statements\nRevenue | $ | 391,035"


def row(*cells: str) -> str:
    """A table row as Microsoft's and Prologis' 10-Ks write it: each cell in a <p>, on its own
    line of the source."""
    wrapped = (
        f'<td style="vertical-align:bottom"><p style="margin:0"><span>{cell}</span></p></td>'
        for cell in cells
    )
    return "<tr>\n     " + "\n     ".join(wrapped) + "\n    </tr>"


@pytest.mark.parametrize(
    ("cells", "line"),
    [
        # Microsoft: the executive officers' table lost each age.
        (("Judson B. Althoff", "&#160;", "53", "&#160;", "Chief Executive Officer"),
         "Judson B. Althoff | 53 | Chief Executive Officer"),
        (("Bradford L. Smith", "&#160;", "67", "&#160;", "Vice Chair and President"),
         "Bradford L. Smith | 67 | Vice Chair and President"),
        # Prologis: its top customers lost their share of the total.
        (("1. Amazon", "6.3", "35", "&#160;", "1. Amazon", "5.3", "48"),
         "1. Amazon | 6.3 | 35 | 1. Amazon | 5.3 | 48"),
        (("Rental expenses", "(488", ")", "(445", ")"), "Rental expenses | (488 | ) | (445 | )"),
        # The tagged numbers of an inline XBRL filing.
        (("Revenue", "<ix:nonFraction>365</ix:nonFraction>", "1,234"), "Revenue | 365 | 1,234"),
        # "LLC" reads as a Roman numeral outside a table.
        (("Prologis", "LLC"), "Prologis | LLC"),
    ],
)  # fmt: skip
def test_a_row_of_wrapped_cells_is_one_line_with_every_digit(
    cells: tuple[str, ...], line: str
) -> None:
    assert text_lines(page("<table>", row(*cells), "</table>")) == [line]


@pytest.mark.parametrize(
    ("cell", "text"),
    [
        ("<div>Total<br>revenue</div>", "Total revenue"),
        ("<div>Total</div><div>revenue</div>", "Total revenue"),
        ("<p>Total</p><p>revenue</p>", "Total revenue"),
        ("<div>Total<br/>revenue</div>", "Total revenue"),
    ],
)
def test_a_cell_keeps_its_blocks_on_one_line(cell: str, text: str) -> None:
    document = page(f"<table><tr><td>{cell}</td><td><div>365</div></td></tr></table>")
    assert text_lines(document) == [f"{text} | 365"]


def test_a_line_break_in_the_source_is_a_space() -> None:
    assert text_lines(page("<p>Net sales\nrose</p>\n<p>Costs fell.</p>")) == [
        "Net sales rose",
        "Costs fell.",
    ]


def test_page_furniture_goes_outside_tables_and_a_contents_link_goes_anywhere() -> None:
    document = page(
        "<p>12</p><p>iv</p><p>LLC</p><p>Net sales rose.</p>",
        "<table><tr><td>Table of Contents</td></tr><tr><td>Revenue</td><td>12</td></tr></table>",
    )
    assert text_lines(document) == ["Net sales rose.", "Revenue | 12"]


def test_a_table_inside_a_cell_keeps_its_rows_and_an_unclosed_cell_ends_at_the_row() -> None:
    nested = "<table><tr><td>Inner</td></tr><tr><td>7</td></tr></table>"
    assert text_lines(page(f"<table><tr><td>Outer{nested}</td></tr></table>")) == [
        "Outer",
        "Inner",
        "7",
    ]
    unclosed = "<table><tr><td><p>A</p><td><p>7</p></tr><tr><td>B</tr></table><p>After</p>"
    assert text_lines(page(unclosed)) == ["A | 7", "B", "After"]


@pytest.mark.skipif(not SEC_CACHE.is_dir(), reason="needs the local SEC cache; CI has none")
@pytest.mark.parametrize(
    ("name", "line"),
    [
        ("msft-20260630.htm.gz", "Bradford L. Smith | 67 | Vice Chair and President"),
        ("pld-20251231.htm.gz", "5. Walmart | 0.8 | 5 | 5. DSV | 1.2 | 14"),
    ],
)
def test_the_filings_the_review_found_keep_their_rows(name: str, line: str) -> None:
    document = next(SEC_CACHE.glob(f"*/*/{name}")).read_bytes()
    assert line in text_lines(decode(gzip.decompress(document)))


def test_a_missing_item_is_listed_and_one_reading_not_applicable_is_found() -> None:
    document = page(
        "<p>Item 1. Business</p><p>Widgets.</p>",
        "<p>Item 1A. Risk Factors</p><p>Risks.</p>",
        "<p>Item 7. MD&amp;A</p><p>Sales grew.</p>",
        "<p>Item 7A. Market Risk</p><p>Not applicable.</p>",
        "<p>Item 9. Changes in Accountants</p><p>None.</p>",
    )
    parsed = parse_filing(document, "10-K")
    assert [s.item for s in parsed.sections] == ["1", "1A", "7", "7A", "9"]
    assert parsed.missing == ["8"]
    assert text(parsed, "7A") == "Item 7A. Market Risk\nNot applicable."


def test_a_filing_without_any_required_item_fails_with_the_reason() -> None:
    document = page("<p>Exhibit 99.1</p><p>Press release.</p>", "<p>Item 9B. Other</p>")
    with pytest.raises(ParseError, match=r"No required item found; looked for items 1, 1A, 7"):
        parse_filing(document, "10-K")
    with pytest.raises(ParseError, match="only 10-K and 10-Q"):
        parse_filing(document, "8-K")


# Trimmed 10-Ks whose Items 7 or 8 only point to a separate financial section inside a later item
# (memory.md, 2026-10-18): that section's own headings take the items, in one range each.
SEPARATE = [
    (
        "jpm-10k-2025.htm",
        "15",
        {
            "7": "Management\N{RIGHT SINGLE QUOTATION MARK}s discussion and analysis\n",
            "8": "Report of Independent Registered Public Accounting Firm\n",
        },
    ),
    (
        "cvx-10k-2025.htm",
        "14",
        {
            "7": "Management\N{RIGHT SINGLE QUOTATION MARK}s Discussion and Analysis of Financial"
            " Condition and Results of Operations\n",
            "8": "Management\N{RIGHT SINGLE QUOTATION MARK}s Responsibility for Financial"
            " Statements\n",
        },
    ),
    ("nvda-10k-2026.htm", "15", {"8": "Report of Independent Registered Public Accounting Firm\n"}),
    ("pld-10k-2025.htm", "16", {"8": "REPORT OF INDEPENDENT REGISTERED PUBLIC ACCOUNTING FIRM\n"}),
]


@pytest.mark.parametrize(("name", "holder", "moved"), SEPARATE)
def test_a_separate_financial_section_takes_the_items_that_point_to_it(
    name: str, holder: str, moved: dict[str, str]
) -> None:
    parsed = parse_filing((FIXTURES / name).read_text(encoding="utf-8"), "10-K")
    items = [s.item for s in parsed.sections]
    assert parsed.missing == [] and len(items) == len(set(items))  # one range per item
    after = items.index(holder) + 1
    assert items[after : after + len(moved)] == list(moved)  # cut from the item that held them
    for item, opening in moved.items():
        assert text(parsed, item).startswith(opening)
    heads = [parsed.text[s.start : s.start + 8].upper() for s in parsed.sections]
    assert not any(head.startswith(f"ITEM {item}.") for item in moved for head in heads)


@pytest.mark.parametrize(
    ("name", "risk"),
    [
        ("jpm-10k-2025.htm", "MARKET RISK MANAGEMENT"),
        ("cvx-10k-2025.htm", "Financial and Derivative"),
    ],
)
def test_market_risk_inside_the_discussion_stays_in_item_7_and_7a_stays_the_pointer(
    name: str, risk: str
) -> None:
    parsed = parse_filing((FIXTURES / name).read_text(encoding="utf-8"), "10-K")
    assert f"\n{risk}" in text(parsed, "7")
    assert text(parsed, "7A").startswith(
        "Item 7A. Quantitative and Qualitative Disclosures About Market Risk"
    )


def test_a_short_item_8_with_no_financial_section_after_it_stays_as_it_is() -> None:
    document = page(
        "<p>Item 1. Business</p><p>Widgets.</p>",
        "<p>Item 1A. Risk Factors</p><p>Risks.</p>",
        "<p>Item 7. MD&amp;A</p><p>Sales grew.</p>",
        "<p>Item 8. Financial Statements</p><p>See the annual report to shareholders.</p>",
        "<p>Item 15. Exhibits</p><p>Exhibit 13. Annual report.</p>",
    )
    parsed = parse_filing(document, "10-K")
    assert [s.item for s in parsed.sections] == ["1", "1A", "7", "8", "15"]


REPORT = "<p>Report of Independent Registered Public Accounting Firm</p>"


def short_item_8(holder: str, *rest: str) -> str:
    """A 10-K with a short Item 8, then Items 9, 9A and 9B, `holder` with an auditor's report."""
    report = f"{REPORT}<p>We audited internal control.</p>"
    return page(
        "<p>Item 1. Business</p><p>Widgets.</p>",
        "<p>Item 1A. Risk Factors</p><p>Risks.</p>",
        "<p>Item 7. MD&amp;A</p><p>Sales grew.</p>",
        "<p>Item 7A. Market Risk</p><p>Rates.</p>",
        "<p>Item 8. Financial Statements</p><p>See the pages after Item 15.</p>",
        "<p>Item 9. Changes in Accountants</p><p>None.</p>",
        report if holder == "9" else "",
        "<p>Item 9A. Controls and Procedures</p><p>Controls work.</p>",
        report if holder == "9A" else "",
        "<p>Item 9B. Other Information</p><p>None.</p>",
        *rest,
    )


@pytest.mark.parametrize("holder", ["9", "9A"])
def test_item_8_opens_past_items_9_and_9a_never_inside_them(holder: str) -> None:
    """Review finding 4: Item 8 took 9A's report on internal control, and the statements stayed
    in Item 15."""
    statements = f"<p>Item 15. Exhibits</p><p>Exhibit list.</p>{REPORT}<p>We audited sales.</p>"
    parsed = parse_filing(short_item_8(holder, statements), "10-K")
    assert [s.item for s in parsed.sections] == [
        *("1", "1A", "7", "7A", "9", "9A", "9B", "15", "8"),
    ]
    assert text(parsed, "8").endswith("We audited sales.")
    assert text(parsed, holder).endswith("We audited internal control.")


@pytest.mark.parametrize("holder", ["9", "9A"])
def test_item_8_stays_short_when_only_items_9_or_9a_hold_a_report(holder: str) -> None:
    parsed = parse_filing(short_item_8(holder, "<p>Item 15. Exhibits</p><p>Exhibits.</p>"), "10-K")
    assert [s.item for s in parsed.sections] == [
        *("1", "1A", "7", "7A", "8", "9", "9A", "9B", "15"),
    ]
    assert text(parsed, "8") == "Item 8. Financial Statements\nSee the pages after Item 15."
    assert text(parsed, holder).endswith("We audited internal control.")


@pytest.mark.parametrize("following", ["Item 9. Changes", "Item 9A. Controls and Procedures"])
def test_a_full_item_8_ends_where_the_next_item_starts(following: str) -> None:
    document = page(
        "<p>Item 7. MD&amp;A</p><p>Sales grew.</p>",
        "<p>Item 8. Financial Statements</p>",
        "<p>Net sales rose.</p>" * 200,
        f"<p>{following}</p><p>None.</p>",
    )
    parsed = parse_filing(document, "10-K")
    assert text(parsed, "8").endswith("Net sales rose.")
    assert text(parsed, following.split(".")[0].removeprefix("Item ")).startswith(following)


@pytest.mark.skipif(not SEC_CACHE.is_dir(), reason="needs the local SEC cache; CI has none")
def test_the_other_cached_10ks_keep_their_section_ranges() -> None:
    """The 26 cached golden-set 10-Ks without a separate financial section, as the parser cut them
    once table rows kept their cells (section-ranges.json, 2026-11-06). That fix moved the offsets
    and changed no filing's list of items."""
    pinned = json.loads((FIXTURES / "section-ranges.json").read_text(encoding="utf-8"))
    for folder, ranges in pinned.items():
        document = next(SEC_CACHE.glob(f"*/{folder}/*.htm.gz")).read_bytes()
        parsed = parse_filing(decode(gzip.decompress(document)), "10-K")
        assert [[s.item, s.start, s.end] for s in parsed.sections] == ranges, folder


def test_10q_items_carry_their_part() -> None:
    document = page(
        "<p>PART I. FINANCIAL INFORMATION</p>",
        "<p>Item 1. Financial Statements</p><p>Balance sheet.</p>",
        "<p>Item 2. Management's Discussion</p><p>Quarter.</p>",
        "<p>Item 3. Market Risk</p><p>Rates.</p>",
        "<p>Item 4. Controls and Procedures</p><p>Effective.</p>",
        "<p>PART II. OTHER INFORMATION</p>",
        "<p>Item 1. Legal Proceedings</p><p>None.</p>",
        "<p>Item 1A. Risk Factors</p><p>No material changes.</p>",
        "<p>Item 6. Exhibits</p><p>Exhibit 31.1</p>",
    )
    parsed = parse_filing(document, "10-Q")
    assert [s.item for s in parsed.sections] == [
        "I-1",
        "I-2",
        "I-3",
        "I-4",
        "II-1",
        "II-1A",
        "II-6",
    ]
    assert parsed.missing == []
    assert section(parsed, "II-1A").title == "Risk Factors"
