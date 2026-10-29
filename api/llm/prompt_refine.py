"""Расширение и улучшение поисковых запросов через эвристику и кэш"""
import logging
from api.utils.text import extract_keywords

logger = logging.getLogger(__name__)

# Словарь эвристических синонимов для домена Support
DOMAIN_SYNONYMS = {
    "прайс": ["товары и услуги", "товар", "услуга", "прейскурант"],
    "товар": ["прайс", "товары и услуги", "услуга"],
    "товары": ["прайс", "товары и услуги", "услуги"],
    "услуга": ["прайс", "товары и услуги", "товар"],
    "услуги": ["прайс", "товары и услуги", "товары"],
    "разместить": ["добавить", "загрузить", "создать", "опубликовать"],
    "размещение": ["добавление", "загрузка", "создание"],
    "добавить": ["разместить", "загрузить", "создать"],
    "загрузить": ["разместить", "добавить", "импортировать"],
    "создать": ["разместить", "добавить", "сформировать"],
    "отзыв": ["рецензия", "комментарий", "обжалование"],
    "отзывы": ["рецензии", "комментарии", "обжалование"],
    "обжалование": ["автообжалование", "отзывы", "жалоба"],
    "автообжалование": ["автоматическое обжалование", "обжалование отзывов"],
    "настроить": ["подключить", "установить", "активировать", "настройка"],
    "настройка": ["подключение", "установка", "параметры"],
    "подключить": ["настроить", "установить", "интегрировать"],
    "оповещения": ["уведомления", "email", "telegram"],
    "оповещение": ["уведомление", "рассылка"],
    "уведомления": ["оповещения", "email", "telegram"],
    "уведомление": ["оповещение", "предупреждение"],
    "интеграция": ["подключение", "api", "синхронизация"],
    "аккаунт": ["профиль", "учетная запись", "кабинет"],
    "профиль": ["аккаунт", "учетная запись"],
    "филиал": ["точка", "объект", "компания", "организация"],
    "филиалы": ["точки", "объекты", "компании", "организации"],
    "ошибка": ["проблема", "сбой", "не работает"],
}

_EXPANSION_CACHE: dict[str, str] = {}


def expand_query_heuristic(query: str) -> str:
    """
    Эвристическое расширение запроса синонимами без вызыва LLM.
    Быстро, детерминированно и не расходует токены / лимиты LLM.
    """
    keywords = extract_keywords(query)
    clean_words = keywords.lower().split()
    
    synonyms = []
    for word in clean_words:
        if word in DOMAIN_SYNONYMS:
            synonyms.extend(DOMAIN_SYNONYMS[word])
        else:
            if len(word) >= 4:
                prefix = word[:4]
                for key, syn_list in DOMAIN_SYNONYMS.items():
                    if key.startswith(prefix) or prefix in key:
                        synonyms.extend(syn_list)
                        break

    seen = set(clean_words)
    unique_synonyms = []
    for syn in synonyms:
        syn_lower = syn.lower()
        if syn_lower not in seen:
            seen.add(syn_lower)
            unique_synonyms.append(syn)
            if len(unique_synonyms) >= 8:
                break

    if unique_synonyms:
        expanded_query = f"{keywords} {' '.join(unique_synonyms)}"
    else:
        expanded_query = keywords

    return expanded_query


def expand_query_with_llm(query: str, use_llm: bool = False) -> str:
    """
    Расширение поискового запроса.
    По умолчанию использует эвристическое/кэшированное расширение для предотвращения
    избыточных вызовов LLM во время векторного и гибридного поиска.
    """
    if not query or not query.strip():
        return query

    query_key = query.strip().lower()

    if query_key in _EXPANSION_CACHE:
        return _EXPANSION_CACHE[query_key]

    if not use_llm:
        expanded = expand_query_heuristic(query)
        _EXPANSION_CACHE[query_key] = expanded
        return expanded

    try:
        from api.llm.factory import get_llm_provider
        provider = get_llm_provider()
        keywords = extract_keywords(query)
        
        prompt = f"""Пользователь задал вопрос для поиска в базе знаний Support: "{query}"

Извлеки ключевые слова и сгенерируй синонимы для улучшения поиска.
Верни ТОЛЬКО список ключевых слов и синонимов через запятую, без дополнительных объяснений."""
        system_message = "Ты помощник для расширения поисковых запросов. Отвечай кратко, только ключевые слова через запятую."

        expanded_text = provider.complete(prompt, system_message, max_tokens=80)
        variants = [
            v.strip() for v in expanded_text.replace('.', ',').split(',')
            if v.strip() and len(v.strip()) > 2
        ]
        original_words = set(keywords.lower().split())
        new_words = [v for v in variants if v.lower() not in original_words]
        expanded = f"{keywords} {' '.join(new_words[:8])}"
        _EXPANSION_CACHE[query_key] = expanded
        return expanded
    except Exception as e:
        logger.warning(f"⚠️ Ошибка LLM расширения запроса: {e}. Используем эвристику.")
        expanded = expand_query_heuristic(query)
        _EXPANSION_CACHE[query_key] = expanded
        return expanded
