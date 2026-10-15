"""Local models on the CPU: the embedders behind the chunk embedding columns, and the reranker.

Weights come from the Hugging Face cache (HF_HOME, on H: here). `make models` fetches the pinned
revisions once; tests and containers then load them offline (HF_HUB_OFFLINE=1).
"""

import threading
from collections.abc import Sequence
from functools import cache
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:  # torch loads only in processes that run a model
    from sentence_transformers import CrossEncoder, SentenceTransformer

# Pinned commits: the embedders of the chunk columns (bge-small's is also the chunker's vendored
# tokenizer) and the rerankers that RERANK_MODEL may name.
REVISIONS = {
    "BAAI/bge-small-en-v1.5": "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
    "BAAI/bge-base-en-v1.5": "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a",
    "cross-encoder/ms-marco-TinyBERT-L-2-v2": "81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc",
    "cross-encoder/ms-marco-MiniLM-L-2-v2": "1b5cd67b15209f24824c50370e0397743aa9b787",
    "cross-encoder/ms-marco-MiniLM-L-6-v2": "233902d25c440f23af6f7d6e94d2946bac0bee0a",
}
# What sentence-transformers reads; skips the ONNX and OpenVINO copies in the same repos.
FILES = ["*.json", "*.txt", "model.safetensors"]
# The bge model cards' instruction for short queries against passages; passages get none.
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
_rerank_lock = threading.Lock()


@cache
def embedder(model: str) -> "SentenceTransformer":
    """The model, loaded on first use; callers on a deadline load it first, outside the clock."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model, revision=REVISIONS[model], device="cpu")


@cache
def reranker(model: str, max_tokens: int) -> "CrossEncoder":
    """The cross-encoder, reading at most `max_tokens` of each (query, text) pair."""
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model, revision=REVISIONS[model], device="cpu", max_length=max_tokens)


def embed(texts: Sequence[str], model: str, *, query: bool = False) -> list[list[float]]:
    """Unit-length vectors; a query gets the model's instruction prefix (bge: BGE_QUERY_PREFIX)."""
    prefix = BGE_QUERY_PREFIX if query and model.startswith("BAAI/bge-") else None
    vectors = embedder(model).encode(  # pyright: ignore[reportUnknownMemberType]
        list(texts), prompt=prefix, normalize_embeddings=True, convert_to_numpy=True
    )
    return cast(list[list[float]], vectors.tolist())


def rerank(
    query: str,
    texts: Sequence[str],
    *,
    model: str,
    max_tokens: int,
    abandoned: threading.Event | None = None,
) -> list[float] | None:
    """Cross-encoder relevance of each text to `query` (higher is better), one call at a time.

    torch already spreads one call over every core, so calls queue on a lock. A call whose caller
    gave up while it waited (`abandoned` set) returns None without running the model.
    """
    encoder = reranker(model, max_tokens)
    with _rerank_lock:
        if abandoned is not None and abandoned.is_set():
            return None
        pairs = [(query, text) for text in texts]
        scores = encoder.predict(pairs, convert_to_numpy=True)  # pyright: ignore[reportUnknownMemberType]
        return cast(list[float], scores.tolist())


def download() -> None:
    """Fetch every pinned model into the Hugging Face cache (HF_HOME); run once, outside tests."""
    from huggingface_hub import snapshot_download  # pyright: ignore[reportUnknownVariableType]

    for repo, revision in REVISIONS.items():
        path: str = snapshot_download(repo, revision=revision, allow_patterns=FILES)
        print(f"{repo}@{revision[:8]}: {path}")


if __name__ == "__main__":
    download()
