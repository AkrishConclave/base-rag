"""Model-specific input formatting for asymmetric E5 retrieval."""
from __future__ import annotations

from collections.abc import Sequence


def as_query(text: str) -> str:
    """Format an end-user search request as required by multilingual E5."""
    return f"query: {text.strip()}"


def as_passage(text: str) -> str:
    """Format a knowledge-base chunk as required by multilingual E5."""
    return f"passage: {text.strip()}"


def encode_query(embedder, text: str):
    """Encode one query with the E5 retrieval prefix and L2 normalisation."""
    return embedder.encode([as_query(text)], normalize_embeddings=True)[0]


def encode_passages(embedder, documents: Sequence[str], batch_size: int):
    """Encode corpus chunks with the E5 passage prefix and L2 normalisation."""
    return embedder.encode(
        [as_passage(document) for document in documents],
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
