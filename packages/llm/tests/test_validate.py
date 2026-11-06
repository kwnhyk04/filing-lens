"""Answer post-validation: citations quote their chunk; amounts parse and match within 0.5%."""

from dataclasses import dataclass
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from filinglens_llm.answer import Reply, Source, check
from filinglens_llm.validate import (
    UNSTATED,
    Calculation,
    amounts_match,
    check_sentence,
    citation_error,
    figures,
    find_amounts,
    numbers_in,
    on_calculation,
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
        ("51.32 USD", None, "51.32"),
        ("USD 51.32", None, "51.32"),
        ("$51.32", None, "51.32"),
        ("USD 4.2 billion", None, "4200000000"),
        ("4.2 billion USD", None, "4200000000"),
        ("(USD 1,234)", None, "-1234"),
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
        ("51.32 USDT", None),  # never 51.32 trillion
        ("51.32 EUR", None),
        ("USD", None),
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
        ("It paid 51.32 USD a share.", [(Decimal("51.32"), False)]),  # n44 and n51 (test)
        ("It paid USD 51.32 a share.", [(Decimal("51.32"), False)]),
        ("It paid $51.32 a share.", [(Decimal("51.32"), False)]),
        ("Diluted EPS was 14.23 USD/shares.", [(Decimal("14.23"), False)]),  # n09 (dev)
        ("Revenue was USD 4.2 billion.", [(Decimal(4_200_000_000), False)]),
        ("Revenue was 4.2 billion USD.", [(Decimal(4_200_000_000), False)]),
        ("It paid 1,234 USD.", [(Decimal(1234), False)]),
        # A bracket closed or opened beyond the match: the amount was dropped unread.
        ("EPS was high (USD 51.32 per share).", [(Decimal("51.32"), False)]),
        ("EPS was high ($51.32 per share).", [(Decimal("51.32"), False)]),
        ("EPS was high (or $51.32).", [(Decimal("51.32"), False)]),
        (
            "It lost $44.2 billion ($43.4 billion net).",
            [(Decimal(44_200_000_000), False), (Decimal(43_400_000_000), False)],
        ),
        # Rows the check must leave alone.
        ("Filings report in USD for fiscal 2025.", []),
        ("In fiscal 2025, USD revenue rose.", []),
        ("The figures are in 2025 USD.", []),
        ("It holds 51.32 USDT.", []),
    ],
)
def test_the_finder_pulls_every_amount_out_of_answer_text_but_no_years_or_items(
    text: str, amounts: list[tuple[Decimal, bool]]
) -> None:
    assert find_amounts(text) == amounts


@pytest.mark.parametrize(
    ("text", "numbers"),
    [
        ("In fiscal 2025, the Company expanded.", []),
        ("Net sales | 2025 | 2024 | 1999", []),  # a table's header row
        ("FY2023 against 2022", []),
        ("1,800 stores and 2,025 more", [Decimal(1800), Decimal(2025)]),  # counts: a comma
        ("$2025", [Decimal(2025)]),  # money
        ("2025 million", [Decimal(2_025_000_000)]),  # a scale
        ("2025.5 and 12025", [Decimal("2025.5"), Decimal(12025)]),
        ("1899 and 2100", [Decimal(1899), Decimal(2100)]),  # outside the years filings write
    ],
)
def test_a_bare_year_is_no_number_and_every_other_number_is(
    text: str, numbers: list[Decimal]
) -> None:
    assert numbers_in(text) == numbers


@dataclass
class Src:
    text: str
    chunk_id: str | None = None
    fact_id: str | None = None
    value: Decimal | None = None
    calculation: Calculation | None = None
    unit_above: str = ""


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


FACT_ONLY = {"F1": SOURCES["F1"]}


@pytest.mark.parametrize(
    "sentence",
    [
        "The sources do not state how it changed [F1].",  # the demo capture, 2026-11-07
        "The sources don't say how it changed [F1].",
        "The difference is not stated in the sources [F1].",  # saved drafts, as written
        "The filing does not provide further detail [F1].",
        "That figure is labeled fiscal 2025 Q2, so the sources do not show the year-end [F1].",
        "The source reports this as a Q2 balance, so it does not confirm the year-end [F1].",
        "The year-end total cannot be confirmed from them [F1].",
        "No further information on the change is given [F1].",
    ],
)
def test_no_sentence_says_what_the_sources_leave_out_when_only_facts_were_read(
    sentence: str,
) -> None:
    assert check_sentence(sentence, {}, FACT_ONLY) == (
        "it says what the sources do not state; say only what they show"
    )


@pytest.mark.parametrize(
    "sentence",
    [
        "Net sales were $416.2 billion [F1].",
        "Net sales did not fall below $416.2 billion [F1].",  # a negation about the figure
        "The fact gives net sales of $416.2 billion [F1].",  # its noun, with no negation
        "Apple filed no amended figure [F1].",  # "no", about something else
    ],
)
def test_a_fact_only_sentence_that_leaves_nothing_out_stands(sentence: str) -> None:
    assert check_sentence(sentence, {}, FACT_ONLY) is None


def test_with_filing_text_read_a_sentence_may_say_what_it_leaves_out() -> None:
    sentence = "The sources do not state why net sales rose [C1]."
    assert check_sentence(sentence, QUOTES, SOURCES) is None


COMPARED = {
    "F1": Src("402,836,000,000 USD", fact_id="f-1", value=Decimal(402_836_000_000)),
    "F2": Src("350,018,000,000 USD", fact_id="f-2", value=Decimal(350_018_000_000)),
    "F3": Src("14.23 USD/shares", fact_id="f-3", value=Decimal("14.23")),
    "F4": Src("15.11 USD/shares", fact_id="f-4", value=Decimal("15.11")),
    "F5": Src("2.03 USD/shares", fact_id="f-5", value=Decimal("2.03")),
}


