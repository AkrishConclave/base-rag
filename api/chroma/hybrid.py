"""Гибридный поиск: комбинация BM25 (классический) и векторного поиска"""
from __future__ import annotations
from typing import List
from api.config import settings
from api.chroma.client import get_embedder
from api.chroma.embeddings import encode_query
from api.chroma.schema import SearchResult
from api.llm.prompt_refine import expand_query_with_llm
from api.utils.text import extract_keywords
from api.vector_engine import search_index


def bm25_search(query: str, documents: List[str], top_k: int = 10) -> List[tuple[int, float]]:
    """
    Простой BM25 поиск по документам
    
    Args:
        query: Поисковый запрос
        documents: Список документов для поиска
        top_k: Количество результатов
        
    Returns:
        Список кортежей (индекс документа, score)
    """
    import re
    from collections import Counter
    
    # Токенизация запроса
    query_words = set(re.findall(r'\w+', query.lower()))
    if not query_words:
        return []
    
    # Подсчет TF-IDF для каждого документа
    doc_scores = []
    total_docs = len(documents)
    
    for idx, doc in enumerate(documents):
        doc_words = re.findall(r'\w+', doc.lower())
        doc_word_counts = Counter(doc_words)
        doc_length = len(doc_words)
        
        if doc_length == 0:
            continue
        
        score = 0.0
        for word in query_words:
            if word in doc_word_counts:
                # Простой TF-IDF score
                tf = doc_word_counts[word] / doc_length
                # IDF (упрощенный - считаем сколько документов содержат слово)
                docs_with_word = sum(1 for d in documents if word in d.lower())
                idf = 1.0 if docs_with_word == 0 else total_docs / docs_with_word
                score += tf * idf
        
        if score > 0:
            doc_scores.append((idx, score))
    
    # Сортируем по score и берем top_k
    doc_scores.sort(key=lambda x: x[1], reverse=True)
    return doc_scores[:top_k]


def hybrid_search(query: str, top_k: int | None = None, bm25_weight: float = 0.3, admin_mode: bool = False) -> list[SearchResult]:
    """
    Гибридный поиск: комбинация BM25 и векторного поиска
    
    Args:
        query: Поисковый запрос
        top_k: Количество результатов
        bm25_weight: Вес BM25 (0.0-1.0), остальное - векторный поиск
        admin_mode: True = все статьи (status=0 ИЛИ status=1), False/не указан = только публичные (status=1)
        
    Returns:
        Список результатов поиска
    """
    if top_k is None:
        top_k = settings.top_k
    
    embedder = get_embedder()
    
    # Извлекаем ключевые слова и расширяем запрос
    keywords = extract_keywords(query)
    expanded_query = expand_query_with_llm(query)
    search_query = f"{keywords} {expanded_query}" if keywords != query else expanded_query
    
    # Векторный поиск
    q_emb = encode_query(embedder, search_query)
    vector_hits = search_index(q_emb, top_k * 3, admin_mode)
    vector_docs = [hit.doc for hit in vector_hits]
    vector_metas = [hit.meta for hit in vector_hits]
    vector_dists = [hit.dist for hit in vector_hits]
    
    # BM25 поиск по найденным документам
    bm25_results = bm25_search(query, vector_docs, top_k=len(vector_docs))
    bm25_scores = {idx: score for idx, score in bm25_results}
    
    # Комбинируем результаты
    results_with_scores = []
    vector_weight = 1.0 - bm25_weight
    
    for idx, (doc, meta, dist) in enumerate(zip(vector_docs, vector_metas, vector_dists)):
        # Native index returns cosine distance: 1 - cosine_similarity.
        vector_score = max(0.0, 1.0 - dist)
        
        # Получаем BM25 score (нормализуем к 0-1)
        bm25_score = bm25_scores.get(idx, 0.0)
        if bm25_score > 0:
            # Нормализуем BM25 score (максимальный score становится 1.0)
            max_bm25 = max(bm25_scores.values()) if bm25_scores else 1.0
            bm25_normalized = bm25_score / max_bm25 if max_bm25 > 0 else 0.0
        else:
            bm25_normalized = 0.0
        
        # Комбинируем scores
        hybrid_score = (vector_score * vector_weight) + (bm25_normalized * bm25_weight)
        
        results_with_scores.append({
            "doc": doc,
            "meta": meta,
            "dist": dist,
            "score": hybrid_score
        })
    
    # Сортируем по комбинированному score
    results_with_scores.sort(key=lambda x: x["score"], reverse=True)
    
    # Возвращаем top_k результатов
    results = []
    for r in results_with_scores[:top_k]:
        results.append(SearchResult(doc=r["doc"], meta=r["meta"], dist=r["dist"]))
    
    return results

