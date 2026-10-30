"""Роут для обработки вопросов через RAG"""
import asyncio
import json
import logging
import re
from fastapi import APIRouter, HTTPException, Request
from api.models.request import AskRequest
from api.models.response import AskResponse, Source
from api.chroma.search import search
from api.chroma.hybrid import hybrid_search
from api.llm.prompt_refine import expand_query_with_llm
from api.llm.prompt_answer import build_prompt
from api.llm.factory import get_llm_provider
from api.llm.cache import get_cache
from api.utils.text import extract_keywords
from api.vector_engine import search_title_matches

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["RAG"])

_RAG_RESPONSE_CACHE_SCOPE = "public-rag-response-v1"
_RAG_RESPONSE_CACHE_MODEL = "rag-response"


def _normalise_cache_question(question: str) -> str:
    """Make inconsequential whitespace and letter case share one cache entry."""
    return re.sub(r"\s+", " ", question).strip().casefold()


def _get_cached_response(question: str) -> AskResponse | None:
    cached = get_cache().get(
        _normalise_cache_question(question),
        _RAG_RESPONSE_CACHE_SCOPE,
        _RAG_RESPONSE_CACHE_MODEL,
    )
    if not cached:
        return None
    try:
        return AskResponse.model_validate(json.loads(cached))
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.warning("Ignoring an invalid cached RAG response")
        return None


def _cache_response(question: str, response: AskResponse) -> None:
    get_cache().set(
        _normalise_cache_question(question),
        _RAG_RESPONSE_CACHE_SCOPE,
        _RAG_RESPONSE_CACHE_MODEL,
        response.model_dump_json(),
    )


def _needs_query_rewrite(question: str) -> bool:
    """Avoid an extra model call when a title already clearly matches."""
    words = set(re.findall(r"\w+", extract_keywords(question).casefold()))
    return not search_title_matches(words, top_k=1, admin_mode=True)


def _format_search_results_as_answer(hits: list, question: str) -> str:
    """Форматирует результаты поиска как ответ, если LLM недоступен"""
    if not hits:
        return "К сожалению, по вашему запросу ничего не найдено в базе знаний."
    
    answer_parts = [
        f"Найдено {len(hits)} релевантных статей по запросу «{question}»:\n\n"
    ]
    
    for i, hit in enumerate(hits[:5], 1):  # Показываем до 5 лучших результатов
        title = hit.meta.get("title", "Без названия")
        doc = hit.doc[:300] + "..." if len(hit.doc) > 300 else hit.doc
        answer_parts.append(f"{i}. **{title}**\n{doc}\n")
    
    answer_parts.append(
        "\n*Примечание: Ответ сформирован на основе результатов поиска. "
        "Сервис генерации ответов временно недоступен.*"
    )
    
    return "\n".join(answer_parts)


@router.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest, req: Request):
    """
    Отвечает на вопрос пользователя на основе проиндексированных статей.
    Если LLM недоступен, возвращает результаты поиска с информативным сообщением.
    
    Args:
        request: Запрос с вопросом пользователя
        req: Объекты запроса FastAPI для проверки авторизации в заголовках
        
    Returns:
        Ответ с текстом и источниками
    """
    question = request.q.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Вопрос не может быть пустым")

    cached_response = _get_cached_response(question)
    if cached_response is not None:
        logger.info("💾 Returning cached RAG response")
        return cached_response
    
    # The public knowledge-base API intentionally searches the complete
    # published corpus. Operational endpoints retain their token protection;
    # `status` is not an access-control boundary for answers returned here.
    admin_mode = True

    # Поиск релевантных документов (гибридный или векторный)
    # Это критически важная часть - должна работать всегда
    try:
        search_query = question
        if _needs_query_rewrite(question):
            search_query = await asyncio.to_thread(expand_query_with_llm, question, True)
            logger.info("Using Yandex-normalized query for retrieval")
        if request.use_hybrid:
            hits = await asyncio.to_thread(hybrid_search, search_query, admin_mode=admin_mode)
        else:
            hits = await asyncio.to_thread(search, search_query, admin_mode=admin_mode)
        logger.info(f"Найдено {len(hits)} результатов для запроса: {question}")
    except Exception as e:
        logger.error(f"Ошибка при поиске документов: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Ошибка при поиске документов: {str(e)}"
        )
    
    # Формирование источников (всегда возвращаем, даже если LLM не работает)
    sources = []
    source_ids = set()
    for hit in hits:
        article_id = hit.meta.get("article_id", "")
        if article_id in source_ids:
            continue
        source_ids.add(article_id)
        sources.append(
            Source(
                title=hit.meta.get("title", "Без названия"),
                id=article_id,
                dist=hit.dist,
            )
        )
    
    # Попытка генерации ответа через LLM
    # Если не получится - возвращаем результаты поиска
    try:
        # Построение промпта
        prompt = build_prompt(question, hits)
        
        # Генерация ответа через LLM с fallback
        provider = get_llm_provider()
        answer = await asyncio.to_thread(
            provider.complete_with_fallback,
            prompt,
            system_message="Ты — помощник поддержки Support. Отвечай по контексту.",
            max_tokens=700
        )
        
        logger.info(f"✅ Успешно сгенерирован ответ через LLM для запроса: {question}")
        response = AskResponse(answer=answer, sources=sources)
        _cache_response(question, response)
        return response
        
    except ValueError as e:
        # Ошибка конфигурации (например, нет API ключа) - не критично, возвращаем поиск
        logger.warning(f"⚠️ Проблема с конфигурацией LLM: {e}. Возвращаю результаты поиска.")
        answer = _format_search_results_as_answer(hits, question)
        return AskResponse(answer=answer, sources=sources)
        
    except Exception as e:
        # Любая другая ошибка LLM - не критично, возвращаем поиск
        logger.warning(
            f"⚠️ LLM недоступен для запроса '{question}': {e}. "
            f"Возвращаю результаты поиска ({len(hits)} результатов)."
        )
        answer = _format_search_results_as_answer(hits, question)
        return AskResponse(answer=answer, sources=sources)

