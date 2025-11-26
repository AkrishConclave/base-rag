"""Роут для обработки вопросов через RAG"""
from fastapi import APIRouter, HTTPException
from api.models.request import AskRequest
from api.models.response import AskResponse, Source
from api.chroma.search import search
from api.chroma.hybrid import hybrid_search
from api.llm.prompt_answer import build_prompt
from api.llm.factory import get_llm_provider

router = APIRouter(prefix="/api", tags=["RAG"])


@router.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """
    Отвечает на вопрос пользователя на основе проиндексированных статей
    
    Args:
        request: Запрос с вопросом пользователя
        
    Returns:
        Ответ с текстом и источниками
    """
    question = request.q.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Вопрос не может быть пустым")
    
    try:
        # Поиск релевантных документов (гибридный или векторный)
        if request.use_hybrid:
            hits = hybrid_search(question)
        else:
            hits = search(question)
        
        # Построение промпта
        prompt = build_prompt(question, hits)
        
        # Генерация ответа через LLM
        provider = get_llm_provider()
        answer = provider.complete_with_fallback(
            prompt,
            system_message="Ты — помощник поддержки Pinbox. Отвечай по контексту.",
            max_tokens=700
        )
        
        # Формирование источников
        sources = [
            Source(
                title=h.meta.get("title", "Без названия"),
                id=h.meta.get("article_id", ""),
                dist=h.dist
            )
            for h in hits
        ]
        
        return AskResponse(answer=answer, sources=sources)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при обработке запроса: {str(e)}")

