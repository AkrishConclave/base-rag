"""Роуты API"""
from .rag import router as rag_router
from .ingest import router as ingest_router
from .embed import router as embed_router
from .debug import router as debug_router

__all__ = ["rag_router", "ingest_router", "embed_router", "debug_router"]

