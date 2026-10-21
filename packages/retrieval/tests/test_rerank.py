"""The reranker's wait, on a stand-in model: nothing is loaded."""

import asyncio
import threading
from collections.abc import Sequence

import pytest

import filinglens_retrieval as retrieval


async def test_a_cancelled_search_lets_its_queued_rerank_skip_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued, lock_free, finished = threading.Event(), threading.Event(), threading.Event()
    skipped: list[bool] = []

    def rerank(
        q: str, texts: Sequence[str], *, model: str, max_tokens: int, abandoned: threading.Event
    ) -> list[float] | None:
        queued.set()
        lock_free.wait(5)  # another search's rerank holds the lock
        skipped.append(abandoned.is_set())  # the real rerank returns None here, model unrun
        finished.set()
        return None

    monkeypatch.setattr(retrieval, "reranker", lambda model, max_tokens: None)
    monkeypatch.setattr(retrieval, "rerank", rerank)
    task = asyncio.create_task(retrieval._rerank("q", ["a passage"], "model", 512, 60.0))
    await asyncio.to_thread(queued.wait, 5)
    task.cancel()  # the guessed search the plan did not use
    with pytest.raises(asyncio.CancelledError):
        await task
    lock_free.set()
    await asyncio.to_thread(finished.wait, 5)
    assert skipped == [True]
