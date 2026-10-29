"""Клиент для работы с ChromaDB"""
from __future__ import annotations
import os
# Принудительно отключаем GPU для PyTorch и sentence-transformers
os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.environ['TRANSFORMERS_NO_CUDA'] = '1'

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
        print(f"Loading embedder: {settings.embed_model} (CPU mode)")
        # First prefer the persistent local Hugging Face cache. It avoids slow
        # metadata checks on every container restart. A brand-new deployment
        # falls back to one network download and then populates that cache.
        try:
            _embedder = SentenceTransformer(
                settings.embed_model,
                device="cpu",
                local_files_only=True,
            )
            print("Loaded embedder from local cache")
        except OSError:
            _embedder = SentenceTransformer(settings.embed_model, device="cpu")
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


def get_client() -> chromadb.PersistentClient:
    """Получить клиент ChromaDB (ленивая загрузка)"""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=settings.chroma_dir)
    return _client


def reset_collection_cache():
    """Сбрасывает кэш коллекции (для использования после очистки индекса)"""
    global _collection
    _collection = None