@pytest.mark.parametrize(
    ("sentence", "problem"),
    [
        # A year states no figure, though 2.03 at a table's thousands is within 0.5% of 2025.
        ("Diluted EPS rose in 2025 [F5].", "[F5]"),
        # c02's conclusion (test, 2026-10-17): the judge counted neither citation.
        ("Therefore, Alphabet's revenue was higher in fiscal 2025 [F1][F2].", "[F1], [F2]"),
        ("Alphabet's revenue rose to $402.8 billion from $350.0 billion [F1][F2].", None),
        ("It was higher in 2025, at $402.8 billion [F1], than in 2024 [F2].", "[F2]"),
        # Per-share figures as Gemini copies them (n09); a bare 15.11 before them still counts.
        ("Diluted EPS fell to 14.23 USD/shares from 15.11 USD/shares [F3][F4].", None),
        ("Diluted EPS fell from 15.11 to 14.23 USD/shares [F3][F4].", None),
        ("Home Depot's diluted earnings per share were 14.23 USD/shares [F3].", None),
    ],
)
def test_a_comparison_that_cites_facts_states_their_figures(
    sentence: str, problem: str | None
) -> None:
    found = check_sentence(sentence, {}, COMPARED)
    if problem is None:
        assert found is None
    else:
        assert found == f"it compares figures without stating those of {problem}"


YEAR_QUOTE = "In fiscal 2025, the Company expanded its factory."


@pytest.mark.parametrize(
    ("sentence", "shown"),
    [
        ("Tesla spent $2 billion on its factory [C1].", "2,000,000,000"),  # review finding 1
        ("Tesla spent $2.0 billion on its factory [C1].", "2,000,000,000"),
        ("Tesla spent $2.03 billion on its factory [C1].", "2,030,000,000"),  # within 0.5%
    ],
)
def test_a_year_in_a_quote_backs_no_amount(sentence: str, shown: str) -> None:
    sources = {"C1": Src(YEAR_QUOTE, chunk_id="c-1")}
    found = check_sentence(sentence, {"C1": [YEAR_QUOTE]}, sources)
    assert found == f"the amount {shown} is not in the sources it cites"


PER_SHARE = {"F1": Src("51.32 USD", fact_id="f-1", value=Decimal("51.32"))}


@pytest.mark.parametrize(
    "written",
    ["{} USD", "USD {}", "${}", "({} USD)", "(USD {})", "(USD {} per share)", "(${} per share)"],
)
def test_a_per_share_amount_is_checked_however_it_is_written(written: str) -> None:
    sentence = f"Diluted EPS was {written} [F1]."
    assert check_sentence(sentence.format("51.32"), {}, PER_SHARE) is None
    wrong = check_sentence(sentence.format("52.32"), {}, PER_SHARE)
    assert wrong is not None and "52.32 is not in the sources it cites" in wrong


@pytest.mark.parametrize(
    ("sentence", "written"),
    [
        ("Diluted EPS was 51.32 USD [F1].", "51.32 USD"),
        ("Diluted EPS was USD 51.32 [F1].", "USD 51.32"),
        ("Diluted EPS was $51.32 [F1].", "$51.32"),
        ("Diluted EPS (USD 51.32 per share) was high [F1].", "USD 51.32"),
        ("Diluted EPS ($51.32 per share) was high [F1].", "$51.32"),
        ("Diluted EPS (or $51.32) was high [F1].", "$51.32"),
    ],
)
def test_a_figure_keeps_the_text_the_sentence_wrote(sentence: str, written: str) -> None:
    assert [f.text for f in figures(sentence, {}, PER_SHARE)] == [written]


CASH = {  # n24 (dev, E2): Haiku's "$4.1 billion" is 0.51% off, outside the 0.5% tolerance
    "F1": Src("4,121,000,000 USD", fact_id="f-1", value=Decimal(4_121_000_000)),
    "C1": Src("(in millions)\nCash and cash equivalents | $ | 4,121 | $ | 2,483", chunk_id="c-1"),
}


@pytest.mark.parametrize(
    ("sentence", "problem"),
    [
        ("Lockheed Martin held $4.1 billion in cash at the end of fiscal 2025 [F1].", None),
        ("It held about $4 billion in cash [F1].", None),
        ("It held $4.1 billion in cash [C1].", None),  # a table row in millions
        ("It held $4.2 billion in cash [F1].", "the amount 4,200,000,000 is not in the sources"),
        ("It held $5 billion in cash [F1].", "the amount 5,000,000,000 is not in the sources"),
        ("It held $4.2 billion in cash [C1].", "the amount 4,200,000,000 is not in the sources"),
    ],
)
def test_an_amount_passes_as_its_source_rounded_at_the_amounts_last_digit(
    sentence: str, problem: str | None
) -> None:
    found = check_sentence(sentence, {"C1": ["Cash and cash equivalents | $ | 4,121"]}, CASH)
    assert found == problem or (
        problem is not None and found is not None and found.startswith(problem)
    )


# c09 and c13 (dev): one company's two fiscal years, F1 the later, K1 from the earlier year.
APPLE = {
    "F1": Src("416,161,000,000 USD", fact_id="f-1", value=Decimal(416_161_000_000)),
    "F2": Src("391,035,000,000 USD", fact_id="f-2", value=Decimal(391_035_000_000)),
    "K1": Src(
        "From fiscal 2024 to fiscal 2025: an increase of 25,126,000,000 USD, or 6.43%.",
        calculation=Calculation(("F2", "F1"), Decimal(25_126_000_000), Decimal("6.43"), True),
    ),
}
UNITEDHEALTH = {
    "F1": Src("12,056,000,000 USD", fact_id="f-1", value=Decimal(12_056_000_000)),
    "F2": Src("14,405,000,000 USD", fact_id="f-2", value=Decimal(14_405_000_000)),
    "K1": Src(
        "From fiscal 2024 to fiscal 2025: a decrease of 2,349,000,000 USD, or 16.31%.",
        calculation=Calculation(("F2", "F1"), Decimal(-2_349_000_000), Decimal("-16.31"), True),
    ),
}
# c08 (dev): two companies, one year; K1 names the lower first, so the higher is the second.
PEERS = {
    "F1": Src("716,924,000,000 USD", fact_id="f-1", value=Decimal(716_924_000_000)),
    "F2": Src("680,985,000,000 USD", fact_id="f-2", value=Decimal(680_985_000_000)),
    "K1": Src(
        "Amazon is higher by 35,939,000,000 USD, 5.28% more than Walmart.",
        calculation=Calculation(("F2", "F1"), Decimal(35_939_000_000), Decimal("5.28"), False),
    ),
}
EPS = {  # review finding: K1's difference 0.52 must not back "52%"
    "F1": Src("6.11 USD/shares", fact_id="f-1", value=Decimal("6.11")),
    "F2": Src("6.63 USD/shares", fact_id="f-2", value=Decimal("6.63")),
    "K1": Src("", calculation=Calculation(("F1", "F2"), Decimal("0.52"), Decimal("8.51"), True)),
}
LOSS = {  # a net loss from -1.0 to -2.2 billion: "the loss grew" is right, though the value fell
    "F1": Src("-2,200,000,000 USD", fact_id="f-1", value=Decimal(-2_200_000_000)),
    "F2": Src("-1,000,000,000 USD", fact_id="f-2", value=Decimal(-1_000_000_000)),
    "K1": Src("", calculation=Calculation(("F2", "F1"), Decimal(-1_200_000_000), None, True)),
}
C09 = "Apple's net sales were $416.2 billion in fiscal 2025 and $391.0 billion in fiscal 2024, "
C13 = (
    "UnitedHealth's net income {} $2.3 billion, from $14.4 billion in fiscal 2024 to $12.1 billion"
)


