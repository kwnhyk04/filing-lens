"""Local models, loaded offline from the Hugging Face cache (make models fills it)."""

import math
import threading

from filinglens_llm.local import BGE_QUERY_PREFIX, embed, embedder, rerank

MODEL_A = "BAAI/bge-small-en-v1.5"
RERANKER = "cross-encoder/ms-marco-TinyBERT-L-2-v2"
PASSAGES = [
    "Gross margin increased due to a favorable mix of services and lower component costs.",
    "The Company leases office space in Cupertino, California.",
]


def test_passages_embed_as_unit_vectors_of_model_a_dimensions() -> None:
    vectors = embed(PASSAGES, MODEL_A)
    assert [len(vector) for vector in vectors] == [384, 384]
    assert all(math.isclose(math.hypot(*vector), 1.0, abs_tol=1e-4) for vector in vectors)


def test_a_query_gets_the_model_cards_instruction_and_a_passage_does_not() -> None:
    question = "What drove the change in gross margin?"
    [as_query] = embed([question], MODEL_A, query=True)
    [as_passage] = embed([question], MODEL_A)
    [by_hand] = (
        embedder(MODEL_A)
        .encode(  # pyright: ignore[reportUnknownMemberType]
            [BGE_QUERY_PREFIX + question], normalize_embeddings=True
        )
        .tolist()
    )
    assert BGE_QUERY_PREFIX == "Represent this sentence for searching relevant passages: "
    assert all(math.isclose(a, b, abs_tol=1e-5) for a, b in zip(as_query, by_hand, strict=True))
    assert as_query != as_passage


def test_the_reranker_puts_the_relevant_passage_first() -> None:
    scores = rerank("What drove gross margin?", PASSAGES, model=RERANKER, max_tokens=512)
    assert scores is not None
    assert scores[0] > scores[1]


def test_an_abandoned_rerank_skips_the_model() -> None:
    gave_up = threading.Event()
    gave_up.set()
    assert rerank("q", PASSAGES, model=RERANKER, max_tokens=512, abandoned=gave_up) is None
