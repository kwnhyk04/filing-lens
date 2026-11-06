"""The re-parse audit's comparison: what today's parser would change in a filing's stored chunks."""

from pathlib import Path

from filinglens_ingest.parsing import parse_filing
from filinglens_ingest.reparse import compare, fresh_chunks

FIXTURES = Path(__file__).with_name("fixtures")
ACCESSION = "0000320193-25-000079"
PARSED = parse_filing((FIXTURES / "aapl-10k-2025.htm").read_text(encoding="utf-8"), "10-K")


def test_a_filing_stored_as_todays_parser_cuts_it_is_not_affected() -> None:
    stored = fresh_chunks(PARSED, ACCESSION)
    audit = compare(ACCESSION, stored, PARSED)
    assert not audit.affected
    assert (audit.changed, audit.added, audit.kept) == ([], 0, len(stored))


def test_a_changed_or_old_chunk_is_listed_and_a_new_one_counted() -> None:
    fresh = fresh_chunks(PARSED, ACCESSION)
    edited, lost, *rest = fresh
    stored = {edited: "Net sales were | 1,234", "old": "an old chunk"}
    stored |= {chunk: fresh[chunk] for chunk in rest}
    audit = compare(ACCESSION, stored, PARSED)
    assert audit.affected
    assert sorted(audit.changed) == sorted([edited, "old"])
    assert audit.added == 1  # `lost`, which the store does not hold
    assert audit.kept == len(rest)
    assert lost not in audit.changed


def test_the_digits_a_parse_would_restore_are_counted() -> None:
    fresh = fresh_chunks(PARSED, ACCESSION)
    stored = {chunk: "".join(c for c in text if not c.isdigit()) for chunk, text in fresh.items()}
    audit = compare(ACCESSION, stored, PARSED)
    assert audit.digits == sum(c.isdigit() for text in fresh.values() for c in text)