@pytest.mark.parametrize(
    ("sources", "sentence", "problem"),
    [
        (APPLE, C09 + "an increase of about $25.1 billion [F1][F2][K1].", None),
        (APPLE, C09 + "up $25.1 billion, or 6.4% [F1][F2][K1].", None),
        (UNITEDHEALTH, C13.format("fell by") + " in fiscal 2025 [F1][F2][K1].", None),
        (PEERS, "Amazon's $716.9 billion was $35.9 billion, or 5.3%, higher than Walmart's"
         " $681.0 billion [F1][F2][K1].", None),
        (PEERS, "Walmart's $681.0 billion was $35.9 billion lower than Amazon's $716.9 billion"
         " [F1][F2][K1].", None),  # two companies: no direction word is checked
        # c09's draft (dev, E2): without K1 the difference is in no source.
        (APPLE, C09 + "an increase of about $25.1 billion [F1][F2].",
         "the amount 25,100,000,000 is not in the sources it cites"),
        (APPLE, C09 + "an increase of about $26.1 billion [F1][F2][K1].",
         "the amount 26,100,000,000 is not in the sources it cites"),
        (APPLE, C09 + "a decrease of $25.1 billion [F1][F2][K1].",
         "it says the figure fell, but [K1] shows a rise"),
        (UNITEDHEALTH, C13.format("rose by") + " in fiscal 2025 [F1][F2][K1].",
         "it says the figure rose, but [K1] shows a fall"),
        (APPLE, "Net sales increased by about $25.1 billion [K1].",
         "[K1] is cited without [F2] and [F1], the facts it was calculated from"),
        (APPLE, "Net sales of $416.2 billion were up $25.1 billion [F1][K1].",
         "[K1] is cited without [F2], the facts it was calculated from"),
        (APPLE, C09 + "up $25.1 billion [F1][F2][K2].", "[K2] is not one of the sources"),
        # Review findings: a figure matches only amounts of its own kind, as stated, and a loss
        # has no rise or fall word to check.
        (APPLE, C09 + "up $6.4 billion [F1][F2][K1].",
         "the amount 6,400,000,000 is not in the sources it cites"),
        (EPS, "Diluted EPS rose 52%, from 6.11 to 6.63 USD/shares [F1][F2][K1].",
         "the amount 52% is not in the sources it cites"),
        (LOSS, "The net loss grew by $1.2 billion, from $1.0 billion in fiscal 2024 to $2.2 billion"
         " [F1][F2][K1].", None),
    ],
)  # fmt: skip
def test_a_calculation_holds_the_difference_when_cited_with_both_its_facts(
    sources: dict[str, Src], sentence: str, problem: str | None
) -> None:
    assert check_sentence(sentence, {}, sources) == problem


def test_an_amount_k1_holds_names_k1() -> None:
    sentence = C09 + "up $25.1 billion, or 6.4% [F1][F2][K1]."
    assert [(f.text, f.alias, f.number) for f in figures(sentence, {}, APPLE)] == [
        ("$416.2 billion", "F1", 416_161_000_000),
        ("$391.0 billion", "F2", 391_035_000_000),
        ("$25.1 billion", "K1", 25_126_000_000),
        ("6.4%", "K1", Decimal("6.43")),
    ]


R02 = (  # the sentence both of r02's drafts lost, live on 2026-11-07
    "Fiscal 2025 revenue was higher by $25,126 million (about $25.13 billion), which is 6.43% more"
    " than fiscal 2024 [F1][F2][K1]."
)
NAMES_THE_FIGURES = (  # r02's first two sentences
    "Apple's fiscal 2025 revenue was $416.2 billion [F1]. Fiscal 2024 revenue was $391.0 billion,"
    " or $391,035 million [F2]. "
)
UNION_PACIFIC = {  # c19 (test): two companies, K1 from the lower
    "F1": Src("2,821,000,000 USD", fact_id="f-1", value=Decimal(2_821_000_000)),
    "F2": Src("3,791,000,000 USD", fact_id="f-2", value=Decimal(3_791_000_000)),
    "K1": Src(
        "UNION PACIFIC CORP (UNP) is higher by 970,000,000 USD, 34.38% more than CATERPILLAR INC.",
        calculation=Calculation(("F1", "F2"), Decimal(970_000_000), Decimal("34.38"), False),
    ),
}
C19 = (  # Haiku's first draft of 2026-11-06, whose rewrite became a false refusal
    "Union Pacific spent more on capital expenditures in 2025, with payments to acquire property,"
    " plant, and equipment of $3.791 billion compared with Caterpillar's $2.821 billion"
    " [F1][F2][K1]. The calculation shows Union Pacific's figure is higher by $970 million, or"
    " 34.38% more than Caterpillar's [F1][F2][K1]."
)


def test_r02s_lost_sentence_keeps_its_calculation_and_loses_the_facts_it_does_not_state() -> None:
    assert on_calculation(R02, {}, APPLE) == (
        "Fiscal 2025 revenue was higher by $25,126 million (about $25.13 billion), which is 6.43%"
        " more than fiscal 2024 [K1].",
        ["F1", "F2"],
    )


