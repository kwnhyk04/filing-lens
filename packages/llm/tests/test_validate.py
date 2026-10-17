"""Answer post-validation: citations quote their chunk; amounts parse and match within 0.5%."""

from dataclasses import dataclass
from decimal import Decimal

import pytest

from filinglens_llm.validate import (
    amounts_match,
    check_sentence,
    citation_error,
    find_amounts,
    parse_amount,
    split_sentences,
)

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


@pytest.mark.parametrize(
    ("text", "amounts"),
    [
        ("Revenue was about $4.2B in fiscal 2025.", [(Decimal(4_200_000_000), False)]),
        (
            "It earned $416.2 billion, up 6.4%.",
            [(Decimal(416_200_000_000), False), (Decimal("6.4"), True)],
        ),
        ("Backlog reached 4,213 million.", [(Decimal(4_213_000_000), False)]),
        (
            "A net loss of $(1,234) and 12 percent margins.",
            [(Decimal(-1234), False), (Decimal(12), True)],
        ),
        ("The 10-K for fiscal 2025 covers Item 7A and 3 segments.", []),  # no amount at all
        (
            "Diluted EPS was $6.08 on 15,004,697 thousand shares.",
            [(Decimal("6.08"), False), (Decimal(15_004_697_000), False)],
        ),
    ],
)
def test_the_finder_pulls_every_amount_out_of_answer_text_but_no_years_or_items(
    text: str, amounts: list[tuple[Decimal, bool]]
) -> None:
    assert find_amounts(text) == amounts


@dataclass
class Src:
    text: str
    chunk_id: str | None = None
    fact_id: str | None = None
    value: Decimal | None = None


SOURCES = {
    "C1": Src(CHUNK, chunk_id="c-1"),
    "F1": Src("416,161,000,000 USD", fact_id="f-1", value=Decimal(416_161_000_000)),
}
QUOTES = {"F1": ["416,161,000,000 USD"], "C1": ["Net sales rose 6% to $416.2 billion."]}


@pytest.mark.parametrize(
    ("sentence", "problem"),
    [
        ("Net sales were $416.2 billion [F1].", None),  # 0.01% from the fact
        ("Net sales were $416 billion, up 6% [C1].", None),  # both in the quote
        ("Both say $416.2 billion [F1, C1].", None),
        ("Net sales were $461.2 billion [F1].", "the amount 461,200,000,000 is not in the sources"),
        ("Net sales grew 60% [C1].", "the amount 60% is not in the sources"),
        ("Net sales were $416.2 billion.", "it cites no source"),
        ("Net sales were $416.2 billion [C9].", "[C9] is not one of the sources"),
        ("Net sales were $416.2 billion [C1][C2].", "[C2] is not one of the sources"),
        # A marker that is no source id: x18's [12] (nightly, 2026-10-18) and x11's [D1] (dev).
        ("Net sales were $416.2 billion [F1][12].", "[12] is not one of the sources"),
        ("Net sales were $416.2 billion [F1][D1].", "[D1] is not one of the sources"),
        ("Net sales [sic] were $416.2 billion [F1].", None),  # no digit, so not a marker
    ],
)
def test_a_sentence_holds_only_when_its_citations_and_amounts_check_out(
    sentence: str, problem: str | None
) -> None:
    found = check_sentence(sentence, QUOTES, SOURCES)
    assert found == problem or (
        problem is not None and found is not None and found.startswith(problem)
    )


def test_a_changed_quote_fails_the_sentence_even_with_a_right_amount() -> None:
    quotes = {"C1": ["Net sales rose 7% to $416.2 billion."]}
    assert check_sentence("Net sales were $416.2 billion [C1].", quotes, SOURCES) == (
        "[C1] the quote is not in chunk c-1"
    )
    assert check_sentence("Net sales were $416.2 billion [C1].", {}, SOURCES) == (
        "[C1] has no quote under Sources"
    )


@pytest.mark.parametrize(
    "sentence",
    [
        # x16 (dev, 2026-10-16): a cut after "U.S." left "Government, either as..." on its own.
        "In 2025, 72% of Lockheed Martin's $75.0 billion in sales were from the U.S. Government,"
        " either as a prime contractor or as a subcontractor [C3].",
        "Lockheed Martin Corp. (LMT) sells mostly to the U.S. Department of War [C3].",
        "Apple Inc. Services revenue is not split out by country [C1].",
        "Union Pacific Railroad Co. (UPRR) is its main subsidiary [C1].",
        "Lease terms are in Note No. 7 of the statements [C2].",
        "Some segments, e.g. Greater China, grew [C1].",
        "Its largest segment, i.e. Americas, grew [C1].",
    ],
)
def test_an_abbreviation_inside_a_sentence_does_not_end_it(sentence: str) -> None:
    assert split_sentences(sentence) == [sentence]


@pytest.mark.parametrize(
    ("text", "sentences"),
    [
        (
            "Most sales were in the U.S. The rest came from Europe [C1].",
            ["Most sales were in the U.S.", "The rest came from Europe [C1]."],
        ),
        (
            "The registrant is Apple Inc. It designs the iPhone [C1].",
            ["The registrant is Apple Inc.", "It designs the iPhone [C1]."],
        ),
        (
            "It sells phones, tablets, etc. However, services grew faster [C1].",
            ["It sells phones, tablets, etc.", "However, services grew faster [C1]."],
        ),
        (
            "Sales were highest in the U.S. [C1]. Europe came second [C2].",
            ["Sales were highest in the U.S. [C1].", "Europe came second [C2]."],
        ),
        (
            "Net sales rose [F1]. 72% came from the U.S. Government [C3].",
            ["Net sales rose [F1].", "72% came from the U.S. Government [C3]."],
        ),
    ],
)
def test_a_sentence_that_ends_with_an_abbreviation_still_splits(
    text: str, sentences: list[str]
) -> None:
    assert split_sentences(text) == sentences
