"""Модели ответов API"""
from pydantic import BaseModel, Field
from typing import List


class Source(BaseModel):
    """Источник информации для ответа"""
    title: str
    id: str
    dist: float = Field(..., description="Расстояние в векторном пространстве")


class AskResponse(BaseModel):
    """Ответ на вопрос пользователя"""
    answer: str
    sources: List[Source]


class IngestResponse(BaseModel):
    """Ответ на запрос индексации"""
    indexed_chunks: int

