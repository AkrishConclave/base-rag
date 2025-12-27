"""Схемы данных для ChromaDB"""
from pydantic import BaseModel
from typing import Any


class SearchResult(BaseModel):
    """Результат поиска в ChromaDB"""
    doc: str
    meta: dict[str, Any]
    dist: float

