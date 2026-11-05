"""The answer reply format: the Sources block, what a stream shows, and dropping bad sentences."""

from decimal import Decimal

import pytest

from filinglens_llm.answer import INSUFFICIENT, SYSTEM, Source, Visible, check, read_reply
from filinglens_llm.validate import Calculation

CHUNK = "Services net sales increased due to higher advertising, App Store and cloud revenue."
SOURCES = {
    "F1": Source("F1", None, "7", "AAPL", "416,161,000,000 USD", Decimal(416_161_000_000), "u"),
    "C1": Source("C1", "c-1", None, "AAPL Item 7", CHUNK, None, "u"),
}
REPLY = """\
Apple's net sales were $416.2 billion in fiscal 2025 [F1]. Services grew on advertising, the App \
Store and cloud [C1].

**Sources:**
[F1] "416,161,000,000 USD"
[C1] “Services net sales increased due to higher advertising, App Store and cloud revenue”
"""


def test_the_reply_splits_into_answer_text_and_quotes_per_source() -> None:
    reply = read_reply(REPLY)
    assert reply.text.endswith("cloud [C1].")
    assert reply.quotes == {
        "F1": ["416,161,000,000 USD"],
        "C1": [CHUNK.removesuffix(".")],
    }
    assert not reply.insufficient
    assert read_reply(f"  {INSUFFICIENT}\n").insufficient


@pytest.mark.parametrize("size", range(1, 40))
def test_a_stream_shows_the_numbered_answer_and_never_the_sources_block(size: int) -> None:
    visible = Visible()
    shown = [visible.feed(REPLY[start : start + size]) for start in range(0, len(REPLY), size)]
    shown.append(visible.feed(final=True))
    streamed = "".join(shown)
    assert streamed == check(read_reply(REPLY), SOURCES).text
    assert streamed.endswith(
        "fiscal 2025 [1]. Services grew on advertising, the App Store and cloud [2]."
    )
    assert all("Sources" not in part and "[C1" not in part for part in shown)


def test_rounded_figures_keep_four_significant_digits() -> None:
    """Rule 4's floor: one decimal in billions put Haiku outside numeric exact match's 0.5% on
    dev ($4.1 billion for 4,121,000,000 in n24, $6.7 billion for 6,747,000,000 in n39; user,
    2026-11-04). Validation still passes such a figure (validate.rounded): a lapse is no refusal."""
    assert (
        "4. Give figures as the sources state them, or rounded to at least four significant"
        " digits, such as $416.2 billion or $4.121 billion." in " ".join(SYSTEM.split())
    )


def test_a_stream_shows_nothing_of_an_insufficient_evidence_reply() -> None:
    visible = Visible()
    shown = [visible.feed(part) for part in ("INSUFF", "ICIENT_EVI", "DENCE\n")]
    assert "".join(shown) + visible.feed(final=True) == ""


def test_valid_sentences_keep_their_text_and_cite_in_order_of_use() -> None:
    checked = check(read_reply(REPLY), SOURCES)
    assert checked.citations == [("F1", "416,161,000,000 USD"), ("C1", CHUNK.removesuffix("."))]
    assert (checked.problems, checked.removed) == ([], 0)


def test_a_sentence_with_an_unsupported_number_is_removed_and_markers_renumbered() -> None:
    reply = read_reply(
        "Net sales were $461.2 billion [F1]. Services grew on advertising and cloud [C1].\n"
        'Sources:\n[F1] "416,161,000,000 USD"\n'
        '[C1] "Services net sales increased due to higher advertising"\n'
    )
    checked = check(reply, SOURCES)
    assert checked.text == "Services grew on advertising and cloud [1]."
    assert checked.citations == [("C1", "Services net sales increased due to higher advertising")]
    assert checked.removed == 1
    assert "461,200,000,000" in checked.problems[0]
    assert checked.figures == []  # the dropped sentence's amount is not listed


