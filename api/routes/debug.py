"""Debug эндпоинты для отладки и разработки"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from api.chroma.search import search
from api.chroma.hybrid import hybrid_search
from api.chroma.client import get_embedder

router = APIRouter(prefix="/api/debug", tags=["Debug"])


class EmbedRequest(BaseModel):
    """Запрос на создание эмбеддинга"""
    text: str


class EmbedResponse(BaseModel):
    """Ответ с эмбеддингом"""
    embedding: List[float]
    dimension: int


class SearchDebugRequest(BaseModel):
    """Запрос на отладочный поиск"""
    q: str
    top_k: Optional[int] = 10
    use_hybrid: Optional[bool] = False


class SearchDebugResponse(BaseModel):
    """Ответ с отладочной информацией"""
    query: str
    expanded_query: Optional[str] = None
    results_count: int
    results: List[dict]
    search_type: str


@router.post("/embed", response_model=EmbedResponse)
async def create_embedding(request: EmbedRequest):
    """
    Создает эмбеддинг для текста (для тестирования и отладки)
    
    Args:
        request: Текст для создания эмбеддинга
        
    Returns:
        Эмбеддинг и его размерность
    """
    try:
        embedder = get_embedder()
        embedding = embedder.encode([request.text])[0].tolist()
        return EmbedResponse(
            embedding=embedding,
            dimension=len(embedding)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка создания эмбеддинга: {str(e)}")


@router.post("/search", response_model=SearchDebugResponse)
async def debug_search(request: SearchDebugRequest):
    """
    Отладочный поиск с детальной информацией о результатах
    
    Args:
        request: Параметры поиска
        
    Returns:
        Детальная информация о результатах поиска
    """
    try:
        query = request.q.strip()
        if not query:
            raise HTTPException(status_code=400, detail="Запрос не может быть пустым")
        
        # Выполняем поиск
        if request.use_hybrid:
            results = hybrid_search(query, top_k=request.top_k)
            search_type = "hybrid"
        else:
            results = search(query, top_k=request.top_k)
            search_type = "vector"
        
        # Формируем детальную информацию
        debug_results = []
        for idx, result in enumerate(results, 1):
            debug_results.append({
                "rank": idx,
                "title": result.meta.get("title", "Без названия"),
                "article_id": result.meta.get("article_id"),
                "distance": result.dist,
                "chunk_index": result.meta.get("chunk_index"),
                "preview": result.doc[:200] + "..." if len(result.doc) > 200 else result.doc
            })
        
        return SearchDebugResponse(
            query=query,
            results_count=len(results),
            results=debug_results,
            search_type=search_type
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка поиска: {str(e)}")

