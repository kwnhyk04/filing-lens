"""parse_filing on two trimmed real 10-Ks (Apple, Freeport-McMoRan) and on small made-up filings.

The fixtures are the companies' 10-Ks from EDGAR, cut to item headings and the first blocks after
each (aapl-10k-2025.htm: 1,520,318 to 58,128 bytes; fcx-10k-2025.htm: 6,347,588 to 184,158).
"""

from pathlib import Path

import pytest

from filinglens_ingest.parsing import Parsed, ParseError, Section, parse_filing

FIXTURES = Path(__file__).with_name("fixtures")
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