@pytest.mark.parametrize(
    ("sources", "sentence", "kept", "gone"),
    [
        # One fact stated: only the other goes.
        (APPLE, "Revenue of $416.2 billion was higher by $25.13 billion, or 6.43% more {}.",
         "[F1][K1]", ["F2"]),
        (APPLE, "Revenue was higher than the $391.0 billion of fiscal 2024 by 6.43% {}.",
         "[F2][K1]", ["F1"]),
        # The result as rounded, by the rule every amount follows.
        (APPLE, "Revenue was higher by about $25.13 billion, or 6.4% more than fiscal 2024 {}.",
         "[K1]", ["F1", "F2"]),
        (APPLE, "Fiscal 2025 revenue was 6.4% more than fiscal 2024 {}.", "[K1]", ["F1", "F2"]),
        (APPLE, "Fiscal 2025 revenue was higher by $25.13 billion {}.", "[K1]", ["F1", "F2"]),
        # A fall said as a fall, and a loss that grew: K1's difference is below 0.
        (UNITEDHEALTH, "Net income was lower by $2.349 billion, or 16.31% less than in 2024 {}.",
         "[K1]", ["F1", "F2"]),
        (UNITEDHEALTH, "Net income fell by $2.349 billion, or 16.31%, in fiscal 2025 {}.",
         "[K1]", ["F1", "F2"]),
        (LOSS, "The net loss grew by $1.2 billion in fiscal 2025 {}.", "[K1]", ["F1", "F2"]),
        (PEERS, "Amazon's revenue was higher by $35.94 billion, or 5.28% more than Walmart's {}.",
         "[K1]", ["F1", "F2"]),
    ],
)  # fmt: skip
def test_a_sentence_that_states_its_calculations_result_loses_only_its_unstated_facts(
    sources: dict[str, Src], sentence: str, kept: str, gone: list[str]
) -> None:
    written = sentence.format("[F1][F2][K1]")
    assert check_sentence(written, {}, sources) == UNSTATED + ", ".join(f"[{f}]" for f in gone)
    assert on_calculation(written, {}, sources) == (sentence.format(kept), gone)


def test_facts_joined_in_one_marker_go_the_same_way() -> None:
    sentence = "Fiscal 2025 revenue was higher by $25.13 billion [F1, F2, K1]."
    assert on_calculation(sentence, {}, APPLE) == (
        "Fiscal 2025 revenue was higher by $25.13 billion [K1].",
        ["F1", "F2"],
    )


BOTH = UNSTATED + "[F1], [F2]"


@pytest.mark.parametrize(
    ("sources", "sentence", "problem"),
    [
        # No calculation stands for the facts.
        (APPLE, "Fiscal 2025 revenue was higher than fiscal 2024 [F1][F2].", BOTH),
        (COMPARED, "Alphabet's revenue was higher by 6.43% in fiscal 2025 [F1][F2].",
         "the amount 6.43% is not in the sources it cites"),
        # Its result is not stated.
        (APPLE, "Fiscal 2025 revenue was higher than fiscal 2024 [F1][F2][K1].", BOTH),
        # The wrong scale, past its rounding, or of another kind.
        (APPLE, "Fiscal 2025 revenue was higher by $25.13 million [F1][F2][K1].",
         "the amount 25,130,000 is not in the sources it cites"),
        (APPLE, "Fiscal 2025 revenue was higher by $26.1 billion [F1][F2][K1].",
         "the amount 26,100,000,000 is not in the sources it cites"),
        (APPLE, "Fiscal 2025 revenue was higher by 25.13% [F1][F2][K1].",
         "the amount 25.13% is not in the sources it cites"),
        (APPLE, "Fiscal 2025 revenue was higher by 7.4% [F1][F2][K1].",
         "the amount 7.4% is not in the sources it cites"),
        # The wrong sign: by the rise and fall check, or else by the words beside the comparison.
        (APPLE, "Fiscal 2025 revenue fell by $25.13 billion [F1][F2][K1].",
         "it says the figure fell, but [K1] shows a rise"),
        (APPLE, "Fiscal 2025 revenue was lower by $25.13 billion, or 6.43% less than fiscal 2024"
         " [F1][F2][K1].", BOTH),
        (UNITEDHEALTH, "Net income was higher by $2.349 billion, or 16.31% more [F1][F2][K1].",
         BOTH),
        (APPLE, "Fiscal 2025 revenue was higher by -$25.13 billion [F1][F2][K1].", BOTH),
        # K1 short of a fact, as the model wrote it.
        (APPLE, "Net sales were up $25.1 billion [K1].",
         "[K1] is cited without [F2] and [F1], the facts it was calculated from"),
        (APPLE, "Net sales were up $25.1 billion [F1][K1].",
         "[K1] is cited without [F2], the facts it was calculated from"),
    ],
)  # fmt: skip
def test_any_other_sentence_fails_as_it_did(
    sources: dict[str, Src], sentence: str, problem: str
) -> None:
    assert check_sentence(sentence, {}, sources) == problem
    assert on_calculation(sentence, {}, sources) is None


def drafted(sources: dict[str, Src]) -> dict[str, Source]:
    """The test's sources as the answer pipeline holds them."""
    return {
        alias: Source(alias, s.chunk_id, s.fact_id, "", s.text, s.value, "u", s.calculation)
        for alias, s in sources.items()
    }


def test_r02s_answer_keeps_its_change_and_each_fact_where_its_figure_is_stated() -> None:
    checked = check(Reply(NAMES_THE_FIGURES + R02, {}, False), drafted(APPLE))
    assert checked.problems == [] and (checked.pruned, checked.unstated) == (0, 2)
    assert checked.text.endswith("which is 6.43% more than fiscal 2024 [3].")
    assert [alias for alias, _ in checked.citations] == ["F1", "F2", "K1"]
    assert ("$25,126 million", "K1") in [(f.text, f.alias) for f in checked.figures]


def test_c19s_draft_holds_without_a_rewrite() -> None:
    checked = check(Reply(C19, {}, False), drafted(UNION_PACIFIC))
    assert checked.problems == [] and checked.unstated == 2
    assert checked.text.endswith("or 34.38% more than Caterpillar's [3].")
    assert [alias for alias, _ in checked.citations] == ["F1", "F2", "K1"]


