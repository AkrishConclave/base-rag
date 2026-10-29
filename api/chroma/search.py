"""Векторный поиск в ChromaDB"""
from __future__ import annotations
from api.config import settings
from api.chroma.client import get_embedder
from api.chroma.schema import SearchResult
from api.llm.prompt_refine import expand_query_with_llm
from api.utils.text import extract_keywords
from api.vector_engine import search_index


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
    q_emb = embedder.encode([search_query])[0]
    # Native C top-K searches only public candidates unless the authenticated
    # caller has staff access. This is enforced before reranking.
    vector_hits = search_index(q_emb, top_k * 10, admin_mode)
    
    import re
    # Сортируем и фильтруем результаты по сбалансированной математической метрике
    results_with_scores = []
    query_words = set(re.findall(r'\w+', query_lower))
    
    for hit in vector_hits:
        doc, meta, dist = hit.doc, hit.meta, hit.dist
        vector_score = max(0.0, 1.0 - dist)
        
        title = (meta.get('title') or '').lower()
        title_words = set(re.findall(r'\w+', title))
        
        if query_words:
            title_overlap = len(query_words & title_words) / len(query_words)
        else:
            title_overlap = 0.0

        final_score = 0.8 * vector_score + 0.2 * title_overlap
        results_with_scores.append({"doc": doc, "meta": meta, "dist": dist, "score": final_score})
    
    # Сортируем по score и берем лучшие
    results_with_scores.sort(key=lambda x: x["score"], reverse=True)
    results = []
    for r in results_with_scores[:top_k]:
        results.append(SearchResult(doc=r["doc"], meta=r["meta"], dist=r["dist"]))
    
    return results

