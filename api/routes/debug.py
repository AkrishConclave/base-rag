"""Debug эндпоинты для отладки и разработки"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from api.chroma.search import search
from api.chroma.hybrid import hybrid_search
from api.chroma.client import get_embedder, get_collection
from api.llm.cache import get_cache
from api.llm.prompt_refine import expand_query_with_llm

logger = logging.getLogger(__name__)
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
    admin_mode: Optional[bool] = False


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
            results = hybrid_search(query, top_k=request.top_k, admin_mode=request.admin_mode)
            search_type = "hybrid"
        else:
            results = search(query, top_k=request.top_k, admin_mode=request.admin_mode)
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


class CheckIdsRequest(BaseModel):
    """Запрос на проверку article_id"""
    start_id: int
    end_id: int


class CheckIdsResponse(BaseModel):
    """Ответ с результатами проверки ID"""
    start_id: int
    end_id: int
    found_count: int
    missing_count: int
    found_ids: List[dict]
    missing_ids: List[int]


@router.post("/check-ids", response_model=CheckIdsResponse)
async def check_article_ids(request: CheckIdsRequest):
    """
    Проверяет наличие записей с article_id в указанном диапазоне
    
    Args:
        request: Диапазон ID для проверки
        
    Returns:
        Информация о найденных и отсутствующих ID
    """
    try:
        from api.chroma.client import get_collection
        
        collection = get_collection()
        found_ids = []
        missing_ids = []
        
        for article_id in range(request.start_id, request.end_id + 1):
            article_id_str = str(article_id)
            
            try:
                results = collection.get(
                    where={"article_id": article_id_str},
                    include=["documents", "metadatas"]
                )
                
                if results["ids"]:
                    chunk_count = len(results["ids"])
                    # Получаем уникальные метаданные для этого article_id
                    titles = set()
                    statuses = set()
                    for meta in results["metadatas"]:
                        if meta.get("title"):
                            titles.add(meta.get("title"))
                        if meta.get("status") is not None:
                            statuses.add(meta.get("status"))
                    
                    title = list(titles)[0] if titles else "Без названия"
                    status = list(statuses)[0] if statuses else None
                    
                    found_ids.append({
                        "article_id": article_id,
                        "chunks": chunk_count,
                        "title": title,
                        "status": status
                    })
                else:
                    missing_ids.append(article_id)
            except Exception as e:
                missing_ids.append(article_id)
        
        return CheckIdsResponse(
            start_id=request.start_id,
            end_id=request.end_id,
            found_count=len(found_ids),
            missing_count=len(missing_ids),
            found_ids=found_ids,
            missing_ids=missing_ids
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при проверке ID: {str(e)}")


class ClearIndexResponse(BaseModel):
    """Ответ на очистку индекса"""
    success: bool
    message: str
    deleted_count: Optional[int] = None


@router.delete("/clear-index", response_model=ClearIndexResponse)
async def clear_index():
    """
    Очищает все данные из ChromaDB индекса (удаляет коллекцию)
    
    Returns:
        Результат операции очистки
    """
    try:
        from api.chroma.client import get_collection, reset_collection_cache
        from api.config import settings
        import chromadb
        
        collection = get_collection()
        
        # Получаем количество записей перед удалением
        deleted_count = 0
        try:
            count_result = collection.get(include=["documents"])
            ids = count_result.get("ids", [])
            deleted_count = len(ids)
            
            # Если есть записи, удаляем их по ID
            if ids:
                collection.delete(ids=ids)
                logger.info(f"Удалено {deleted_count} записей из коллекции")
            else:
                logger.info("Коллекция уже пуста")
        except Exception as e:
            logger.warning(f"Не удалось получить количество записей: {e}")
            # Пробуем удалить коллекцию через клиент
            try:
                from api.chroma.client import get_client
                client = get_client()
                client.delete_collection(settings.chroma_collection_name)
                logger.info("Коллекция удалена через клиент")
            except Exception as delete_error:
                logger.error(f"Ошибка при удалении коллекции: {delete_error}")
                raise
        
        # Сбрасываем глобальный кэш коллекции для пересоздания при следующем запросе
        reset_collection_cache()
        
        logger.info(f"Индекс очищен. Удалено записей: {deleted_count}")
        
        return ClearIndexResponse(
            success=True,
            message=f"Индекс успешно очищен",
            deleted_count=deleted_count if deleted_count > 0 else None
        )
    except Exception as e:
        logger.error(f"Ошибка при очистке индекса: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при очистке индекса: {str(e)}")


class ClearCacheResponse(BaseModel):
    """Ответ на очистку кэша"""
    success: bool
    message: str
    cache_type: str


class CacheStatsResponse(BaseModel):
    """Ответ со статистикой кэша"""
    enabled: bool
    cache_type: str
    ttl_seconds: int
    total_entries: int
    oldest_entry: Optional[str] = None
    newest_entry: Optional[str] = None
    total_size_bytes: int
    error: Optional[str] = None


@router.delete("/clear-cache", response_model=ClearCacheResponse)
async def clear_cache():
    """
    Очищает весь кэш запросов LLM
    
    Returns:
        Результат операции очистки кэша
    """
    try:
        cache = get_cache()
        cache_type = cache.cache_type
        
        # Очищаем кэш
        cache.clear()
        
        logger.info(f"Кэш очищен (тип: {cache_type})")
        
        return ClearCacheResponse(
            success=True,
            message="Кэш успешно очищен",
            cache_type=cache_type
        )
    except Exception as e:
        logger.error(f"Ошибка при очистке кэша: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при очистке кэша: {str(e)}")


@router.get("/cache-stats", response_model=CacheStatsResponse)
async def get_cache_stats():
    """
    Возвращает статистику кэша LLM
    
    Returns:
        Статистика кэша: количество записей, размер, время создания и т.д.
    """
    try:
        cache = get_cache()
        stats = cache.get_stats()
        
        return CacheStatsResponse(**stats)
    except Exception as e:
        logger.error(f"Ошибка при получении статистики кэша: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при получении статистики кэша: {str(e)}")


class LLMTestRequest(BaseModel):
    """Запрос на тест LLM"""
    query: str = "тестовый запрос"


class LLMTestResponse(BaseModel):
    """Ответ на тест LLM"""
    success: bool
    query: str
    expanded_query: Optional[str] = None
    error: Optional[str] = None
    provider: str
    model: str
    response_time_ms: Optional[float] = None


@router.post("/test-llm", response_model=LLMTestResponse)
async def test_llm_connection(request: LLMTestRequest):
    """
    Проверяет соединение с LLM для расширения запросов
    
    Args:
        request: Тестовый запрос
        
    Returns:
        Результат теста LLM
    """
    import time
    
    query = request.query.strip()
    if not query:
        query = "тестовый запрос"
    
    try:
        from api.llm.factory import get_llm_provider
        from api.config import settings
        
        provider = get_llm_provider()
        provider_name = settings.llm_provider
        model_name = settings.openrouter_model
        
        # Тестируем расширение запроса
        start_time = time.time()
        expanded_query = expand_query_with_llm(query)
        response_time = (time.time() - start_time) * 1000  # в миллисекундах
        
        logger.info(f"LLM тест успешен: {query} -> {expanded_query[:100]}...")
        
        return LLMTestResponse(
            success=True,
            query=query,
            expanded_query=expanded_query,
            provider=provider_name,
            model=model_name,
            response_time_ms=round(response_time, 2)
        )
    except Exception as e:
        logger.error(f"Ошибка при тесте LLM: {e}", exc_info=True)
        return LLMTestResponse(
            success=False,
            query=query,
            error=str(e),
            provider=settings.llm_provider if hasattr(settings, 'llm_provider') else "unknown",
            model=settings.openrouter_model if hasattr(settings, 'openrouter_model') else "unknown"
        )