@pytest.mark.parametrize(
    "text",
    [
        R02,  # no other sentence cites the facts
        NAMES_THE_FIGURES.replace("[F2]", "[F1]").replace("$391.0 billion, or $391,035 million",
                                                          "$416.2 billion") + R02,  # or not F2
        "Fiscal 2024 revenue was $999.0 billion [F2]. " + R02,  # or only a sentence that fails
    ],
)  # fmt: skip
def test_a_fact_no_sentence_that_holds_cites_keeps_the_sentence_failing(text: str) -> None:
    """K1's citation names its facts' citations, so the answer must keep them (Calculation)."""
    checked = check(Reply(text, {}, False), drafted(APPLE))
    assert f'"{R02}": {BOTH}' in checked.problems
    assert "K1" not in [alias for alias, _ in checked.citations] and checked.unstated == 0


def test_a_changed_quote_fails_the_sentence_even_with_a_right_amount() -> None:
    quotes = {"C1": ["Net sales rose 7% to $416.2 billion."]}
    assert check_sentence("Net sales were $416.2 billion [C1].", quotes, SOURCES) == (
        "[C1] the quote is not in chunk c-1"
    )
    assert check_sentence("Net sales were $416.2 billion [C1].", {}, SOURCES) == (
        "[C1] has no quote under Sources"
    )


TABLE = "Net income | $ | 3,855 | $ | 7,153"
FIGURE_SOURCES = {
    **SOURCES,
    "C2": Src(f"Consolidated statements of operations (in millions)\n{TABLE}", chunk_id="c-2"),
    "F2": Src("0.162 pure", fact_id="f-2", value=Decimal("0.162")),
    "F3": Src("-1,200,000,000 USD", fact_id="f-3", value=Decimal(-1_200_000_000)),
}
FIGURE_QUOTES = {**QUOTES, "C2": [TABLE]}


@pytest.mark.parametrize(
    ("sentence", "found"),
    [
        ("Net sales were $416.2 billion [F1].", [("$416.2 billion", "F1", 416_161_000_000)]),
        (  # both in the quote, the percent at its own scale
            "Net sales were $416 billion, up 6% [C1].",
            [("$416 billion", "C1", 416_200_000_000), ("6%", "C1", 6)],
        ),
        ("Both say $416.2 billion [F1, C1].", [("$416.2 billion", "F1", 416_161_000_000)]),
        (  # the percent held by the second source only; the cited fact states its figure
            "Net sales rose 6% to $416.2 billion [F1][C1].",
            [("6%", "C1", 6), ("$416.2 billion", "F1", 416_161_000_000)],
        ),
        ("Net income was $3,855 million [C2].", [("$3,855 million", "C2", 3855)]),  # in millions
        ("The margin was 16.2% [F2].", [("16.2%", "F2", Decimal("0.162"))]),
        ("A net loss of $1.2 billion [F3].", [("$1.2 billion", "F3", -1_200_000_000)]),  # sign
        ("In fiscal 2025 the 10-K names 3 segments [C1].", []),  # a year and a count: no amount
    ],
)
def test_each_amount_of_a_sentence_that_holds_names_the_source_that_holds_it(
    sentence: str, found: list[tuple[str, str, Decimal | int]]
) -> None:
    assert check_sentence(sentence, FIGURE_QUOTES, FIGURE_SOURCES) is None
    listed = figures(sentence, FIGURE_QUOTES, FIGURE_SOURCES)
    assert [(f.text, f.alias, f.number) for f in listed] == found


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


# The architecture review's V1 (2026-11-06): the amounts check_sentence let through, and the rows
# the check must leave alone.
def usd(value: int) -> dict[str, Src]:
    return {"F1": Src(f"{value:,} USD", fact_id="f-1", value=Decimal(value))}


NET_SALES = usd(416_161_000_000)
NET_LOSS = usd(-1_200_000_000)
NET_INCOME = usd(1_200_000_000)
DILUTED = {"F1": Src("6.11 USD/shares", fact_id="f-1", value=Decimal("6.11"))}
NOT_HELD = "is not in the sources it cites"


@pytest.mark.parametrize(
    ("sentence", "sources", "problem"),
    [
        # A fact is in base units, so no table scale applies to it.
        ("Net sales were $416.2 trillion in fiscal 2025 [F1].", NET_SALES,
         f"the amount 416,200,000,000,000 {NOT_HELD}"),
        ("Net sales were $416.2 million in fiscal 2025 [F1].", NET_SALES,
         f"the amount 416,200,000 {NOT_HELD}"),
        ("Net sales were $416,161 in fiscal 2025 [F1].", NET_SALES,
         f"the amount 416,161 {NOT_HELD}"),
        ("Diluted EPS was $6.11 billion [F1].", DILUTED, f"the amount 6,110,000,000 {NOT_HELD}"),
        ("Diluted EPS was $6.11 million [F1].", DILUTED, f"the amount 6,110,000 {NOT_HELD}"),
        # A per-share figure is no total, and a dollar figure no percentage.
        ("Net income was $6.11 [F1].", DILUTED,
         "[F1] is a per-share figure, which the sentence does not say"),
        ("Diluted EPS grew 6.11% [F1].", DILUTED, f"the amount 6.11% {NOT_HELD}"),
        ("Net sales grew 416.2% [F1].", NET_SALES, f"the amount 416.2% {NOT_HELD}"),
        # A loss stated as a profit, and the reverse.
        ("Net income was $1.2 billion [F1].", NET_LOSS,
         "[F1] shows a loss or a negative figure, which the sentence does not say"),
        ("Net income rose by $1.2 billion [F1].", NET_LOSS,
         "[F1] shows a loss or a negative figure, which the sentence does not say"),
        ("Net loss was $1.2 billion [F1].", NET_INCOME, "it says a loss, but [F1] shows a gain"),
    ],
)  # fmt: skip
def test_a_fact_backs_an_amount_only_at_its_own_scale_sign_and_unit(
    sentence: str, sources: dict[str, Src], problem: str
) -> None:
    assert check_sentence(sentence, {}, sources) == problem


