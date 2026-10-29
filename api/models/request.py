"""Модели запросов API"""
from pydantic import BaseModel, Field
from typing import Optional


class AskRequest(BaseModel):
    """Запрос на ответ на вопрос"""
    q: str = Field(..., description="Вопрос пользователя", min_length=1)
    use_hybrid: Optional[bool] = Field(False, description="Использовать гибридный поиск (BM25 + векторный)")


class IngestRequest(BaseModel):
    """Запрос на индексацию данных (опционально, может быть пустым)"""
    pass

