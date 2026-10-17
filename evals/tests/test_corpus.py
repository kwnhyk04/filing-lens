"""The CI corpus dump's guards, on synthetic input: no database or Docker."""

import io
from pathlib import Path

import pytest

from evals import corpus

TOC = """;
; Archive created at 2026-10-17 09:00:00 UTC
5160; 0 16400 TABLE DATA public chunks filinglens
5161; 0 16410 TABLE DATA public financial_facts filinglens
5162; 1259 16420 TABLE public eval_runs filinglens
5163; 1259 16430 INDEX public ix_chunks_tsv filinglens
5164; 0 0 SEQUENCE SET public eval_runs_id_seq filinglens
"""


def test_the_dump_lists_table_rows_and_sequence_values_it_holds() -> None:
    held = corpus.data_entries(TOC)
    assert held == {"chunks", "financial_facts", "eval_runs_id_seq"}  # eval_runs: schema only


def test_a_secret_split_across_two_blocks_is_still_found() -> None:
    text = b"x" * ((1 << 20) - 3) + b"s3cr3t-value" + b"y" * 10
    assert corpus.leaks(io.BytesIO(text), [b"absent-value", b"s3cr3t-value"]) == {1}


def test_secret_named_variables_and_the_sec_contact_are_searched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "not-a-real-key")
    monkeypatch.setenv("POSTGRES_PASSWORD", "short")  # too short to tell from filing text
    monkeypatch.setenv("SEC_USER_AGENT", "FilingLens Jane jane@mail.net")
    found = corpus.secrets()
    assert found["GROQ_API_KEY"] == [b"not-a-real-key"]
    assert "POSTGRES_PASSWORD" not in found
    assert found["SEC_USER_AGENT"] == [b"FilingLens Jane jane@mail.net", b"jane@mail.net"]


def test_a_restore_refuses_a_file_whose_sha256_differs(tmp_path: Path) -> None:
    path = tmp_path / "corpus.dump"
    path.write_bytes(b"not the published dump")
    with pytest.raises(SystemExit, match="sha256"):
        corpus.check(path, "0" * 64)
    corpus.check(path, corpus.sha256(path))