@pytest.mark.parametrize(
    ("value", "sentence"),
    [
        # Rule 4: at least four significant digits, and the rounding the check keeps as a backstop.
        (416_161_000_000, "Net sales were $416.2 billion in fiscal 2025 [F1]."),
        (416_161_000_000, "Net sales were $416.161 billion in fiscal 2025 [F1]."),
        (416_161_000_000, "Net sales were $416 billion in fiscal 2025 [F1]."),
        (416_161_000_000, "Net sales were $416,161 million in fiscal 2025 [F1]."),
        (416_161_000_000, "Net sales were USD 416.2 billion in fiscal 2025 [F1]."),
        (416_161_000_000, "Net sales were 416.2 billion USD in fiscal 2025 [F1]."),
        (416_161_000_000, "Net sales were $416,161,000,000 in fiscal 2025 [F1]."),
        (4_121_000_000, "It held $4.121 billion in cash [F1]."),
        (4_121_000_000, "It held $4.1 billion in cash [F1]."),  # n24, 0.51% off
        (6_747_000_000, "It held $6.7 billion in cash [F1]."),  # n39, 0.70% off
        (6_835_000_000, "It held $6.835 billion in cash [F1]."),  # n49
        (6_835_000_000, "It held $6.8 billion in cash [F1]."),
    ],
)
def test_rule_4_roundings_still_pass(value: int, sentence: str) -> None:
    assert check_sentence(sentence, {}, usd(value)) is None


@pytest.mark.parametrize(
    "written",
    [
        "A net loss of $1.2 billion [F1].",
        "It lost $1.2 billion [F1].",
        "Net losses were $1.2 billion [F1].",
        "The deficit was $1.2 billion [F1].",
        "Net cash used in operating activities was $1.2 billion [F1].",
        "Net income was -$1.2 billion [F1].",
        "Net income was \N{MINUS SIGN}$1.2 billion [F1].",
        "Net income was $(1.2) billion [F1].",
        "Net income was ($1.2 billion) [F1].",
    ],
)
def test_a_negative_fact_passes_with_a_loss_word_a_minus_or_brackets(written: str) -> None:
    assert check_sentence(written, {}, NET_LOSS) is None


def test_a_positive_fact_is_no_loss_only_where_the_sentence_says_nothing_else() -> None:
    assert check_sentence("Net income was $1.2 billion [F1].", {}, NET_INCOME) is None
    sentence = "After a net loss in 2023, net income was $1.2 billion [F1]."
    assert check_sentence(sentence, {}, NET_INCOME) is None


def test_a_per_share_fact_passes_when_the_sentence_says_per_share() -> None:
    for sentence in (
        "Diluted EPS was $6.11 [F1].",
        "Diluted earnings per share were $6.11 [F1].",
        "Earnings per diluted share were 6.11 USD [F1].",
        "It earned 6.11 USD/shares [F1].",
        "It earned $6.11 a share [F1].",
    ):
        assert check_sentence(sentence, {}, DILUTED) is None, sentence


MARGIN = "Gross margin was 46.2% of net sales"
AT_YEAR_END = "as of December 31, 2025"
ROW = "Cash and cash equivalents | $ | 4,121 | $ | 2,483"
RESULT_ROW = "Net income (loss) | $ | (1,200 | ) | $ | 3,855"
PER_SHARE_ROW = "Diluted earnings per share | $ | 6.11"
STATEMENTS = "(In millions, except per share amounts)\n"


@pytest.mark.parametrize(
    ("sentence", "chunk", "quote", "problem"),
    [
        # A percentage reads as no dollar amount, and a dollar amount as no percentage.
        ("Gross profit was $46.2 billion [C1].", MARGIN, MARGIN, "46,200,000,000"),
        ("Gross profit was $46.2 [C1].", MARGIN, MARGIN, "46.2"),
        ("Gross margin was 46.2% [C1].", "gross profit of $46.2 billion",
         "gross profit of $46.2 billion", "46.2%"),
        # A part of a date backs nothing.
        ("Cash was $31 billion [C1].", AT_YEAR_END, AT_YEAR_END, "31,000,000,000"),
        ("Cash was $31 [C1].", AT_YEAR_END, AT_YEAR_END, "31"),
        ("Its share was 31% [C1].", AT_YEAR_END, AT_YEAR_END, "31%"),
        ("Cash was $31 billion [C1].", "at 31 December 2025", "at 31 December 2025",
         "31,000,000,000"),
        ("Cash was $12 billion [C1].", "dated 12/31/2025", "dated 12/31/2025", "12,000,000,000"),
        ("Cash was $31 billion [C1].", "on 2025-12-31", "on 2025-12-31", "31,000,000,000"),
        # A table's scale needs stating, and only the stated one applies.
        ("It held $4.1 billion [C1].", ROW, ROW, "4,100,000,000"),
        ("It held $4.1 billion [C1].", f"(in thousands)\n{ROW}", ROW, "4,100,000,000"),
        ("It held $4.1 trillion [C1].", f"(in millions)\n{ROW}", ROW, "4,100,000,000,000"),
        ("It held $4,121 [C1].", f"(in millions)\n{ROW}", ROW, "4,121"),
        ("It held $4.1 billion [C1].", f"We serve millions of customers.\n{ROW}", ROW,
         "4,100,000,000"),
        # A number with its own scale, or one that is no table's cell, takes no table scale.
        ("Backlog was $4.2 billion [C1].", "(in thousands)\nbacklog of $4.2 million",
         "backlog of $4.2 million", "4,200,000,000"),
        ("It spent $2 billion [C1].", "(in millions)\nWe run 1,800 stores in all.",
         "We run 1,800 stores in all.", "2,000,000,000"),
        # A per-share cell keeps its scale though the table states one.
        ("Net income was $6.11 million [C1].", STATEMENTS + PER_SHARE_ROW, PER_SHARE_ROW,
         "6,110,000"),
        # Dollars are no percentage, and a count in prose is none either.
        ("It grew 12% [C1].", "Revenue | $ | 12 | $ | 10", "Revenue | $ | 12 | $ | 10", "12%"),
        ("It grew 31% [C1].", "We run 31 stores in all", "We run 31 stores in all", "31%"),
        # Pounds and ounces are no dollars.
        ("Output was $4.1 billion [C1].", f"Copper (millions of recoverable pounds)\n{ROW}", ROW,
         "4,100,000,000"),
    ],
)  # fmt: skip
def test_a_quote_backs_an_amount_only_of_its_kind_at_a_stated_scale(
    sentence: str, chunk: str, quote: str, problem: str
) -> None:
    found = check_sentence(sentence, {"C1": [quote]}, {"C1": Src(chunk, chunk_id="c-1")})
    assert found == f"the amount {problem} {NOT_HELD}"


