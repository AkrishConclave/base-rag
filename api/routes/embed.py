"""Эндпоинт для создания эмбеддингов"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from api.chroma.client import get_embedder
from api.chroma.embeddings import encode_query
from api.utils.security import verify_admin_token

router = APIRouter(
    prefix="/api",
    tags=["Embed"],
    dependencies=[Depends(verify_admin_token)],
)


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
        embedding = await asyncio.to_thread(encode_query, embedder, request.text)
        embedding = embedding.tolist()
        return EmbedResponse(
            embedding=embedding,
            dimension=len(embedding)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка создания эмбеддинга: {str(e)}")

