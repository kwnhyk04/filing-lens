"""The answer reply format: the Sources block, what a stream shows, and dropping bad sentences."""

from decimal import Decimal

import pytest

from filinglens_llm.answer import INSUFFICIENT, Source, Visible, check, read_reply

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
