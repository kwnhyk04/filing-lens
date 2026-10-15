"""Chunker properties on every section of the two fixture 10-Ks and on text without breaks."""

from itertools import pairwise
from pathlib import Path

from filinglens_db.models import chunk_id
from filinglens_ingest.chunking import MAX_TOKENS, MODEL_LIMIT, OVERLAP_TOKENS, split, tokenizer
from filinglens_ingest.parsing import parse_filing

FIXTURES = Path(__file__).with_name("fixtures")
FILINGS = {"aapl-10k-2025.htm": "0000320193-25-000079", "fcx-10k-2025.htm": "0000831259-26-000012"}
# No line or sentence break, and words that WordPiece cuts into several tokens.
RUN_ON = " ".join(f"supercalifragilistic{n} intercontinental" for n in range(1500))


def sections() -> list[tuple[str, str, str, int]]:
    """(accession number, item, text, offset in the filing) of every fixture section."""
    found: list[tuple[str, str, str, int]] = []
    for name, accession in FILINGS.items():
        parsed = parse_filing((FIXTURES / name).read_text(encoding="utf-8"), "10-K")
        found += [
            (accession, s.item, parsed.text[s.start : s.end], s.start) for s in parsed.sections
        ]
    return found


def test_pieces_fit_the_model_overlap_and_reassemble_to_the_text() -> None:
    texts = [text for _, _, text, _ in sections()] + [RUN_ON, "Item 4. None."]
    for text in texts:
        pieces = split(text)
        assert (pieces[0].start, pieces[-1].end) == (0, len(text))
        rebuilt = text[pieces[0].start : pieces[0].end]
        for before, after in pairwise(pieces):
            assert before.start < after.start <= before.end  # overlapping, never a gap
            overlap = tokenizer().encode(text[after.start : before.end], add_special_tokens=False)
            assert len(overlap.ids) >= OVERLAP_TOKENS
            rebuilt += text[before.end : after.end]
        assert rebuilt == text
        for piece in pieces:
            assert piece.token_count <= MAX_TOKENS
            assert len(tokenizer().encode(text[piece.start : piece.end]).ids) <= MODEL_LIMIT
    assert len(split(RUN_ON)) > 1
    assert split("") == []


def test_chunk_ids_are_deterministic_and_unique() -> None:
    def ids() -> list[str]:
        return [
            chunk_id(accession, item, offset + piece.start)
            for accession, item, text, offset in sections()
            for piece in split(text)
        ]

    first = ids()
    assert first == ids()
    assert len(set(first)) == len(first)