@pytest.mark.parametrize(
    ("sentence", "chunk", "quote", "problem"),
    [
        ("Net income was $6.11 [C1].", STATEMENTS + PER_SHARE_ROW, PER_SHARE_ROW,
         "[C1] is a per-share figure, which the sentence does not say"),
        ("Net income was $1.2 billion [C1].", "a net loss of $1.2 billion",
         "a net loss of $1.2 billion", "it says a gain, but [C1] shows a loss"),
        ("A net loss of $1.2 billion [C1].", "net income of $1.2 billion",
         "net income of $1.2 billion", "it says a loss, but [C1] shows a gain"),
        ("Net income was $1.2 billion [C1].", f"(in millions)\n{RESULT_ROW}", RESULT_ROW,
         "[C1] shows a loss or a negative figure, which the sentence does not say"),
        ("Net sales increased 5% [C1].", "Net sales decreased 5%", "Net sales decreased 5%",
         "it says the figure rose, but [C1] says it fell"),
        ("Net sales fell by $2.0 billion [C1].", "Net sales increased by $2.0 billion",
         "Net sales increased by $2.0 billion", "it says the figure fell, but [C1] says it rose"),
    ],
)  # fmt: skip
def test_a_quote_backs_no_amount_the_sentence_turns_around(
    sentence: str, chunk: str, quote: str, problem: str
) -> None:
    sources = {"C1": Src(chunk, chunk_id="c-1")}
    assert check_sentence(sentence, {"C1": [quote]}, sources) == problem


@pytest.mark.parametrize(
    ("sentence", "chunk", "quote"),
    [
        # A bracketed expense is no loss: only a result's row reads as one.
        ("Rental expenses were $488 million [C1].", "(in millions)\nRental expenses | (488 | )",
         "Rental expenses | (488 | )"),
        ("A net loss of $1.2 billion [C1].", f"(in millions)\n{RESULT_ROW}", RESULT_ROW),
        ("Net income was $3.9 billion [C1].", f"(in millions)\n{RESULT_ROW}", RESULT_ROW),
        # Loss words about something else, and either direction said at once, decide nothing.
        ("The allowance was $1.2 billion [C1].", "allowance for credit losses of $1.2 billion",
         "allowance for credit losses of $1.2 billion"),
        ("Revenue grew 5% while margins fell [C1].", "Revenue grew 5% as prices fell",
         "Revenue grew 5% as prices fell"),
        ("Revenue was up 5% [C1].", "set up 5% of the sites to fall", "set up 5% of the sites"),
        # A percentage split from its sign by the table's cells, and a percentage in prose.
        ("Same store NOI grew 5.7% [C1].", "Same Store NOI | $ | 1,427 | 5.7 | %",
         "Same Store NOI | $ | 1,427 | 5.7 | %"),
        ("Services were 26 percent of sales [C1].", "Services were 26 percent of net sales",
         "Services were 26 percent of net sales"),
        ("All currencies weakened 1% [C1].", "All operating currencies | (1) | % | (5) | %",
         "All operating currencies | (1) | % | (5) | %"),  # x30
        # A plain cell may be a percentage: the header saying so is often in the chunk before.
        ("Gross profit was 71.1% of revenue [C1].", "Gross profit | 71.1 | 75.0",
         "Gross profit | 71.1 | 75.0"),  # c11
        ("Mounjaro grew 99 percent [C1].", "Mounjaro | $ | 22,965 | $ | 11,540 | 99",
         "Mounjaro | $ | 22,965 | $ | 11,540 | 99"),  # x12
        # Rows a quote joins with spaces are still cells (x31), under the unit it states.
        ("Cash acquired was $385 million [C1].",
         "Millions of Dollars\nCash and cash equivalents | $ | 385\nAccounts receivable, net | 976",
         "Millions of Dollars Cash and cash equivalents | $ | 385 Accounts receivable, net | 976"),
        # Per-share cells in a table in millions, and a count the sentence states as a count.
        ("Diluted EPS was $6.11 [C1].", STATEMENTS + PER_SHARE_ROW, PER_SHARE_ROW),
        ("It has 12,000 employees [C1].", "We had 12,000 employees", "We had 12,000 employees"),
        ("It holds 4,121 sites [C1].", f"(in millions)\n{ROW}", ROW),
        ("It paid $2 billion [C1].", "a payment of $2B", "a payment of $2B"),
        ("It paid $1,250 million [C1].", "(in millions)\nInterest paid | 1,250",
         "Interest paid | 1,250"),
    ],
)  # fmt: skip
def test_the_amount_check_leaves_these_alone(sentence: str, chunk: str, quote: str) -> None:
    assert check_sentence(sentence, {"C1": [quote]}, {"C1": Src(chunk, chunk_id="c-1")}) is None


@pytest.mark.parametrize(
    "heading",
    [
        "(in millions)",
        "(In millions, except per share amounts)",
        "(Dollars in millions)",
        "($ in millions)",
        "$ in millions",
        "(Amounts in millions)",
        "(U.S. dollars in millions)",
        "Millions of dollars",
        "(Millions of dollars)",
        "In millions of dollars",
        "($ millions)",
        "(Tables present dollars in millions, except per-share data)",  # Lilly's Item 7
        "Millions, except percentages | 2025 | 2024",  # Union Pacific's tables
        "Millions | 2025 | 2024",
        "Amounts in millions of dollars except per share amounts",  # Procter & Gamble's
    ],
)
def test_a_table_states_its_scale_as_filings_write_it(heading: str) -> None:
    sources = {"C1": Src(f"{heading}\n{ROW}", chunk_id="c-1")}
    assert check_sentence("It held $4.1 billion [C1].", {"C1": [ROW]}, sources) is None


def test_a_table_in_thousands_backs_only_thousands() -> None:
    sources = {"C1": Src(f"(dollars in thousands)\n{ROW}", chunk_id="c-1")}
    assert check_sentence("It held $4.1 million [C1].", {"C1": [ROW]}, sources) is None


