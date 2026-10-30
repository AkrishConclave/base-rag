"""Векторный поиск в ChromaDB"""
from __future__ import annotations
from api.config import settings
from api.chroma.client import get_embedder
from api.chroma.embeddings import encode_query
from api.chroma.schema import SearchResult
from api.llm.prompt_refine import expand_query_with_llm
from api.utils.text import extract_keywords
from api.vector_engine import search_index, search_title_matches


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
    
    import re
    meaningful_words = set(re.findall(r'\w+', keywords.lower()))
    # Create lexical title candidates first. They complement, rather than
    # replace, semantic retrieval for exact how-to article names.
    title_hits = search_title_matches(meaningful_words, top_k, admin_mode)

    embedder = get_embedder()
    # Создаем эмбеддинг для поиска
    q_emb = encode_query(embedder, search_query)
    # Native C top-K searches only public candidates unless the authenticated
    # caller has staff access. This is enforced before reranking.
    vector_hits = search_index(q_emb, top_k * 10, admin_mode)
    
    # Do not reward boilerplate question words such as "что такое".  They occur
    # in many article titles and previously let a generic FAQ outrank an article
    # whose title contained the actual subject of the request.
    # Сортируем и фильтруем результаты по сбалансированной математической метрике
    results_with_scores = []
    
    for hit in vector_hits:
        doc, meta, dist = hit.doc, hit.meta, hit.dist
        vector_score = max(0.0, 1.0 - dist)
        
        title = (meta.get('title') or '').lower()
        title_words = set(re.findall(r'\w+', title))
        
        if meaningful_words:
            title_overlap = len(meaningful_words & title_words) / len(meaningful_words)
        else:
            title_overlap = 0.0

        # A title is curated metadata and an exact meaningful-word match is a
        # stronger signal than a semantically similar generic help article.
        final_score = 0.7 * vector_score + 0.3 * title_overlap
        results_with_scores.append({"doc": doc, "meta": meta, "dist": dist, "score": final_score})
    
    # Сортируем по score и берем лучшие
    results_with_scores.sort(key=lambda x: x["score"], reverse=True)
    results = []
    seen_articles = set()
    for hit in title_hits:
        article_id = hit.meta.get("article_id", "")
        if article_id not in seen_articles:
            results.append(hit)
            seen_articles.add(article_id)
    for r in results_with_scores[:top_k]:
        article_id = r["meta"].get("article_id", "")
        if article_id not in seen_articles:
            results.append(SearchResult(doc=r["doc"], meta=r["meta"], dist=r["dist"]))
            seen_articles.add(article_id)
        if len(results) >= top_k:
            break
    
    return results

