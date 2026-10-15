"""Token-aware chunks for embedding model A, BAAI/bge-small-en-v1.5 (512 tokens with [CLS], [SEP]).

A chunk holds at most MAX_TOKENS tokens of its section and repeats the last OVERLAP_TOKENS (or a
few more, to start on a whole word) of the chunk before it. It ends at a line break, or else after
a sentence, when one falls in its last quarter. The tokenizer file is the model's own, pinned to
Hugging Face commit 5c38ec7c405ec4b44b94cc5a9bb96e735b38267a (MIT licence), so nothing downloads.
"""

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from tokenizers import Tokenizer

MAX_TOKENS = 384
OVERLAP_TOKENS = 64
MODEL_LIMIT = 512  # bge-small-en-v1.5, [CLS] and [SEP] included
TOKENIZER_FILE = Path(__file__).with_name("tokenizer-bge-small-en-v1.5.json")
SENTENCE_ENDS = frozenset({".", "?", "!"})


@dataclass(frozen=True)
class Piece:
    start: int  # offsets in the text that was split
    end: int
    token_count: int  # without [CLS] and [SEP]


@cache
def tokenizer() -> Tokenizer:
    return Tokenizer.from_file(str(TOKENIZER_FILE))


def split(text: str) -> list[Piece]:
    """Overlapping pieces that cover `text` from its first token to its last."""
    encoding = tokenizer().encode(text, add_special_tokens=False)
    offsets, words = encoding.offsets, encoding.word_ids
    count = len(offsets)
    pieces: list[Piece] = []
    first = 0
    while first < count:
        last = min(first + MAX_TOKENS, count)  # exclusive
        if last < count:
            last = _break(text, offsets, words, first, last)
        pieces.append(Piece(offsets[first][0], offsets[last - 1][1], last - first))
        if last == count:
            break
        previous = first
        first = max(last - OVERLAP_TOKENS, previous + 1)
        while first > previous + 1 and words[first] == words[first - 1]:  # start on a whole word
            first -= 1
    return pieces


def _break(
    text: str,
    offsets: list[tuple[int, int]],
    words: list[int | None],
    first: int,
    last: int,
) -> int:
    """Where the piece starting at token `first` should end, at most at token `last`."""
    floor = first + MAX_TOKENS * 3 // 4
    for end in range(last, floor, -1):  # a line break between tokens end - 1 and end
        if "\n" in text[offsets[end - 1][1] : offsets[end][0]]:
            return end
    for end in range(last, floor, -1):
        if text[offsets[end - 1][0] : offsets[end - 1][1]] in SENTENCE_ENDS:
            return end
    for end in range(last, first + 1, -1):  # never inside a word
        if words[end] != words[end - 1]:
            return end
    return last