SEGMENTS = (
    "The Company's operations are conducted in three reportable segments: Walmart U.S., Walmart"
    " International and Sam's Club U.S. The Company defines its segments as those operations"
)
WALMART = {
    "C5": Source("C5", "c-5", None, "WMT Item 1", "Walmart serves customers worldwide.", None, "u"),
    "C9": Source("C9", "c-9", None, "WMT Item 7", SEGMENTS, None, "u"),
}


@pytest.mark.parametrize("markers", ["[C5][C9]", "[C5, C9]"])
def test_a_sentence_keeps_the_cited_sources_that_hold_it(markers: str) -> None:
    """x06 (dev): C9's quote is in C9 and C5's is not, so the sentence was dropped twice and the
    answer refused; C5 adds nothing the sentence needs."""
    reply = read_reply(
        "Walmart has three reportable segments: Walmart U.S., Walmart International and Sam's"
        f" Club U.S {markers}.\n\nSources:\n"
        '[C5] "The operations are conducted in three segments, which are further described."\n'
        f'[C9] "{SEGMENTS.split(" The Company defines")[0]}"\n'
    )
    checked = check(reply, WALMART)
    assert checked.text.endswith("and Sam's Club U.S [1].")
    assert [alias for alias, _ in checked.citations] == ["C9"]
    assert (checked.problems, checked.removed, checked.pruned) == ([], 0, 1)


def test_an_amount_only_a_failing_citation_could_hold_still_drops_the_sentence() -> None:
    reply = read_reply(
        'Net sales were $416.2 billion [C1][F9].\n\nSources:\n[C1] "Services net sales increased"\n'
    )
    checked = check(reply, SOURCES)  # F9 is no source, and C1's quote holds no amount
    assert (checked.removed, checked.pruned) == (1, 0)


def test_a_source_line_may_end_with_its_own_marker() -> None:
    """x17 (dev): the regeneration wrote [C1] "quote" [C1] on every source line."""
    quote = "Services net sales increased due to higher advertising"
    reply = read_reply(f'Services grew [C1].\n\nSources:\n[C1] "{quote}" [C1]\n')
    assert reply.quotes == {"C1": [quote]}


INCREASE = "From fiscal 2024 to fiscal 2025: an increase of 25,126,000,000 USD, or 6.43%."
APPLE = {
    "F1": Source("F1", None, "7", "2025", "416,161,000,000 USD", Decimal(416_161_000_000), "u1"),
    "F2": Source("F2", None, "8", "2024", "391,035,000,000 USD", Decimal(391_035_000_000), "u2"),
    "K1": Source(
        "K1", None, None, "Calculated by FilingLens from F2 and F1", INCREASE, None, "u2",
        Calculation(("F2", "F1"), Decimal(25_126_000_000), Decimal("6.43"), over_time=True),
    ),
}  # fmt: skip


def test_a_calculation_is_cited_like_a_fact_and_holds_the_difference() -> None:
    """c09 (dev): Haiku's "an increase of about $25.1 billion" was in no source it was given."""
    reply = read_reply(
        "Net sales rose from $391.0 billion in fiscal 2024 to $416.2 billion in fiscal 2025, up"
        " $25.1 billion [F2][F1][K1].\n\nSources:\n"
        '[F2] "391,035,000,000 USD"\n[F1] "416,161,000,000 USD"\n[K1] "25,126,000,000 USD" [K1]\n'
    )
    assert reply.quotes["K1"] == ["25,126,000,000 USD"]
    checked = check(reply, APPLE)
    assert checked.text.endswith("up $25.1 billion [1][2][3].")
    assert checked.citations[2] == ("K1", INCREASE)  # its text, as a fact's value line
    assert ("$25.1 billion", "K1") in [(f.text, f.alias) for f in checked.figures]