LILLY_ROW = "Mounjaro | $ | 13,651 | $ | 9,315 | $ | 22,965 | $ | 11,540 | 99"


def test_a_table_may_state_its_unit_in_the_section_above_the_chunk() -> None:
    """x12 (dev), the landing page's answer: Item 7 opens with "(Tables present dollars in
    millions, ...)", 21,694 characters above the row."""
    sources = {"C1": Src(LILLY_ROW, chunk_id="c-1", unit_above="dollars in millions")}
    sentence = "Mounjaro revenue was $22,965 million in 2025 [C1]."
    assert check_sentence(sentence, {"C1": [LILLY_ROW]}, sources) is None
    wrong = check_sentence(
        "Mounjaro revenue was $22,965 billion [C1].", {"C1": [LILLY_ROW]}, sources
    )
    assert wrong == f"the amount 22,965,000,000,000 {NOT_HELD}"
    alone = {"C1": Src(LILLY_ROW, chunk_id="c-1")}
    assert check_sentence(sentence, {"C1": [LILLY_ROW]}, alone) == (
        f"the amount 22,965,000,000 {NOT_HELD}"
    )


@pytest.mark.parametrize(
    ("chunk", "quote"),
    [
        # x19 (dev): cells a quote joins with spaces, as a split table reads.
        ("(in thousands)\nTotal revenues (2) $ 584,060 $ 662,132",
         "Total revenues (2) $ 584,060 $ 662,132"),
        ("(in thousands)\nStrategic capital 584,060 671,907", "Strategic capital 584,060 671,907"),
    ],
)  # fmt: skip
def test_cells_a_quote_joins_with_spaces_are_still_cells(chunk: str, quote: str) -> None:
    sources = {"C1": Src(chunk, chunk_id="c-1")}
    sentence = "Revenues were $584,060 thousand in 2025 [C1]."
    assert check_sentence(sentence, {"C1": [quote]}, sources) is None


def test_the_statement_nearest_above_a_quote_wins_over_one_below_it() -> None:
    chunk = f"(in millions)\n{ROW}\n(in thousands)\nOther assets | 12"
    sources = {"C1": Src(chunk, chunk_id="c-1")}
    assert check_sentence("It held $4.1 billion [C1].", {"C1": [ROW]}, sources) is None
    assert check_sentence("It held $4.1 million [C1].", {"C1": [ROW]}, sources) == (
        f"the amount 4,100,000 {NOT_HELD}"
    )


def test_words_elsewhere_in_a_quote_say_nothing_about_a_number() -> None:
    """x30 (test): the quote's "increased marketing spending" is not about the 1%."""
    quotes = {
        "C1": [
            "increased marketing spending and an unfavorable impact of 1%",
            "was a decrease of 2%",
        ]
    }
    chunk = "increased marketing spending and an unfavorable impact of 1%\nwas a decrease of 2%"
    sentence = "Currency cost 1% of operating income, and revenues decreased by 2% [C1]."
    assert check_sentence(sentence, quotes, {"C1": Src(chunk, chunk_id="c-1")}) is None


def test_a_rise_or_fall_word_matches_its_facts_with_k1_cited_or_not() -> None:
    wrong = "Net sales fell to $416.2 billion from $391.0 billion [F1][F2]."
    assert check_sentence(wrong, {}, APPLE) == "it says the figure fell, but [K1] shows a rise"
    right = "Net sales rose to $416.2 billion from $391.0 billion [F1][F2]."
    assert check_sentence(right, {}, APPLE) is None


def test_from_and_to_order_the_amounts_of_an_answer_with_no_calculation() -> None:
    years = {key: source for key, source in APPLE.items() if key != "K1"}
    wrong = "Net sales rose from $416.2 billion to $391.0 billion [F1][F2]."
    assert check_sentence(wrong, {}, years) == "it says the figure rose, but its amounts fall"
    wrong = "Net sales fell to $416.2 billion from $391.0 billion [F1][F2]."
    assert check_sentence(wrong, {}, years) == "it says the figure fell, but its amounts rise"
    right = "Net sales rose from $391.0 billion to $416.2 billion [F1][F2]."
    assert check_sentence(right, {}, years) is None
    right = "Net sales fell to $391.0 billion from $416.2 billion [F1][F2]."
    assert check_sentence(right, {}, years) is None


SCALES = {10**3: "thousand", 10**6: "million", 10**9: "billion", 10**12: "trillion"}


def stated(value: int) -> tuple[str, int]:
    """`value` in dollars at its scale, to rule 4's four significant digits, and that scale."""
    scale = max(step for step in SCALES if step <= value)
    return f"{Decimal(value) / scale:.3f}", scale


@given(st.integers(10**6, 10**13 - 1))
def test_a_fact_at_any_scale_but_its_own_fails(value: int) -> None:
    figure, scale = stated(value)
    sources = usd(value)
    assert check_sentence(f"Net sales were ${figure} {SCALES[scale]} [F1].", {}, sources) is None
    for other in SCALES:
        if other != scale:
            found = check_sentence(f"Net sales were ${figure} {SCALES[other]} [F1].", {}, sources)
            assert found is not None and found.endswith(NOT_HELD)


@given(st.integers(10**6, 10**13 - 1))
def test_a_negative_fact_stated_as_a_gain_fails(value: int) -> None:
    figure, scale = stated(value)
    amount = f"${figure} {SCALES[scale]}"
    sources = usd(-value)
    assert check_sentence(f"It lost {amount} [F1].", {}, sources) is None
    assert check_sentence(f"Net income was {amount} [F1].", {}, sources) == (
        "[F1] shows a loss or a negative figure, which the sentence does not say"
    )


@given(st.integers(1, 9_999), st.sampled_from(("thousands", "millions", "billions")))
def test_a_table_row_backs_its_stated_scale_alone(cell: int, scale: str) -> None:
    row = f"Net sales | {cell:,}"
    chunk = {"C1": Src(f"(in {scale})\n{row}", chunk_id="c-1")}
    step = next(s for s, word in SCALES.items() if f"{word}s" == scale)
    for other, word in SCALES.items():
        found = check_sentence(f"Net sales were ${cell:,} {word} [C1].", {"C1": [row]}, chunk)
        assert (found is None) == (other == step)
