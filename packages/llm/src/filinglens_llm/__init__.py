"""LLM provider client, question router, answer generation and citation validation."""

from collections.abc import Sequence

from filinglens_core.errors import NotImplementedYetError


def embed(texts: Sequence[str], model: str) -> list[list[float]]:
    """Embed texts with `model`. The local and Cloudflare providers arrive in build step 6."""
    raise NotImplementedYetError(f"No provider can embed with {model} yet.")
