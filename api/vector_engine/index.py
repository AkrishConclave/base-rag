"""Immutable in-memory vector index backed by a native C top-K routine."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from api.chroma.schema import SearchResult

try:
    import rag_vector_native
except ImportError as exc:  # pragma: no cover - installation error, not a search fallback
    rag_vector_native = None
    _native_import_error = exc
else:
    _native_import_error = None


def _normalise(vector: np.ndarray) -> np.ndarray:
    result = np.ascontiguousarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(result))
    if norm == 0.0:
        raise ValueError("Embedding must not be a zero vector")
    return result / norm


@dataclass(frozen=True)
class InMemoryVectorIndex:
    """Read-only corpus with separate candidate lists for public and staff searches."""

    vectors: np.ndarray
    documents: tuple[str, ...]
    metadatas: tuple[dict[str, Any], ...]
    public_indices: np.ndarray
    all_indices: np.ndarray

    @classmethod
    def create(
        cls,
        embeddings: Sequence[Sequence[float]],
        documents: Sequence[str],
        metadatas: Sequence[dict[str, Any]],
    ) -> "InMemoryVectorIndex":
        vectors = np.asarray(embeddings, dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[0] == 0:
            raise ValueError("Embeddings must be a non-empty two-dimensional array")
        if vectors.shape[0] != len(documents) or len(documents) != len(metadatas):
            raise ValueError("Embeddings, documents, and metadata must have equal lengths")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if np.any(norms == 0.0):
            raise ValueError("Embeddings must not contain zero vectors")
        vectors = np.ascontiguousarray(vectors / norms, dtype=np.float32)
        all_indices = np.arange(vectors.shape[0], dtype=np.int64)
        public_indices = np.ascontiguousarray(
            [index for index, meta in enumerate(metadatas) if meta.get("status") == 1],
            dtype=np.int64,
        )
        return cls(vectors, tuple(documents), tuple(metadatas), public_indices, all_indices)

    def search(self, embedding: Sequence[float], top_k: int, admin_mode: bool) -> list[SearchResult]:
        if rag_vector_native is None:
            raise RuntimeError(
                "Native vector engine is not installed. Build it with `pip install .`."
            ) from _native_import_error
        if top_k <= 0:
            return []
        query = _normalise(np.asarray(embedding, dtype=np.float32))
        if query.ndim != 1 or query.shape[0] != self.vectors.shape[1]:
            raise ValueError("Embedding dimension does not match the loaded vector index")
        candidates = self.all_indices if admin_mode else self.public_indices
        hits = rag_vector_native.cosine_top_k(self.vectors, query, self.vectors.shape[0], self.vectors.shape[1], top_k, candidates)
        return [
            SearchResult(doc=self.documents[index], meta=self.metadatas[index], dist=max(0.0, 1.0 - score))
            for index, score in hits
        ]


_index: InMemoryVectorIndex | None = None
_index_lock = threading.Lock()


def replace_index(index: InMemoryVectorIndex) -> None:
    """Atomically publish a completely built index to concurrent readers."""
    global _index
    with _index_lock:
        _index = index


def clear_index() -> None:
    global _index
    with _index_lock:
        _index = None


def load_index_from_collection(collection: Any) -> int:
    """Restore RAM state from the durable Chroma collection after an API restart."""
    count = collection.count()
    if count == 0:
        clear_index()
        return 0
    data = collection.get(
        limit=count,
        include=["embeddings", "documents", "metadatas"],
    )
    embeddings = data.get("embeddings")
    documents = data.get("documents")
    metadatas = data.get("metadatas")
    if embeddings is None or documents is None or metadatas is None:
        raise RuntimeError("Chroma collection did not return embeddings, documents, and metadata")
    replace_index(InMemoryVectorIndex.create(embeddings, documents, metadatas))
    return len(documents)


def search_index(embedding: Sequence[float], top_k: int, admin_mode: bool) -> list[SearchResult]:
    index = _index
    if index is None:
        raise RuntimeError("In-memory vector index is not loaded. Run /api/ingest first.")
    return index.search(embedding, top_k, admin_mode)