LOWER = (
    "Fiscal 2024: 14,405,000,000 USD. Fiscal 2025: 12,056,000,000 USD. Fiscal 2025 is lower by"
    " 2,349,000,000 USD, 16.31% less than fiscal 2024."
)
UNITEDHEALTH = {  # c13 (dev): net income attributable to the parent, fiscal 2025 against 2024
    "F1": Source("F1", None, "540257", "2025", "12,056,000,000 USD", Decimal(12_056_000_000), "u"),
    "F2": Source("F2", None, "540203", "2024", "14,405,000,000 USD", Decimal(14_405_000_000), "u"),
    "K1": Source(
        "K1", None, None, "Calculated by FilingLens from F2 and F1", LOWER, None, "u",
        Calculation(("F2", "F1"), Decimal(-2_349_000_000), Decimal("-16.31"), over_time=True),
    ),
}  # fmt: skip
ANSWER = (
    "UnitedHealth Group's net income attributable to the parent was $12.1 billion in fiscal 2025,"
    " compared with $14.4 billion in fiscal 2024, a decrease of $2.3 billion or 16.31%"
)
LIST = (
    'Sources: [F1] "12,056,000,000 USD"; [F2] "14,405,000,000 USD"; [K1] "Fiscal 2025 is lower by'
    ' 2,349,000,000 USD, 16.31% less than fiscal 2024."'
)
INLINE = f"{ANSWER} [F1][F2][K1]. {LIST}"  # E5's draft of c13, as Haiku wrote it
ENDS_LINE = (  # n40's layout (dev, rule 4 run): the heading ends the answer's line
    f"{ANSWER} [F1][F2][K1]. Sources:\n"
    '[F1] "12,056,000,000 USD"\n[F2] "14,405,000,000 USD"\n'
    '[K1] "Fiscal 2025 is lower by 2,349,000,000 USD, 16.31% less than fiscal 2024."'
)
DRAFTS = pytest.mark.parametrize(
    "draft",
    [INLINE, f"{ANSWER} [F1][F2][K1].\n{LIST}", ENDS_LINE],
    ids=["after the answer", "own line", "ends the answer's line"],
)


@DRAFTS
def test_a_sources_block_written_inline_is_read_as_the_sources_block(draft: str) -> None:
    """c13 (dev, E5): the list stayed in the answer as one more sentence, and its amounts passed."""
    reply = read_reply(draft)
    assert reply.text == f"{ANSWER} [F1][F2][K1]."
    assert reply.quotes == {
        "F1": ["12,056,000,000 USD"],
        "F2": ["14,405,000,000 USD"],
        "K1": ["Fiscal 2025 is lower by 2,349,000,000 USD, 16.31% less than fiscal 2024."],
    }
    checked = check(reply, UNITEDHEALTH)
    assert checked.text == f"{ANSWER} [1][2][3]."
    assert (checked.problems, checked.removed) == ([], 0)


@pytest.mark.parametrize(
    "sentence",
    [
        "Sources: products and services, as the filing lists them [C1].",  # no source follows
        "Services had three such sources: [C1].",  # not where a sentence starts
        "Sources:\nproducts and services, as the filing lists them [C1].",  # no source line next
    ],
)
def test_the_word_sources_in_the_answer_is_no_heading(sentence: str) -> None:
    reply = read_reply(
        f"Net sales were $416.2 billion [F1]. {sentence}\n\nSources:\n"
        '[F1] "416,161,000,000 USD"\n[C1] "Services net sales increased"\n'
    )
    assert reply.text == f"Net sales were $416.2 billion [F1]. {sentence}"
    assert reply.quotes == {"F1": ["416,161,000,000 USD"], "C1": ["Services net sales increased"]}


@DRAFTS
@pytest.mark.parametrize("size", range(1, 40))
def test_a_stream_never_shows_a_sources_block_written_inline(draft: str, size: int) -> None:
    """n13 (dev ci, 2026-10-16) at a few characters a chunk: a reply ending in "Sources:" read as
    the heading, then not once its source followed, so the stream showed text twice."""
    visible = Visible()
    shown = [visible.feed(draft[start : start + size]) for start in range(0, len(draft), size)]
    shown.append(visible.feed(final=True))
    assert "".join(shown) == f"{ANSWER} [1][2][3]."


def test_each_amount_a_kept_sentence_states_comes_with_the_source_that_holds_it() -> None:
    checked = check(read_reply(REPLY), SOURCES)
    assert [(f.text, f.alias, f.number) for f in checked.figures] == [
        ("$416.2 billion", "F1", Decimal(416_161_000_000))
    ]
