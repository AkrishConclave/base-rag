"""Построение промптов для генерации ответов"""
from api.chroma.schema import SearchResult


def build_prompt(question: str, results: list[SearchResult]) -> str:
    """Строит промпт для генерации ответа на основе результатов поиска"""
    if not results:
        return f"Вопрос: {question}\n\nОтвет: К сожалению, в базе знаний не найдено релевантной информации для ответа на ваш вопрос."
    
    prompt_parts = []
    prompt_parts.append("Ты — помощник поддержки Support. Отвечай на вопросы пользователей на основе предоставленного контекста.")
    prompt_parts.append("")
    prompt_parts.append("ИНСТРУКЦИИ:")
    prompt_parts.append("1. Используй ТОЛЬКО информацию из контекста ниже")
    prompt_parts.append("2. Если в контексте есть прямой ответ — дай подробный, пошаговый ответ")
    prompt_parts.append("3. Структурируй ответ: используй списки, заголовки, выделяй важное")
    prompt_parts.append("4. Если информации недостаточно — скажи об этом, но используй то, что есть в контексте")
    prompt_parts.append("5. Отвечай на русском языке, дружелюбно и профессионально")
    prompt_parts.append("")
    prompt_parts.append("КОНТЕКСТ:")
    for idx, r in enumerate(results, 1):
        meta = r.meta
        title = meta.get('title', 'Без названия')
        prompt_parts.append(f"\n--- Источник {idx}: {title} ---")
        prompt_parts.append(r.doc)
    prompt_parts.append("")
    prompt_parts.append(f"ВОПРОС: {question}")
    prompt_parts.append("")
    prompt_parts.append("ОТВЕТ:")
    return "\n".join(prompt_parts)

