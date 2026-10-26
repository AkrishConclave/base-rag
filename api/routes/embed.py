"""Эндпоинт для создания эмбеддингов"""
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from api.chroma.client import get_embedder

router = APIRouter(prefix="/api", tags=["Embed"])


class EmbedRequest(BaseModel):
    """Запрос на создание эмбеддинга"""
    text: str


class EmbedResponse(BaseModel):
    """Ответ с эмбеддингом"""
    embedding: List[float]
    dimension: int


@router.post("/embed", response_model=EmbedResponse)
async def create_embedding(request: EmbedRequest):
    """
    Создает эмбеддинг для текста
    
    Полезно для:
    - Тестирования моделей эмбеддингов
    - Создания эмбеддингов вручную
    - Отладки качества эмбеддингов
    
    Args:
        request: Текст для создания эмбеддинга
        
    Returns:
        Эмбеддинг и его размерность
    """
    try:
        embedder = get_embedder()
        embeddings = await asyncio.to_thread(embedder.encode, [request.text])
        embedding = embeddings[0].tolist()
        return EmbedResponse(
            embedding=embedding,
            dimension=len(embedding)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка создания эмбеддинга: {str(e)}")

