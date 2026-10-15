"""Answer post-validation: citations quote their chunk; amounts parse and match within 0.5%."""

from dataclasses import dataclass
from decimal import Decimal

import pytest

from filinglens_llm.validate import amounts_match, citation_error, parse_amount

CHUNK = (
    "Net sales rose 6% to $416.2 billion.\n"
    'The Company\N{RIGHT SINGLE QUOTATION MARK}s gross margin was 46.9%, and "Services" grew.'
)
CHUNKS = {"c-1": CHUNK}
FACTS = {"f-1"}


@dataclass
class Cite:
    quote: str
    chunk_id: str | None = None
    fact_id: str | None = None


@pytest.mark.parametrize(
    "quote",
    [
        "Net sales rose 6% to $416.2 billion.",  # verbatim
        "Net  sales\N{NO-BREAK SPACE}rose 6%",  # a doubled space and a no-break space
        "billion. The Company's gross margin",  # the line break as a space, a straight apostrophe
        # Curly quotes for straight ones.
        "and \N{LEFT DOUBLE QUOTATION MARK}Services\N{RIGHT DOUBLE QUOTATION MARK} grew.",
        " 46.9%,\t",  # whitespace around it
    ],
)
def test_a_quote_differing_only_in_whitespace_or_quote_style_passes(quote: str) -> None:
    assert citation_error(Cite(quote, chunk_id="c-1"), CHUNKS, FACTS) is None


@pytest.mark.parametrize(
    "quote",
    [
        "Net sales rose 7% to $416.2 billion.",  # a digit
        "$416.3 billion",  # a digit
        "Net sales fell 6%",  # a word
        "net sales rose",  # the letter case of a word
        "Net sales rose 6 % to",  # a space inside a number
    ],
)
def test_a_quote_with_a_changed_word_or_digit_fails(quote: str) -> None:
    error = citation_error(Cite(quote, chunk_id="c-1"), CHUNKS, FACTS)
    assert error == "the quote is not in chunk c-1"


def test_a_citation_needs_a_quote_and_a_source_the_answer_was_given() -> None:
    assert citation_error(Cite(" \n", chunk_id="c-1"), CHUNKS, FACTS) == "the quote is empty"
    error = citation_error(Cite("Net sales", chunk_id="c-9"), CHUNKS, FACTS)
    assert error == "chunk c-9 is not among the answer's sources"
    assert citation_error(Cite("Revenues 416,161", fact_id="f-1"), CHUNKS, FACTS) is None
    error = citation_error(Cite("Revenues", fact_id="f-9"), CHUNKS, FACTS)
    assert error == "fact f-9 is not among the answer's sources"
    error = citation_error(Cite("Revenues"), CHUNKS, FACTS)
    assert error == "the citation names no chunk and no fact"


@pytest.mark.parametrize(
    ("text", "scale", "expected"),
    [
        ("$4.2 billion", None, "4200000000"),
        ("4,213 million", None, "4213000000"),
        ("4,213", "millions", "4213000000"),  # a figure from a table "(in millions)"
        ("4,213,000", "thousands", "4213000000"),  # the same figure "(in thousands)"
        ("(1,234)", None, "-1234"),  # an accounting negative
        ("$(4.2) billion", None, "-4200000000"),
        ("($4.2 billion)", None, "-4200000000"),
        ("\N{MINUS SIGN}1,234.5", None, "-1234.5"),
        ("-$12", "Thousand", "-12000"),
    ],
)
def test_amounts_parse_with_their_scale_and_sign(
    text: str, scale: str | None, expected: str
) -> None:
    assert parse_amount(text, scale) == Decimal(expected)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$4.2B", "4200000000"),
        ("$4.2 b", "4200000000"),
        ("$4.2bn", "4200000000"),
        ("$4.2 BN", "4200000000"),
        ("4,213M", "4213000000"),
        ("4,213 m", "4213000000"),
        ("350K", "350000"),
        ("350 k", "350000"),
        ("1.2T", "1200000000000"),
        ("1.2 t", "1200000000000"),
        ("($4.2B)", "-4200000000"),
    ],
)
def test_abbreviations_read_in_either_case_with_or_without_a_space(
    text: str, expected: str
) -> None:
    assert parse_amount(text) == Decimal(expected)


@pytest.mark.parametrize(
    ("text", "scale"),
    [
        ("about $4.2B", None),  # prose: step 6 finds the amounts in answer text first
        ("4.2 kb", None),
        ("", None),
        ("(1,234", None),
        ("1.234,5", None),
        ("4.2 billion", "millions"),  # two scales
        ("4.2B", "millions"),
        ("12", "dozens"),
    ],
)
def test_anything_else_is_not_an_amount(text: str, scale: str | None) -> None:
    with pytest.raises(ValueError, match=r"amount|scale"):
        parse_amount(text, scale)


def test_amounts_match_within_half_a_percent_and_the_sign_counts() -> None:
    reported = parse_amount("4,213", scale="millions")
    assert amounts_match(parse_amount("$4.2 billion"), reported)  # 0.31% off
    assert not amounts_match(parse_amount("$4.1 billion"), reported)  # 2.7% off
    assert not amounts_match(parse_amount("4,213", scale="thousands"), reported)
    assert amounts_match(parse_amount("(4.2) billion"), -reported)
    assert not amounts_match(parse_amount("$4.2 billion"), -reported)
    assert amounts_match(Decimal(1005), Decimal(1000))
    assert not amounts_match(Decimal(1006), Decimal(1000))
    assert amounts_match(Decimal(0), Decimal(0))
    assert not amounts_match(Decimal(1), Decimal(0))
