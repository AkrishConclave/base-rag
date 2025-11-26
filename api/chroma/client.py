"""Клиент для работы с ChromaDB"""
from __future__ import annotations
import chromadb
from sentence_transformers import SentenceTransformer
from api.config import settings

# Ленивая инициализация
_embedder: SentenceTransformer | None = None
_client: chromadb.PersistentClient | None = None
_collection: chromadb.Collection | None = None


def get_embedder() -> SentenceTransformer:
    """Получить или создать embedder для создания эмбеддингов"""
    global _embedder
    if _embedder is None:
        print(f"Loading embedder: {settings.embed_model}")
        _embedder = SentenceTransformer(settings.embed_model)
    return _embedder


def get_collection() -> chromadb.Collection:
    """Получить коллекцию ChromaDB (ленивая загрузка)"""
    global _client, _collection
    if _client is None:
        _client = chromadb.PersistentClient(path=settings.chroma_dir)
    if _collection is None:
        try:
            _collection = _client.get_collection(settings.chroma_collection_name)
        except Exception as e:
            raise Exception(
                f"Коллекция '{settings.chroma_collection_name}' не найдена. "
                "Сначала выполните индексацию через /ingest endpoint."
            ) from e
    return _collection

