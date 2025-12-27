"""Роут для обработки вопросов через RAG"""
import logging
from fastapi import APIRouter, HTTPException
from api.models.request import AskRequest
from api.models.response import AskResponse, Source
from api.chroma.search import search
from api.chroma.hybrid import hybrid_search
from api.llm.prompt_answer import build_prompt
from api.llm.factory import get_llm_provider

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["RAG"])


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
async def ask(request: AskRequest):
    """
    Отвечает на вопрос пользователя на основе проиндексированных статей.
    Если LLM недоступен, возвращает результаты поиска с информативным сообщением.
    
    Args:
        request: Запрос с вопросом пользователя
        
    Returns:
        Ответ с текстом и источниками
    """
    question = request.q.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Вопрос не может быть пустым")
    
    # Поиск релевантных документов (гибридный или векторный)
    # Это критически важная часть - должна работать всегда
    try:
        if request.use_hybrid:
            hits = hybrid_search(question, admin_mode=request.admin_mode)
        else:
            hits = search(question, admin_mode=request.admin_mode)
        logger.info(f"Найдено {len(hits)} результатов для запроса: {question}")
    except Exception as e:
        logger.error(f"Ошибка при поиске документов: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Ошибка при поиске документов: {str(e)}"
        )
    
    # Формирование источников (всегда возвращаем, даже если LLM не работает)
    sources = [
        Source(
            title=h.meta.get("title", "Без названия"),
            id=h.meta.get("article_id", ""),
            dist=h.dist
        )
        for h in hits
    ]
    
    # Попытка генерации ответа через LLM
    # Если не получится - возвращаем результаты поиска
    try:
        # Построение промпта
        prompt = build_prompt(question, hits)
        
        # Генерация ответа через LLM с fallback
        provider = get_llm_provider()
        answer = provider.complete_with_fallback(
            prompt,
            system_message="Ты — помощник поддержки Pinbox. Отвечай по контексту.",
            max_tokens=700
        )
        
        logger.info(f"✅ Успешно сгенерирован ответ через LLM для запроса: {question}")
        return AskResponse(answer=answer, sources=sources)
        
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

