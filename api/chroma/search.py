"""Векторный поиск в ChromaDB"""
from __future__ import annotations
from api.config import settings
from api.chroma.client import get_collection, get_embedder
from api.chroma.schema import SearchResult
from api.llm.prompt_refine import expand_query_with_llm
from api.utils.text import extract_keywords


def search(query: str, top_k: int | None = None, admin_mode: bool = False) -> list[SearchResult]:
    """
    Выполняет векторный поиск в ChromaDB с расширением запроса через LLM
    
    Args:
        query: Поисковый запрос
        top_k: Количество результатов
        admin_mode: True = все статьи (status=0 ИЛИ status=1), False/не указан = только публичные (status=1)
    """
    if top_k is None:
        top_k = settings.top_k
    
    embedder = get_embedder()
    collection = get_collection()
    
    # Формируем фильтр по статусу
    where_filter = None
    if not admin_mode:
        # По умолчанию (публичная справка) - только статус 1 (для клиентов)
        where_filter = {"status": 1}
    # Если admin_mode=True, where_filter остается None - показываем все статьи (status=0 ИЛИ status=1)
    
    # Извлекаем ключевые слова из запроса
    keywords = extract_keywords(query)
    query_lower = query.lower()
    keywords_lower = keywords.lower()
    
    # Для коротких запросов (1-2 слова) используем их напрямую, для длинных - расширяем через LLM
    is_short_query = len(query.split()) <= 2
    
    if is_short_query:
        # Для коротких запросов используем оригинальный запрос + синонимы от LLM
        expanded_query = expand_query_with_llm(query)
        expanded_words = set(expanded_query.lower().split())
        search_query = expanded_query
    else:
        # Для длинных запросов используем комбинацию ключевых слов и расширенного запроса
        expanded_query = expand_query_with_llm(query)
        expanded_words = set(expanded_query.lower().split())
        search_query = f"{keywords} {expanded_query}" if keywords != query else expanded_query
    
    # Создаем эмбеддинг для поиска
    q_emb = embedder.encode([search_query])[0].tolist()
    
    # Запрашиваем больше результатов для фильтрации
    query_params = {
        "query_embeddings": [q_emb],
        "n_results": top_k * 10,  # Увеличиваем до 10x для лучшего покрытия
        "include": ["documents", "metadatas", "distances"]
    }
    if where_filter:
        query_params["where"] = where_filter
    
    resp = collection.query(**query_params)
    docs = resp["documents"][0]
    metas = resp["metadatas"][0]
    dists = resp["distances"][0]
    
    # Сортируем и фильтруем результаты
    results_with_scores = []
    query_words = set(query_lower.split())
    keywords_set = set(keywords_lower.split())
    
    # Дополнительно проверяем совпадение ключевых слов из расширенного запроса
    expanded_keywords = set([w for w in expanded_query.lower().split() if len(w) > 3])
    
    # Извлекаем ключевые слова из расширенного запроса для лучшего сопоставления
    important_words = set()
    for word in expanded_keywords:
        if word in ['прайс', 'товар', 'добавить', 'разместить', 'загрузить', 'создать']:
            important_words.add(word)
    
    for doc, meta, dist in zip(docs, metas, dists):
        score = 1.0 - dist  # Преобразуем расстояние в score (чем больше, тем лучше)
        
        # Бонус за совпадение ключевых слов в заголовке
        title = (meta.get('title') or '').lower()
        menu = (meta.get('menu') or '').lower()
        
        # Проверяем совпадения в заголовке и меню
        title_words = set(title.split())
        menu_words = set(menu.split())
        
        # Большой бонус за прямое совпадение ключевых слов в заголовке
        keyword_matches = keywords_set & title_words
        expanded_keyword_matches = expanded_keywords & title_words
        important_word_matches = important_words & title_words
        
        if keyword_matches:
            score += 0.8 * len(keyword_matches)
        elif important_word_matches:
            score += 1.0 * len(important_word_matches)
        elif expanded_keyword_matches:
            score += 0.6 * len(expanded_keyword_matches)
        elif query_words & title_words or expanded_words & title_words:
            score += 0.15
        
        # Бонус за совпадение слов в меню
        if keywords_set & menu_words:
            score += 0.4
        elif query_words & menu_words or expanded_words & menu_words:
            score += 0.1
        
        # Дополнительный бонус, если ключевое слово является частью заголовка
        for kw in keywords_set:
            if len(kw) > 3:
                kw_root = kw[:min(6, len(kw))]
                if kw in title or any(
                    kw_root in word or word.startswith(kw_root) or kw.startswith(word[:min(6, len(word))])
                    for word in title_words if len(word) > 3
                ):
                    score += 0.5
        
        # Бонус за частичное совпадение
        all_query_words = keywords_set | expanded_words
        for q_word in all_query_words:
            if len(q_word) > 4:
                if any(q_word in t_word or t_word in q_word for t_word in title_words if len(t_word) > 4):
                    score += 0.05
        
        results_with_scores.append({"doc": doc, "meta": meta, "dist": dist, "score": score})
    
    # Сортируем по score и берем лучшие
    results_with_scores.sort(key=lambda x: x["score"], reverse=True)
    results = []
    for r in results_with_scores[:top_k]:
        results.append(SearchResult(doc=r["doc"], meta=r["meta"], dist=r["dist"]))
    
    return results

